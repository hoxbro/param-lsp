"""Tests for List item_type and Tuple length validation."""

from __future__ import annotations

import pytest

from param_lsp.analyzer import ParamAnalyzer


class TestContainerValidation:
    """Test validation of container parameter constraints."""

    @pytest.fixture
    def analyzer(self):
        """Create a fresh analyzer instance for each test."""
        return ParamAnalyzer()

    def test_list_item_type_validation_valid(self, analyzer):
        """Test that valid List item types pass validation."""
        code = """
import param

class TestClass(param.Parameterized):
    tags = param.List(default=["tag1", "tag2"], item_type=str)

config = TestClass(tags=["valid", "strings"])
"""
        result = analyzer.analyze_file(code, "test_file.py")
        type_errors = result.get("type_errors", [])
        assert len(type_errors) == 0

    def test_list_item_type_validation_invalid(self, analyzer):
        """Test that invalid List item types are caught."""
        code = """
import param

class TestClass(param.Parameterized):
    tags = param.List(default=["tag1", "tag2"], item_type=str)

config = TestClass(tags=["tag1", 123])
"""
        result = analyzer.analyze_file(code, "test_file.py")
        type_errors = result.get("type_errors", [])
        assert len(type_errors) == 1
        assert (
            "Item 1 in List parameter 'tags' has type int, expected str"
            in type_errors[0]["message"]
        )

    def test_tuple_length_validation_valid(self, analyzer):
        """Test that valid Tuple lengths pass validation."""
        code = """
import param

class TestClass(param.Parameterized):
    coordinates = param.Tuple(default=(0, 0), length=2)

config = TestClass(coordinates=(10, 20))
"""
        result = analyzer.analyze_file(code, "test_file.py")
        type_errors = result.get("type_errors", [])
        assert len(type_errors) == 0

    def test_tuple_length_validation_invalid(self, analyzer):
        """Test that invalid Tuple lengths are caught."""
        code = """
import param

class TestClass(param.Parameterized):
    coordinates = param.Tuple(default=(0, 0), length=2)

config = TestClass(coordinates=(1, 2, 3))
"""
        result = analyzer.analyze_file(code, "test_file.py")
        type_errors = result.get("type_errors", [])
        assert len(type_errors) == 1
        assert (
            "Tuple parameter 'coordinates' has 3 elements, expected 2" in type_errors[0]["message"]
        )

    def test_combined_container_validation(self, analyzer):
        """Test multiple container validation errors in one file."""
        code = """
import param

class TestClass(param.Parameterized):
    tags = param.List(default=["tag1", "tag2"], item_type=str)
    coordinates = param.Tuple(default=(0, 0), length=2)

config = TestClass(
    tags=["tag1", 123],  # Invalid item type
    coordinates=(1, 2, 3)  # Invalid length
)
"""
        result = analyzer.analyze_file(code, "test_file.py")
        type_errors = result.get("type_errors", [])
        assert len(type_errors) == 2

        error_messages = [error["message"] for error in type_errors]
        assert any(
            "Item 1 in List parameter 'tags' has type int, expected str" in msg
            for msg in error_messages
        )
        assert any(
            "Tuple parameter 'coordinates' has 3 elements, expected 2" in msg
            for msg in error_messages
        )

    def test_parameter_extraction_stores_constraints(self, analyzer):
        """Test that parameter extraction correctly stores item_type and length."""
        code = """
import param

class TestClass(param.Parameterized):
    tags = param.List(default=["tag1", "tag2"], item_type=str)
    coordinates = param.Tuple(default=(0, 0), length=2)
    numbers = param.List(default=[1, 2], item_type=int)
"""
        result = analyzer.analyze_file(code, "test_file.py")
        param_classes = result.get("param_classes", {})

        assert "TestClass" in param_classes
        test_class = param_classes["TestClass"]

        # Check tags parameter
        tags_param = test_class.get_parameter("tags")
        assert tags_param is not None
        assert tags_param.cls == "List"
        assert tags_param.item_type is str
        assert tags_param.length is None

        # Check coordinates parameter
        coordinates_param = test_class.get_parameter("coordinates")
        assert coordinates_param is not None
        assert coordinates_param.cls == "Tuple"
        assert coordinates_param.item_type is None
        assert coordinates_param.length == 2

        # Check numbers parameter
        numbers_param = test_class.get_parameter("numbers")
        assert numbers_param is not None
        assert numbers_param.cls == "List"
        assert numbers_param.item_type is int
        assert numbers_param.length is None
