"""Tests for external library caching functionality."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from param_lsp.cache import ExternalLibraryCache, external_library_cache
from param_lsp.models import ParameterInfo, ParameterizedInfo
from tests.conftest import _get_library_version_from_env


@pytest.fixture
def enable_cache_for_test(monkeypatch):
    """Enable cache for specific cache tests."""
    monkeypatch.setenv("PARAM_LSP_DISABLE_CACHE", "0")


@pytest.fixture
def isolated_cache():
    """
    Provide an isolated cache environment for tests that modify the global cache.

    This fixture prevents cache pollution between tests by using a temporary
    cache directory that's automatically cleaned up after the test.

    Usage:
        def test_something(isolated_cache):
            # Test code that modifies cache
            external_library_cache.clear()  # Safe - won't affect other tests
    """
    # Save the original cache directory
    original_cache_dir = external_library_cache.cache_dir

    # Create and use a temporary directory for this test
    with tempfile.TemporaryDirectory() as temp_dir:
        external_library_cache.cache_dir = Path(temp_dir)
        try:
            yield external_library_cache
        finally:
            # Restore the original cache directory
            external_library_cache.cache_dir = original_cache_dir


class TestExternalLibraryCache:
    """Test the ExternalLibraryCache functionality."""

    def test_cache_initialization(self):
        """Test that cache initializes properly."""
        cache = ExternalLibraryCache()
        assert cache.cache_dir.exists()
        assert cache.cache_dir.is_dir()

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

            # Create test data using dataclass format
            param_class_info = ParameterizedInfo(name="IntSlider")
            param_class_info.add_parameter(
                ParameterInfo(
                    name="value",
                    cls="Integer",
                    bounds=None,
                    doc=None,
                    allow_None=False,
                    default=None,
                )
            )
            param_class_info.add_parameter(
                ParameterInfo(
                    name="name",
                    cls="String",
                    bounds=None,
                    doc=None,
                    allow_None=False,
                    default=None,
                )
            )
            # Set cache data with version 1.0.0
            cache.set("panel", "panel.widgets.IntSlider", param_class_info, "1.0.0")

            # Get cache data
            result = cache.get("panel", "panel.widgets.IntSlider", "1.0.0")

            assert result is not None
            assert result.name == param_class_info.name
            assert len(result.parameters) == len(param_class_info.parameters)
            assert "value" in result.parameters
            assert "name" in result.parameters

    def test_cache_get_nonexistent(self, enable_cache_for_test):
        """Test getting data that doesn't exist in cache."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ExternalLibraryCache()
            cache.cache_dir = Path(temp_dir)

            result = cache.get("panel", "panel.widgets.NonExistent", "1.0.0")
            assert result is None

    def test_cache_multiple_classes_same_library(self, enable_cache_for_test):
        """Test caching multiple classes from the same library."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ExternalLibraryCache()
            cache.cache_dir = Path(temp_dir)

            # Create test data using dataclass format
            param_class_info1 = ParameterizedInfo(name="IntSlider")
            param_class_info1.add_parameter(
                ParameterInfo(
                    name="value",
                    cls="Integer",
                    bounds=None,
                    doc=None,
                    allow_None=False,
                    default=None,
                )
            )
            param_class_info2 = ParameterizedInfo(name="TextInput")
            param_class_info2.add_parameter(
                ParameterInfo(
                    name="text",
                    cls="String",
                    bounds=None,
                    doc=None,
                    allow_None=False,
                    default=None,
                )
            )

            # Set data for two different classes
            cache.set("panel", "panel.widgets.IntSlider", param_class_info1, "1.0.0")
            cache.set("panel", "panel.widgets.TextInput", param_class_info2, "1.0.0")

            # Get both classes
            result1 = cache.get("panel", "panel.widgets.IntSlider", "1.0.0")
            result2 = cache.get("panel", "panel.widgets.TextInput", "1.0.0")

            assert result1 is not None
            assert result1.name == param_class_info1.name
            assert "value" in result1.parameters

            assert result2 is not None
            assert result2.name == param_class_info2.name
            assert "text" in result2.parameters

    def test_cache_version_isolation(self, enable_cache_for_test):
        """Test that different versions create separate cache files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ExternalLibraryCache()
            cache.cache_dir = Path(temp_dir)

            # Create test data using dataclass format for version 1
            param_class_info_v1 = ParameterizedInfo(name="Widget")
            param_class_info_v1.add_parameter(
                ParameterInfo(
                    name="old_param",
                    cls="String",
                    bounds=None,
                    doc=None,
                    allow_None=False,
                    default=None,
                )
            )

            # Create test data using dataclass format for version 2
            param_class_info_v2 = ParameterizedInfo(name="Widget")
            param_class_info_v2.add_parameter(
                ParameterInfo(
                    name="new_param",
                    cls="String",
                    bounds=None,
                    doc=None,
                    allow_None=False,
                    default=None,
                )
            )

            # Cache data for version 1.0.0
            cache.set("panel", "panel.widgets.Widget", param_class_info_v1, "1.0.0")

            # Cache data for version 2.0.0
            cache.set("panel", "panel.widgets.Widget", param_class_info_v2, "2.0.0")

            # Get data for each version
            result_v1 = cache.get("panel", "panel.widgets.Widget", "1.0.0")
            result_v2 = cache.get("panel", "panel.widgets.Widget", "2.0.0")

            assert result_v1 is not None
            assert result_v1.name == param_class_info_v1.name
            assert "old_param" in result_v1.parameters
            assert result_v2 is not None
            assert result_v2.name == param_class_info_v2.name
            assert "new_param" in result_v2.parameters

    def test_cache_clear_specific_library(self, enable_cache_for_test):
        """Test clearing cache for a specific library."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ExternalLibraryCache()
            cache.cache_dir = Path(temp_dir)

            # Create test data using dataclass format
            param_class_info = ParameterizedInfo(name="IntSlider")
            param_class_info.add_parameter(
                ParameterInfo(
                    name="value",
                    cls="Integer",
                    bounds=None,
                    doc=None,
                    allow_None=False,
                    default=None,
                )
            )
            # Set cache data
            cache.set("panel", "panel.widgets.IntSlider", param_class_info, "1.0.0")

            # Verify it's there
            result = cache.get("panel", "panel.widgets.IntSlider", "1.0.0")
            assert result is not None
            assert result.name == param_class_info.name
            assert "value" in result.parameters

            # Clear the cache
            cache.clear("panel", "1.0.0")

            # Verify it's gone
            result = cache.get("panel", "panel.widgets.IntSlider", "1.0.0")
            assert result is None

    def test_cache_clear_all(self, enable_cache_for_test):
        """Test clearing all cache files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ExternalLibraryCache()
            cache.cache_dir = Path(temp_dir)

            # Create test data using dataclass format
            param_class_info = ParameterizedInfo(name="TestClass")
            param_class_info.add_parameter(
                ParameterInfo(
                    name="value",
                    cls="Integer",
                    bounds=None,
                    doc=None,
                    allow_None=False,
                    default=None,
                )
            )
            # Set cache data for multiple libraries
            cache.set("panel", "panel.widgets.IntSlider", param_class_info, "1.0.0")
            cache.set("holoviews", "holoviews.Curve", param_class_info, "1.0.0")

            # Clear all caches
            cache.clear()

            # Verify all are gone
            result1 = cache.get("panel", "panel.widgets.IntSlider", "1.0.0")
            result2 = cache.get("holoviews", "holoviews.Curve", "1.0.0")
            assert result1 is None
            assert result2 is None

    def test_cache_corrupted_file_handling(self, enable_cache_for_test):
        """Test handling of corrupted cache files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ExternalLibraryCache()
            cache.cache_dir = Path(temp_dir)

            # Create a corrupted cache file
            cache_path = cache._get_cache_path("panel", "1.0.0")
            cache_path.write_text("invalid json{")

            # Getting from corrupted cache should return None
            result = cache.get("panel", "panel.widgets.IntSlider", "1.0.0")
            assert result is None

            # Setting should overwrite the corrupted file
            param_class_info = ParameterizedInfo(name="IntSlider")
            param_class_info.add_parameter(
                ParameterInfo(
                    name="value",
                    cls="Integer",
                    bounds=None,
                    doc=None,
                    allow_None=False,
                    default=None,
                )
            )
            cache.set("panel", "panel.widgets.IntSlider", param_class_info, "1.0.0")

            # Now get should work
            result = cache.get("panel", "panel.widgets.IntSlider", "1.0.0")
            assert result is not None
            assert result.name == param_class_info.name
            assert "value" in result.parameters


class TestCacheIntegration:
    """Test cache integration with the analyzer."""

    def setup_class(self):
        pytest.importorskip("panel")

    def test_analyzer_uses_cache(self, analyzer, enable_cache_for_test):
        """Test that the analyzer uses the cache for external classes."""
        panel_version = _get_library_version_from_env("panel")

        # Mock the cache to return predefined ParameterizedInfo data
        param_class_info = ParameterizedInfo(name="IntSlider")
        param_class_info.add_parameter(
            ParameterInfo(
                name="value",
                cls="Integer",
                bounds=None,
                doc=None,
                allow_None=False,
                default=None,
            )
        )
        original_get = external_library_cache.get
        external_library_cache.get = Mock(return_value=param_class_info)

        try:
            code_py = """\
import panel as pn
w = pn.widgets.IntSlider()
w.value = "invalid"  # should error
"""
            result = analyzer.analyze_file(code_py)

            # Verify cache was called with version
            external_library_cache.get.assert_called_with(
                "panel", "panel.widgets.IntSlider", panel_version
            )

            # Should still detect type error using cached data
            assert len(result["type_errors"]) == 1
            error = result["type_errors"][0]
            assert error["code"] == "runtime-type-mismatch"

        finally:
            # Restore original method
            external_library_cache.get = original_get

    def test_analyzer_populates_cache(self, analyzer, enable_cache_for_test, isolated_cache):
        """Test that the analyzer populates the cache after external class analysis.

        This test mocks the expensive external class analysis and focuses on testing
        that the cache storage mechanism works correctly. The actual analysis is tested
        in test_static_external_analyzer.py.
        """
        panel_version = _get_library_version_from_env("panel")

        # Create mock class info
        mock_class_info = ParameterizedInfo(
            name="IntSlider",
            parameters={
                "value": ParameterInfo(
                    name="value",
                    cls="Integer",
                    default="0",
                    bounds=(0, 100),
                    doc="The current value",
                )
            },
        )

        # Verify cache is initially empty
        assert isolated_cache.get("panel", "panel.widgets.IntSlider", panel_version) is None

        # Mock the expensive operations to focus on cache storage
        with (
            patch.object(
                analyzer.external_inspector,
                "_analyze_class_from_source",
                return_value=mock_class_info,
            ),
            patch.object(analyzer.external_inspector, "populate_library_cache", return_value=0),
        ):
            code_py = """\
import panel as pn
w = pn.widgets.IntSlider()
"""
            analyzer.analyze_file(code_py)

        # Verify cache was populated with the expected data
        cached_data = isolated_cache.get("panel", "panel.widgets.IntSlider", panel_version)
        assert cached_data is not None
        assert isinstance(cached_data, ParameterizedInfo)
        assert cached_data.name == "IntSlider"
        assert "value" in cached_data.parameters


@pytest.mark.parametrize(
    # Update the version and expected values when updating uv.lock
    ("library_name", "library_version", "expected_classes", "expected_aliases"),
    [
        ("param", "2.2.1", 11, 5),
        ("panel", "1.8.2", 275, 190),
        ("holoviews", "1.21.0", 348, 112),
    ],
)
def test_cache_population_levels(
    enable_cache_for_test, library_name, library_version, expected_classes, expected_aliases
):
    """Test that cache population produces expected number of classes and aliases.

    This test ensures that the cache population regression is caught early by
    verifying exact counts of classes and aliases for each library.

    Note: When library versions are updated, run the cache regeneration and update
    the expected values in the parametrize decorator above with the new counts.
    """

    pytest.importorskip(library_name)

    cache_path = external_library_cache._get_cache_path(library_name, library_version)
    assert cache_path.exists(), (
        f"Cache file does not exist for {library_name} version {library_version}"
    )

    with open(cache_path) as f:
        cache_data = json.load(f)

    classes = cache_data.get("classes", {})
    aliases = cache_data.get("aliases", {})

    # Verify exact class count
    assert len(classes) == expected_classes, (
        f"{library_name}: Cache has {len(classes)} classes, expected {expected_classes}"
    )

    # Verify exact alias count
    assert len(aliases) == expected_aliases, (
        f"{library_name}: Cache has {len(aliases)} aliases, expected {expected_aliases}"
    )

    # Verify metadata structure
    assert "metadata" in cache_data
    assert cache_data["metadata"]["library_name"] == library_name
    assert "library_version" in cache_data["metadata"]
    assert "cache_version" in cache_data["metadata"]
