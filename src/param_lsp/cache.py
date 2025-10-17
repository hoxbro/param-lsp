"""Cache management for external library introspection results."""

from __future__ import annotations

import json
import os
import re
import time
from functools import cache
from pathlib import Path
from typing import Any

import platformdirs

from ._logging import get_logger
from .models import ParameterInfo, ParameterizedInfo

logger = get_logger(__name__, "cache")

# Current cache version
CACHE_VERSION = (1, 1, 1)
_re_no = re.compile(r"\d+")


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
        self._pending_cache: dict[str, dict[str, Any]] = {}

    def _get_cache_path(self, library_name: str, version: str) -> Path:
        """Get the cache file path for a library."""
        parsed_version = parse_version(version)
        version_str = string_version(parsed_version, "_")
        cache_str = string_version(CACHE_VERSION, "_")
        filename = f"{library_name}-{version_str}-{cache_str}.json"
        return self.cache_dir / filename

    def has_library_cache(self, library_name: str, version: str) -> bool:
        """Check if cache exists and has content for a library."""
        if not self._caching_enabled:
            return False

        if not version:
            return False

        cache_path = self._get_cache_path(library_name, version)
        if not cache_path.exists():
            return False

        try:
            with cache_path.open("r", encoding="utf-8") as f:
                cache_data = json.load(f)

            # Validate cache format and version compatibility
            if not self._is_cache_valid(cache_data, library_name, version):
                return False

            # Check if cache has any classes
            classes_data = cache_data.get("classes", {})
            return len(classes_data) > 0
        except (json.JSONDecodeError, OSError):
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
            classes_data = cache_data.get("classes", {})
            class_data = classes_data.get(class_path)
            if class_data:
                return self._deserialize_param_class_info(class_data)

            # Check if this is an alias for another class
            aliases = cache_data.get("aliases", {})
            if class_path in aliases:
                full_path = aliases[class_path]
                class_data = classes_data.get(full_path)
                if class_data:
                    return self._deserialize_param_class_info(class_data)

        # If not in pending cache, check disk cache
        cache_path = self._get_cache_path(library_name, version)
        if not cache_path.exists():
            return None

        try:
            with cache_path.open("r", encoding="utf-8") as f:
                cache_data = json.load(f)

            # Validate cache format and version compatibility
            if not self._is_cache_valid(cache_data, library_name, version):
                logger.debug(f"Cache invalid for {library_name}, will regenerate")
                return None

            # Check if this specific class path is in the cache
            classes_data = cache_data.get("classes", {})
            class_data = classes_data.get(class_path)
            if class_data:
                return self._deserialize_param_class_info(class_data)

            # Check if this is an alias for another class
            aliases = cache_data.get("aliases", {})
            if class_path in aliases:
                full_path = aliases[class_path]
                class_data = classes_data.get(full_path)
                if class_data:
                    return self._deserialize_param_class_info(class_data)

            return None
        except (json.JSONDecodeError, OSError) as e:
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
                    with cache_path.open("r", encoding="utf-8") as f:
                        existing_data = json.load(f)
                    # Validate and migrate existing cache if needed
                    if self._is_cache_valid(existing_data, library_name, version):
                        cache_data = existing_data
                    # If invalid, cache_data keeps the new structure
                except (json.JSONDecodeError, OSError):
                    # If we can't read existing cache, start fresh
                    pass

            # Ensure aliases dict exists (for backward compatibility)
            if "aliases" not in cache_data:
                cache_data["aliases"] = {}

            self._pending_cache[cache_key] = cache_data

        # Serialize the dataclass to dict format
        serialized_data = self._serialize_param_class_info(data)

        # Update with new data in memory
        self._pending_cache[cache_key]["classes"][class_path] = serialized_data

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
                    with cache_path.open("r", encoding="utf-8") as f:
                        existing_data = json.load(f)
                    if self._is_cache_valid(existing_data, library_name, version):
                        cache_data = existing_data
                except (json.JSONDecodeError, OSError):
                    pass

            # Ensure aliases dict exists
            if "aliases" not in cache_data:
                cache_data["aliases"] = {}

            self._pending_cache[cache_key] = cache_data

        # Add the alias mapping in memory
        self._pending_cache[cache_key]["aliases"][alias_path] = full_path

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
            with cache_path.open("w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2)
            logger.debug(f"Flushed cache for {library_name} to {cache_path}")
        except OSError as e:
            logger.debug(f"Failed to write cache for {library_name}: {e}")

        # Clear pending cache for this library version after writing
        del self._pending_cache[cache_key]

    def _create_cache_structure(self, library_name: str, version: str) -> dict[str, Any]:
        """Create a new cache structure with metadata."""
        return {
            "metadata": {
                "library_name": library_name,
                "library_version": parse_version(version),
                "created_at": int(time.time()),
                "cache_version": CACHE_VERSION,
            },
            "classes": {},
            "aliases": {},  # Maps re-export paths to full paths (e.g., panel.widgets.TextInput -> panel.widgets.input.TextInput)
        }

    def _is_cache_valid(self, cache_data: dict[str, Any], library_name: str, version: str) -> bool:
        """Validate cache data format and version compatibility."""
        # Only accept new format with metadata
        if "metadata" not in cache_data:
            return False

        metadata = cache_data.get("metadata", {})

        # Check library name match
        if metadata.get("library_name") != library_name:
            return False

        # Check library version match
        if tuple(metadata.get("library_version", ())) != parse_version(version):
            return False

        # Only accept exact cache version match (no backward compatibility)
        return tuple(metadata.get("cache_version", ())) == CACHE_VERSION

    def _serialize_param_class_info(self, param_class_info: ParameterizedInfo) -> dict[str, Any]:
        """Serialize ParameterizedInfo to dictionary format for JSON storage."""
        parameters_data = {}

        for param_name, param_info in param_class_info.parameters.items():
            parameters_data[param_name] = {
                "name": param_info.name,
                "cls": param_info.cls,
                "bounds": param_info.bounds,
                "doc": param_info.doc,
                "allow_None": param_info.allow_None,
                "default": param_info.default,
                "location": param_info.location,
                "objects": param_info.objects,
            }

        return {
            "class_name": param_class_info.name,
            "parameters": parameters_data,
        }

    def _deserialize_param_class_info(self, data: dict[str, Any]) -> ParameterizedInfo | None:
        """Deserialize dictionary format back to ParameterizedInfo."""
        # Handle new dataclass format
        if "class_name" in data and "parameters" in data and isinstance(data["parameters"], dict):
            class_name = data["class_name"]
            parameters_data = data["parameters"]

            param_class_info = ParameterizedInfo(name=class_name)

            for param_data in parameters_data.values():
                # Handle backward compatibility - old cache may have "param_type" instead of "cls"
                cls_value = param_data.get("cls") or param_data.get("param_type", "Unknown")
                allow_None_value = param_data.get("allow_None")
                if allow_None_value is None:
                    allow_None_value = param_data.get("allow_none", False)

                param_info = ParameterInfo(
                    name=param_data["name"],
                    cls=cls_value,
                    bounds=param_data.get("bounds"),
                    doc=param_data.get("doc"),
                    allow_None=allow_None_value,
                    default=param_data.get("default"),
                    location=param_data.get("location"),
                    objects=param_data.get("objects"),
                    item_type=param_data.get("item_type"),
                    length=param_data.get("length"),
                )
                param_class_info.add_parameter(param_info)

            return param_class_info

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
            pattern = f"*-{cache_version_str}.json"
            for cache_file in self.cache_dir.glob(pattern):
                cache_file.unlink()


# Global cache instance
external_library_cache = ExternalLibraryCache()
