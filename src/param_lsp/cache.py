"""Cache management for external library introspection results."""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
import os
from pathlib import Path
from typing import Any

import platformdirs

logger = logging.getLogger(__name__)


class ExternalLibraryCache:
    """Cache for external library introspection results using platformdirs."""

    def __init__(self):
        self.cache_dir = Path(platformdirs.user_cache_dir("param-lsp", "param-lsp"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # Check if caching is disabled (useful for tests)
        self._caching_enabled = os.getenv("PARAM_LSP_DISABLE_CACHE", "").lower() not in (
            "1",
            "true",
            "yes",
        )

    def _get_cache_key(self, library_name: str, version: str) -> str:
        """Generate a cache key based on library name and version."""
        content = f"{library_name}:{version}"
        return hashlib.sha256(content.encode()).hexdigest()

    def _get_cache_path(self, library_name: str, version: str) -> Path:
        """Get the cache file path for a library."""
        cache_key = self._get_cache_key(library_name, version)
        return self.cache_dir / f"{cache_key}.json"

    def _get_library_version(self, library_name: str) -> str | None:
        """Get the version of an installed library."""
        try:
            module = importlib.import_module(library_name)
            # Try different common version attributes
            for attr in ["__version__", "version", "VERSION"]:
                if hasattr(module, attr):
                    version = getattr(module, attr)
                    return str(version) if version else None
            return None
        except ImportError:
            return None

    def get(self, library_name: str, class_path: str) -> dict[str, Any] | None:
        """Get cached introspection data for a library class."""
        if not self._caching_enabled:
            return None

        version = self._get_library_version(library_name)
        if not version:
            return None

        cache_path = self._get_cache_path(library_name, version)
        if not cache_path.exists():
            return None

        try:
            with cache_path.open("r", encoding="utf-8") as f:
                cache_data = json.load(f)

            # Check if this specific class path is in the cache
            return cache_data.get(class_path)
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"Failed to read cache for {library_name}: {e}")
            return None

    def set(self, library_name: str, class_path: str, data: dict[str, Any]) -> None:
        """Cache introspection data for a library class."""
        if not self._caching_enabled:
            return

        version = self._get_library_version(library_name)
        if not version:
            return

        cache_path = self._get_cache_path(library_name, version)

        # Load existing cache data or create new
        cache_data = {}
        if cache_path.exists():
            try:
                with cache_path.open("r", encoding="utf-8") as f:
                    cache_data = json.load(f)
            except (json.JSONDecodeError, OSError):
                cache_data = {}

        # Update with new data
        cache_data[class_path] = data

        # Save updated cache
        try:
            with cache_path.open("w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2)
        except OSError as e:
            logger.debug(f"Failed to write cache for {library_name}: {e}")

    def clear(self, library_name: str | None = None) -> None:
        """Clear cache for a specific library or all libraries."""
        if library_name:
            version = self._get_library_version(library_name)
            if version:
                cache_path = self._get_cache_path(library_name, version)
                if cache_path.exists():
                    cache_path.unlink()
        else:
            # Clear all cache files
            for cache_file in self.cache_dir.glob("*.json"):
                cache_file.unlink()


# Global cache instance
external_library_cache = ExternalLibraryCache()
