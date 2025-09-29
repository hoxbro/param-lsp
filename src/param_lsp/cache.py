"""Cache management for external library introspection results."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from functools import cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import platformdirs

from .models import ParameterInfo, ParameterizedInfo

logger = logging.getLogger(__name__)

# Current cache version
CACHE_VERSION = (1, 0, 0)
_re_no = re.compile(r"\d+")


@cache
def parse_version(version_str: str) -> tuple[int, ...]:
    """Parse a version string into a tuple of integers."""
    return tuple(map(int, _re_no.findall(version_str)[:3]))


@cache
def _get_version(library_name):
    try:
        return version(library_name)
    except PackageNotFoundError:
        return None


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

    def _get_cache_path(self, library_name: str, version: str) -> Path:
        """Get the cache file path for a library."""
        parsed_version = parse_version(version)
        version_str = "_".join(map(str, parsed_version))
        cache_str = "_".join(map(str, CACHE_VERSION))
        filename = f"{library_name}-{version_str}-{cache_str}.json"
        return self.cache_dir / filename

    def _get_library_version(self, library_name: str) -> str | None:
        """Get the version of an installed library."""
        return _get_version(library_name)

    def get(self, library_name: str, class_path: str) -> ParameterizedInfo | None:
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

            # Validate cache format and version compatibility
            if not self._is_cache_valid(cache_data, library_name, version):
                logger.debug(f"Cache invalid for {library_name}, will regenerate")
                return None

            # Check if this specific class path is in the cache
            classes_data = cache_data.get("classes", {})
            class_data = classes_data.get(class_path)
            if class_data:
                return self._deserialize_param_class_info(class_data)
            return None
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"Failed to read cache for {library_name}: {e}")
            return None

    def set(self, library_name: str, class_path: str, data: ParameterizedInfo) -> None:
        """Cache introspection data for a library class."""
        if not self._caching_enabled:
            return

        version = self._get_library_version(library_name)
        if not version:
            return

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

        # Serialize the dataclass to dict format
        serialized_data = self._serialize_param_class_info(data)

        # Update with new data
        cache_data["classes"][class_path] = serialized_data

        # Save updated cache
        try:
            with cache_path.open("w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2)
        except OSError as e:
            logger.debug(f"Failed to write cache for {library_name}: {e}")

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
