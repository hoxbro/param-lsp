"""Cache management for external library introspection results."""

from __future__ import annotations

import os
import re
import time
from functools import cache
from pathlib import Path

import msgspec
import platformdirs

from ._logging import get_logger
from .models import ParameterizedInfo  # noqa: TC001 - needed at runtime for msgspec

logger = get_logger(__name__, "cache")

# Current cache version (bumped to 1.3.0 for msgspec.Struct)
CACHE_VERSION = (1, 3, 0)
_re_no = re.compile(r"\d+")


class CacheMetadata(msgspec.Struct):
    """Metadata for a library cache."""

    library_name: str
    library_version: tuple[int, ...]
    created_at: int
    cache_version: tuple[int, int, int]


class LibraryCache(msgspec.Struct):
    """Complete cache structure for a library."""

    metadata: CacheMetadata
    classes: dict[str, ParameterizedInfo] = msgspec.field(default_factory=dict)
    aliases: dict[str, str] = msgspec.field(default_factory=dict)
    parameter_types: list[str] = msgspec.field(default_factory=list)


@cache
def parse_version(version_str: str) -> tuple[int, ...]:
    """Parse a version string into a tuple of integers."""
    return tuple(map(int, _re_no.findall(version_str)[:3]))


def string_version(version_tuple, delimiter):
    return delimiter.join(map(str, version_tuple))


class ExternalLibraryCache:
    """Cache for external library introspection results using platformdirs."""

    def __init__(self):
        self.cache_dir = Path(platformdirs.user_cache_dir("param-lsp", "param-lsp"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # Check if caching is disabled (useful for tests)
        self._caching_enabled = os.getenv("PARAM_LSP_DISABLE_CACHE", "").lower() not in (
            "1",
            "true",
        )
        # Pending cache changes that will be written on flush()
        self._pending_cache: dict[str, LibraryCache] = {}

    def _get_cache_path(self, library_name: str, version: str) -> Path:
        """Get the cache file path for a library."""
        parsed_version = parse_version(version)
        version_str = string_version(parsed_version, "_")
        cache_str = string_version(CACHE_VERSION, "_")
        filename = f"{library_name}-{version_str}-{cache_str}.msgpack"
        return self.cache_dir / filename

    def has_library_cache(self, library_name: str, version: str) -> bool:
        """Check if cache exists and has content for a library."""
        if not self._caching_enabled:
            return False

        if not version:
            return False

        # Check in-memory pending cache first (fast path)
        cache_key = f"{library_name}:{version}"
        if cache_key in self._pending_cache:
            return len(self._pending_cache[cache_key].classes) > 0

        # Check disk cache (slower path)
        cache_path = self._get_cache_path(library_name, version)
        if not cache_path.exists():
            return False

        try:
            with cache_path.open("rb") as f:
                cache_data = msgspec.msgpack.decode(f.read(), type=LibraryCache)

            # Validate cache format and version compatibility
            if not self._is_cache_valid(cache_data, library_name, version):
                return False

            # Load into memory for future fast lookups
            self._pending_cache[cache_key] = cache_data

            # Check if cache has any classes
            return len(cache_data.classes) > 0
        except (msgspec.DecodeError, msgspec.ValidationError, OSError):
            return False

    def get(self, library_name: str, class_path: str, version: str) -> ParameterizedInfo | None:
        """Get cached introspection data for a library class."""
        if not self._caching_enabled:
            return None

        if not version:
            return None

        # Check pending cache first (in-memory cache)
        cache_key = f"{library_name}:{version}"
        if cache_key in self._pending_cache:
            cache_data = self._pending_cache[cache_key]

            # Check if this specific class path is in the pending cache
            param_info = cache_data.classes.get(class_path)
            if param_info:
                return param_info

            # Check if this is an alias for another class (follow alias chain)
            current_path = class_path
            seen = set()  # Prevent infinite loops
            while current_path in cache_data.aliases and current_path not in seen:
                seen.add(current_path)
                current_path = cache_data.aliases[current_path]
                param_info = cache_data.classes.get(current_path)
                if param_info:
                    return param_info

        # If not in pending cache, check disk cache
        cache_path = self._get_cache_path(library_name, version)
        if not cache_path.exists():
            return None

        try:
            with cache_path.open("rb") as f:
                cache_data = msgspec.msgpack.decode(f.read(), type=LibraryCache)

            # Validate cache format and version compatibility
            if not self._is_cache_valid(cache_data, library_name, version):
                logger.debug(f"Cache invalid for {library_name}, will regenerate")
                return None

            # Load the disk cache into memory for subsequent fast lookups
            self._pending_cache[cache_key] = cache_data

            # Check if this specific class path is in the cache
            param_info = cache_data.classes.get(class_path)
            if param_info:
                return param_info

            # Check if this is an alias for another class (follow alias chain)
            current_path = class_path
            seen = set()  # Prevent infinite loops
            while current_path in cache_data.aliases and current_path not in seen:
                seen.add(current_path)
                current_path = cache_data.aliases[current_path]
                param_info = cache_data.classes.get(current_path)
                if param_info:
                    return param_info

            return None
        except (msgspec.DecodeError, msgspec.ValidationError, OSError) as e:
            logger.debug(f"Failed to read cache for {library_name}: {e}")
            return None

    def set(
        self, library_name: str, class_path: str, data: ParameterizedInfo, version: str
    ) -> None:
        """Cache introspection data for a library class in memory.

        Args:
            library_name: Name of the library
            class_path: Full path to the class
            data: Parameter information for the class
            version: Version of the library
        """
        if not self._caching_enabled:
            return

        if not version:
            return

        # Get or initialize pending cache for this library version
        cache_key = f"{library_name}:{version}"
        if cache_key not in self._pending_cache:
            cache_path = self._get_cache_path(library_name, version)

            # Load existing cache data or create new with metadata
            cache_data = self._create_cache_structure(library_name, version)
            if cache_path.exists():
                try:
                    with cache_path.open("rb") as f:
                        existing_data = msgspec.msgpack.decode(f.read(), type=LibraryCache)
                    # Validate and migrate existing cache if needed
                    if self._is_cache_valid(existing_data, library_name, version):
                        cache_data = existing_data
                    # If invalid, cache_data keeps the new structure
                except (msgspec.DecodeError, msgspec.ValidationError, OSError):
                    # If we can't read existing cache, start fresh
                    pass

            self._pending_cache[cache_key] = cache_data

        # Update with new data in memory (data is already a ParameterizedInfo Struct)
        self._pending_cache[cache_key].classes[class_path] = data

    def set_alias(self, library_name: str, alias_path: str, full_path: str, version: str) -> None:
        """Register an alias (re-export) for a class in memory.

        Args:
            library_name: Name of the library
            alias_path: Short/alias path (e.g., panel.widgets.TextInput)
            full_path: Full/canonical path (e.g., panel.widgets.input.TextInput)
            version: Version of the library
        """
        if not self._caching_enabled:
            return

        if not version:
            return

        # Get or initialize pending cache for this library version
        cache_key = f"{library_name}:{version}"
        if cache_key not in self._pending_cache:
            cache_path = self._get_cache_path(library_name, version)

            # Load existing cache data or create new
            cache_data = self._create_cache_structure(library_name, version)
            if cache_path.exists():
                try:
                    with cache_path.open("rb") as f:
                        existing_data = msgspec.msgpack.decode(f.read(), type=LibraryCache)
                    if self._is_cache_valid(existing_data, library_name, version):
                        cache_data = existing_data
                except (msgspec.DecodeError, msgspec.ValidationError, OSError):
                    pass

            self._pending_cache[cache_key] = cache_data

        # Add the alias mapping in memory
        self._pending_cache[cache_key].aliases[alias_path] = full_path

    def set_parameter_types(
        self, library_name: str, parameter_types: set[str], version: str
    ) -> None:
        """Store detected Parameter type paths for a library in memory.

        Args:
            library_name: Name of the library
            parameter_types: Set of full paths to detected Parameter types
            version: Version of the library
        """
        if not self._caching_enabled:
            return

        if not version:
            return

        # Get or initialize pending cache for this library version
        cache_key = f"{library_name}:{version}"
        if cache_key not in self._pending_cache:
            cache_path = self._get_cache_path(library_name, version)

            # Load existing cache data or create new
            cache_data = self._create_cache_structure(library_name, version)
            if cache_path.exists():
                try:
                    with cache_path.open("rb") as f:
                        existing_data = msgspec.msgpack.decode(f.read(), type=LibraryCache)
                    if self._is_cache_valid(existing_data, library_name, version):
                        cache_data = existing_data
                except (msgspec.DecodeError, msgspec.ValidationError, OSError):
                    pass

            self._pending_cache[cache_key] = cache_data

        # Store parameter types as a sorted list for consistent output
        self._pending_cache[cache_key].parameter_types = sorted(parameter_types)

    def get_parameter_types(self, library_name: str, version: str) -> set[str]:
        """Get detected Parameter type paths for a library from cache.

        Args:
            library_name: Name of the library
            version: Version of the library

        Returns:
            Set of full paths to detected Parameter types, empty set if not found
        """
        if not self._caching_enabled:
            return set()

        if not version:
            return set()

        # Check pending cache first (in-memory cache)
        cache_key = f"{library_name}:{version}"
        if cache_key in self._pending_cache:
            return set(self._pending_cache[cache_key].parameter_types)

        # If not in pending cache, check disk cache
        cache_path = self._get_cache_path(library_name, version)
        if not cache_path.exists():
            return set()

        try:
            with cache_path.open("rb") as f:
                cache_data = msgspec.msgpack.decode(f.read(), type=LibraryCache)

            # Validate cache format and version compatibility
            if not self._is_cache_valid(cache_data, library_name, version):
                return set()

            # Load the disk cache into memory for subsequent fast lookups
            self._pending_cache[cache_key] = cache_data

            return set(cache_data.parameter_types)
        except (msgspec.DecodeError, msgspec.ValidationError, OSError):
            return set()

    def flush(self, library_name: str, version: str) -> None:
        """Write all pending cache changes for a library to disk.

        Args:
            library_name: Name of the library to flush cache for
            version: Version of the library
        """
        if not self._caching_enabled:
            return

        if not version:
            return

        cache_key = f"{library_name}:{version}"
        if cache_key not in self._pending_cache:
            return

        cache_path = self._get_cache_path(library_name, version)
        cache_data = self._pending_cache[cache_key]

        try:
            with cache_path.open("wb") as f:
                f.write(msgspec.msgpack.encode(cache_data))
            logger.debug(f"Flushed cache for {library_name} to {cache_path}")
        except OSError as e:
            logger.debug(f"Failed to write cache for {library_name}: {e}")

        # Clear pending cache for this library version after writing
        del self._pending_cache[cache_key]

    def _create_cache_structure(self, library_name: str, version: str) -> LibraryCache:
        """Create a new cache structure with metadata."""
        metadata = CacheMetadata(
            library_name=library_name,
            library_version=parse_version(version),
            created_at=int(time.time()),
            cache_version=CACHE_VERSION,
        )
        return LibraryCache(
            metadata=metadata,
            classes={},
            aliases={},
            parameter_types=[],
        )

    def _is_cache_valid(self, cache_data: LibraryCache, library_name: str, version: str) -> bool:
        """Validate cache data format and version compatibility."""
        metadata = cache_data.metadata

        # Check library name match
        if metadata.library_name != library_name:
            return False

        # Check library version match
        if tuple(metadata.library_version) != parse_version(version):
            return False

        # Only accept exact cache version match (no backward compatibility)
        return tuple(metadata.cache_version) == CACHE_VERSION

    def clear(self, library_name: str | None = None, version: str | None = None) -> None:
        """Clear cache for a specific library or all libraries."""
        cache_str = string_version(CACHE_VERSION, ".")
        logger.info(f"Clearing existing cache (v{cache_str})")
        if library_name:
            # Clear pending cache for this library (all versions)
            keys_to_delete = [
                key for key in self._pending_cache if key.startswith(f"{library_name}:")
            ]
            for key in keys_to_delete:
                del self._pending_cache[key]

            # Clear disk cache
            if version:
                cache_path = self._get_cache_path(library_name, version)
                if cache_path.exists():
                    cache_path.unlink()
        else:
            # Clear all pending caches
            self._pending_cache.clear()

            # Clear all cache files for the current cache version only
            cache_version_str = string_version(CACHE_VERSION, "_")
            pattern = f"*-{cache_version_str}.msgpack"
            for cache_file in self.cache_dir.glob(pattern):
                cache_file.unlink()


# Global cache instance
external_library_cache = ExternalLibraryCache()
