"""Tests for external library caching functionality."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from param_lsp.cache import ExternalLibraryCache, external_library_cache


@pytest.fixture
def enable_cache_for_test(monkeypatch):
    """Enable cache for specific cache tests."""
    monkeypatch.setenv("PARAM_LSP_DISABLE_CACHE", "0")


class TestExternalLibraryCache:
    """Test the ExternalLibraryCache functionality."""

    def test_cache_initialization(self):
        """Test that cache initializes properly."""
        cache = ExternalLibraryCache()
        assert cache.cache_dir.exists()
        assert cache.cache_dir.is_dir()

    def test_get_library_version(self):
        """Test getting library version."""
        cache = ExternalLibraryCache()

        # Mock a module with __version__
        mock_module = Mock()
        mock_module.__version__ = "1.2.3"

        with patch("importlib.import_module", return_value=mock_module):
            version = cache._get_library_version("test_lib")
            assert version == "1.2.3"

    def test_get_library_version_no_version(self):
        """Test getting library version when no version attribute exists."""
        cache = ExternalLibraryCache()

        # Mock a module without version
        mock_module = Mock(spec=[])  # Empty spec means no attributes

        with patch("importlib.import_module", return_value=mock_module):
            version = cache._get_library_version("test_lib")
            assert version is None

    def test_get_library_version_import_error(self):
        """Test getting library version when import fails."""
        cache = ExternalLibraryCache()

        with patch("importlib.import_module", side_effect=ImportError):
            version = cache._get_library_version("nonexistent_lib")
            assert version is None

    def test_cache_path_generation(self):
        """Test cache path generation produces different paths for different libraries/versions."""
        cache = ExternalLibraryCache()
        path1 = cache._get_cache_path("panel", "1.0.0")
        path2 = cache._get_cache_path("panel", "1.0.1")
        path3 = cache._get_cache_path("holoviews", "1.0.0")

        # Paths should be different for different versions and libraries
        assert path1 != path2
        assert path1 != path3
        assert path2 != path3

        # Same library and version should produce same path
        path1_again = cache._get_cache_path("panel", "1.0.0")
        assert path1 == path1_again

    def test_cache_set_and_get(self, enable_cache_for_test):
        """Test setting and getting cache data."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ExternalLibraryCache()
            cache.cache_dir = Path(temp_dir)

            test_data = {
                "parameters": ["value", "name"],
                "parameter_types": {"value": "Integer", "name": "String"},
                "parameter_bounds": {},
                "parameter_docs": {},
                "parameter_allow_none": {},
                "parameter_defaults": {},
            }

            # Mock library version
            with patch.object(cache, "_get_library_version", return_value="1.0.0"):
                # Set cache data
                cache.set("panel", "panel.widgets.IntSlider", test_data)

                # Get cache data
                result = cache.get("panel", "panel.widgets.IntSlider")

                assert result == test_data

    def test_cache_get_nonexistent(self, enable_cache_for_test):
        """Test getting data that doesn't exist in cache."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ExternalLibraryCache()
            cache.cache_dir = Path(temp_dir)

            with patch.object(cache, "_get_library_version", return_value="1.0.0"):
                result = cache.get("panel", "panel.widgets.NonExistent")
                assert result is None

    def test_cache_multiple_classes_same_library(self, enable_cache_for_test):
        """Test caching multiple classes from the same library."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ExternalLibraryCache()
            cache.cache_dir = Path(temp_dir)

            test_data1 = {"parameters": ["value"], "parameter_types": {"value": "Integer"}}
            test_data2 = {"parameters": ["text"], "parameter_types": {"text": "String"}}

            with patch.object(cache, "_get_library_version", return_value="1.0.0"):
                # Set data for two different classes
                cache.set("panel", "panel.widgets.IntSlider", test_data1)
                cache.set("panel", "panel.widgets.TextInput", test_data2)

                # Get both classes
                result1 = cache.get("panel", "panel.widgets.IntSlider")
                result2 = cache.get("panel", "panel.widgets.TextInput")

                assert result1 == test_data1
                assert result2 == test_data2

    def test_cache_version_isolation(self, enable_cache_for_test):
        """Test that different versions create separate cache files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ExternalLibraryCache()
            cache.cache_dir = Path(temp_dir)

            test_data_v1 = {"parameters": ["old_param"]}
            test_data_v2 = {"parameters": ["new_param"]}

            # Cache data for version 1.0.0
            with patch.object(cache, "_get_library_version", return_value="1.0.0"):
                cache.set("panel", "panel.widgets.Widget", test_data_v1)

            # Cache data for version 2.0.0
            with patch.object(cache, "_get_library_version", return_value="2.0.0"):
                cache.set("panel", "panel.widgets.Widget", test_data_v2)

            # Get data for each version
            with patch.object(cache, "_get_library_version", return_value="1.0.0"):
                result_v1 = cache.get("panel", "panel.widgets.Widget")

            with patch.object(cache, "_get_library_version", return_value="2.0.0"):
                result_v2 = cache.get("panel", "panel.widgets.Widget")

            assert result_v1 == test_data_v1
            assert result_v2 == test_data_v2

    def test_cache_clear_specific_library(self, enable_cache_for_test):
        """Test clearing cache for a specific library."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ExternalLibraryCache()
            cache.cache_dir = Path(temp_dir)

            test_data = {"parameters": ["value"]}

            with patch.object(cache, "_get_library_version", return_value="1.0.0"):
                # Set cache data
                cache.set("panel", "panel.widgets.IntSlider", test_data)

                # Verify it's there
                result = cache.get("panel", "panel.widgets.IntSlider")
                assert result == test_data

                # Clear the cache
                cache.clear("panel")

                # Verify it's gone
                result = cache.get("panel", "panel.widgets.IntSlider")
                assert result is None

    def test_cache_clear_all(self, enable_cache_for_test):
        """Test clearing all cache files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ExternalLibraryCache()
            cache.cache_dir = Path(temp_dir)

            test_data = {"parameters": ["value"]}

            with patch.object(cache, "_get_library_version", return_value="1.0.0"):
                # Set cache data for multiple libraries
                cache.set("panel", "panel.widgets.IntSlider", test_data)
                cache.set("holoviews", "holoviews.Curve", test_data)

            # Clear all caches
            cache.clear()

            with patch.object(cache, "_get_library_version", return_value="1.0.0"):
                # Verify all are gone
                result1 = cache.get("panel", "panel.widgets.IntSlider")
                result2 = cache.get("holoviews", "holoviews.Curve")
                assert result1 is None
                assert result2 is None

    def test_cache_corrupted_file_handling(self, enable_cache_for_test):
        """Test handling of corrupted cache files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ExternalLibraryCache()
            cache.cache_dir = Path(temp_dir)

            # Create a corrupted cache file
            with patch.object(cache, "_get_library_version", return_value="1.0.0"):
                cache_path = cache._get_cache_path("panel", "1.0.0")
                cache_path.write_text("invalid json{")

                # Getting from corrupted cache should return None
                result = cache.get("panel", "panel.widgets.IntSlider")
                assert result is None

                # Setting should overwrite the corrupted file
                test_data = {"parameters": ["value"]}
                cache.set("panel", "panel.widgets.IntSlider", test_data)

                # Now get should work
                result = cache.get("panel", "panel.widgets.IntSlider")
                assert result == test_data


class TestCacheIntegration:
    """Test cache integration with the analyzer."""

    def setup_class(self):
        pytest.importorskip("panel")

    def test_analyzer_uses_cache(self, analyzer, enable_cache_for_test):
        """Test that the analyzer uses the cache for external classes."""
        # Mock the cache to return predefined data
        test_data = {
            "parameters": ["value"],
            "parameter_types": {"value": "Integer"},
            "parameter_bounds": {},
            "parameter_docs": {},
            "parameter_allow_none": {},
            "parameter_defaults": {},
        }

        original_get = external_library_cache.get
        external_library_cache.get = Mock(return_value=test_data)

        try:
            code_py = """\
import panel as pn
w = pn.widgets.IntSlider()
w.value = "invalid"  # should error
"""
            result = analyzer.analyze_file(code_py)

            # Verify cache was called
            external_library_cache.get.assert_called_with("panel", "panel.widgets.IntSlider")

            # Should still detect type error using cached data
            assert len(result["type_errors"]) == 1
            error = result["type_errors"][0]
            assert error["code"] == "runtime-type-mismatch"

        finally:
            # Restore original method
            external_library_cache.get = original_get

    def test_analyzer_populates_cache(self, analyzer, enable_cache_for_test):
        """Test that the analyzer populates the cache after introspection."""

        # Clear any existing cache
        external_library_cache.clear()

        # Mock the set method to verify it's called
        original_set = external_library_cache.set
        external_library_cache.set = Mock()

        try:
            code_py = """\
import panel as pn
w = pn.widgets.IntSlider()
"""
            analyzer.analyze_file(code_py)

            # Verify cache set was called
            external_library_cache.set.assert_called()
            call_args = external_library_cache.set.call_args
            assert call_args[0][0] == "panel"  # library name
            assert call_args[0][1] == "panel.widgets.IntSlider"  # class path
            assert isinstance(call_args[0][2], dict)  # data

        finally:
            # Restore original method
            external_library_cache.set = original_set
