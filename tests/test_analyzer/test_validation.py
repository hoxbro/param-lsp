"""Tests for the ParameterValidator modular component."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from parso import parse

from src.param_lsp._analyzer.parso_utils import get_value, walk_tree
from src.param_lsp._analyzer.validation import ParameterValidator
from src.param_lsp.models import ParameterInfo, ParameterizedInfo


class TestParameterValidator:
    """Test the ParameterValidator modular component."""

    @pytest.fixture
    def sample_param_classes(self):
        """Create sample param classes for testing."""
        test_class = ParameterizedInfo(name="TestClass")
        test_class.add_parameter(
            ParameterInfo(
                name="test_param",
                cls="String",
                default="test_value",
                doc="Test parameter",
            )
        )
        test_class.add_parameter(
            ParameterInfo(
                name="numeric_param",
                cls="Number",
                default="42.0",
                bounds=(0, 100),
                doc="Numeric parameter with bounds",
            )
        )
        test_class.add_parameter(
            ParameterInfo(
                name="bool_param",
                cls="Boolean",
                default="True",
                doc="Boolean parameter",
            )
        )

        return {"TestClass": test_class}

    @pytest.fixture
    def sample_external_classes(self):
        """Create sample external param classes for testing."""
        return {}

    @pytest.fixture
    def sample_imports(self):
        """Create sample imports mapping."""
        return {"param": "param", "Parameterized": "param.Parameterized"}

    @pytest.fixture
    def mock_is_parameter_assignment(self):
        """Mock function for parameter assignment detection."""

        def mock_func(assignment_node):
            # Simple mock that returns True for typical parameter assignments
            # This mimics the behavior of checking if it's a param.Parameter call
            return True  # For testing, assume all assignments are parameter assignments

        return mock_func

    @pytest.fixture
    def mock_external_inspector(self):
        """Mock external inspector for testing."""
        mock = Mock()
        mock.analyze_external_class.return_value = None
        return mock

    @pytest.fixture
    def validator(
        self,
        sample_param_classes,
        sample_external_classes,
        sample_imports,
        mock_is_parameter_assignment,
        mock_external_inspector,
    ):
        """Create a ParameterValidator instance for testing."""
        return ParameterValidator(
            param_classes=sample_param_classes,
            external_param_classes=sample_external_classes,
            imports=sample_imports,
            is_parameter_assignment_func=mock_is_parameter_assignment,
            external_inspector=mock_external_inspector,
            workspace_root=None,
        )

    def test_infer_value_type_string(self, validator):
        """Test _infer_value_type with string literals."""
        code = 'x = "test_string"'
        tree = parse(code)
        # Find the string literal node
        string_nodes = [node for node in walk_tree(tree) if node.type == "string"]
        assert len(string_nodes) == 1

        inferred_type = validator._infer_value_type(string_nodes[0])
        assert inferred_type is str

    def test_infer_value_type_integer(self, validator):
        """Test _infer_value_type with integer literals."""
        code = "x = 42"
        tree = parse(code)
        # Find the number literal node
        number_nodes = [node for node in walk_tree(tree) if node.type == "number"]
        assert len(number_nodes) == 1

        inferred_type = validator._infer_value_type(number_nodes[0])
        assert inferred_type is int

    def test_infer_value_type_float(self, validator):
        """Test _infer_value_type with float literals."""
        code = "x = 3.14"
        tree = parse(code)
        # Find the number literal node
        number_nodes = [node for node in walk_tree(tree) if node.type == "number"]
        assert len(number_nodes) == 1

        inferred_type = validator._infer_value_type(number_nodes[0])
        assert inferred_type is float

    def test_infer_value_type_boolean_true(self, validator):
        """Test _infer_value_type with boolean True."""
        code = "x = True"
        tree = parse(code)
        # Find the keyword node for True
        keyword_nodes = [
            node
            for node in walk_tree(tree)
            if node.type == "keyword" and get_value(node) == "True"
        ]
        assert len(keyword_nodes) == 1

        inferred_type = validator._infer_value_type(keyword_nodes[0])
        assert inferred_type is bool

    def test_infer_value_type_boolean_false(self, validator):
        """Test _infer_value_type with boolean False."""
        code = "x = False"
        tree = parse(code)
        # Find the keyword node for False
        keyword_nodes = [
            node
            for node in walk_tree(tree)
            if node.type == "keyword" and get_value(node) == "False"
        ]
        assert len(keyword_nodes) == 1

        inferred_type = validator._infer_value_type(keyword_nodes[0])
        assert inferred_type is bool

    def test_infer_value_type_none(self, validator):
        """Test _infer_value_type with None."""
        code = "x = None"
        tree = parse(code)
        # Find the keyword node for None
        keyword_nodes = [
            node
            for node in walk_tree(tree)
            if node.type == "keyword" and get_value(node) == "None"
        ]
        assert len(keyword_nodes) == 1

        inferred_type = validator._infer_value_type(keyword_nodes[0])
        assert inferred_type is type(None)

    def test_infer_value_type_list(self, validator):
        """Test _infer_value_type with list literals."""
        code = "x = [1, 2, 3]"
        tree = parse(code)
        # Find the list literal node (atom containing brackets)
        atom_nodes = [
            node
            for node in walk_tree(tree)
            if node.type == "atom"
            and any(
                child.type == "operator" and child.value == "["
                for child in getattr(node, "children", [])
            )
        ]
        assert len(atom_nodes) == 1

        inferred_type = validator._infer_value_type(atom_nodes[0])
        assert inferred_type is list

    def test_infer_value_type_tuple(self, validator):
        """Test _infer_value_type with tuple literals."""
        code = "x = (1, 2, 3)"
        tree = parse(code)
        # Find the tuple literal node (atom containing parentheses)
        atom_nodes = [
            node
            for node in walk_tree(tree)
            if node.type == "atom"
            and any(
                child.type == "operator" and child.value == "("
                for child in getattr(node, "children", [])
            )
        ]
        assert len(atom_nodes) == 1

        inferred_type = validator._infer_value_type(atom_nodes[0])
        assert inferred_type is tuple

    def test_infer_value_type_dict(self, validator):
        """Test _infer_value_type with dict literals."""
        code = 'x = {"a": 1, "b": 2}'
        tree = parse(code)
        # Find the dict literal node (atom containing braces)
        atom_nodes = [
            node
            for node in walk_tree(tree)
            if node.type == "atom"
            and any(
                child.type == "operator" and child.value == "{"
                for child in getattr(node, "children", [])
            )
        ]
        assert len(atom_nodes) == 1

        inferred_type = validator._infer_value_type(atom_nodes[0])
        assert inferred_type is dict

    def test_is_boolean_literal_true(self, validator):
        """Test _is_boolean_literal with True."""
        code = "x = True"
        tree = parse(code)
        # Find the keyword node for True
        keyword_nodes = [
            node
            for node in walk_tree(tree)
            if node.type == "keyword" and get_value(node) == "True"
        ]
        assert len(keyword_nodes) == 1

        assert validator._is_boolean_literal(keyword_nodes[0]) is True

    def test_is_boolean_literal_false(self, validator):
        """Test _is_boolean_literal with False."""
        code = "x = False"
        tree = parse(code)
        # Find the keyword node for False
        keyword_nodes = [
            node
            for node in walk_tree(tree)
            if node.type == "keyword" and get_value(node) == "False"
        ]
        assert len(keyword_nodes) == 1

        assert validator._is_boolean_literal(keyword_nodes[0]) is True

    def test_is_boolean_literal_not_boolean(self, validator):
        """Test _is_boolean_literal with non-boolean."""
        code = 'x = "not_boolean"'
        tree = parse(code)
        # Find the string literal node
        string_nodes = [node for node in walk_tree(tree) if node.type == "string"]
        assert len(string_nodes) == 1

        assert validator._is_boolean_literal(string_nodes[0]) is False

    def test_format_expected_types_single(self, validator):
        """Test _format_expected_types with single type."""
        formatted = validator._format_expected_types((str,))
        assert formatted == "str"

    def test_format_expected_types_multiple(self, validator):
        """Test _format_expected_types with multiple types."""
        formatted = validator._format_expected_types((str, int))
        assert "str" in formatted
        assert "int" in formatted

    def test_parse_bounds_format_tuple(self, validator):
        """Test _parse_bounds_format with tuple bounds."""
        result = validator._parse_bounds_format((0, 10))
        assert result == (0, 10, True, True)  # inclusive on both sides

    def test_parse_bounds_format_invalid(self, validator):
        """Test _parse_bounds_format with invalid bounds."""
        result = validator._parse_bounds_format((1, 2, 3))  # 3 elements, invalid
        assert result is None

    def test_format_bounds_description(self, validator):
        """Test _format_bounds_description."""
        description = validator._format_bounds_description(0, 10, True, True)
        assert "0" in description
        assert "10" in description

    def test_get_parameter_type_from_class_existing(self, validator):
        """Test _get_parameter_type_from_class with existing parameter."""
        param_type = validator._get_parameter_type_from_class("TestClass", "test_param")
        assert param_type == "String"

    def test_get_parameter_type_from_class_missing(self, validator):
        """Test _get_parameter_type_from_class with missing parameter."""
        param_type = validator._get_parameter_type_from_class("TestClass", "missing_param")
        assert param_type is None

    def test_get_parameter_type_from_class_missing_class(self, validator):
        """Test _get_parameter_type_from_class with missing class."""
        param_type = validator._get_parameter_type_from_class("MissingClass", "test_param")
        assert param_type is None

    def test_get_parameter_allow_none_default_false(self, validator):
        """Test _get_parameter_allow_None with default False."""
        allow_none = validator._get_parameter_allow_None("TestClass", "test_param")
        assert allow_none is False

    def test_get_parameter_allow_none_missing_param(self, validator):
        """Test _get_parameter_allow_None with missing parameter."""
        allow_none = validator._get_parameter_allow_None("TestClass", "missing_param")
        assert allow_none is False

    def test_get_parameter_bounds_existing(self, validator):
        """Test _get_parameter_bounds with existing bounds."""
        bounds = validator._get_parameter_bounds("TestClass", "numeric_param")
        assert bounds == (0, 100)

    def test_get_parameter_bounds_missing(self, validator):
        """Test _get_parameter_bounds with missing bounds."""
        bounds = validator._get_parameter_bounds("TestClass", "test_param")
        assert bounds is None

    def test_has_attribute_target_simple_assignment(self, validator):
        """Test _has_attribute_target with simple assignment."""
        code = "x = 5"
        tree = parse(code)
        assignment_node = tree.children[0]

        assert validator._has_attribute_target(assignment_node) is False

    def test_has_attribute_target_attribute_assignment(self, validator):
        """Test _has_attribute_target with attribute assignment."""
        code = "obj.attr = 5"
        tree = parse(code)
        assignment_node = tree.children[0]

        assert validator._has_attribute_target(assignment_node) is True

    def test_create_type_error(self, validator):
        """Test _create_type_error method."""
        code = "x = 5"
        tree = parse(code)
        node = tree.children[0]

        validator._create_type_error(node, "Test error", "test-code")

        assert len(validator.type_errors) == 1
        error = validator.type_errors[0]
        assert error["message"] == "Test error"
        assert error["code"] == "test-code"
        assert error["severity"] == "error"

    def test_check_parameter_default_type_valid(self, validator):
        """Test _check_parameter_default_type with valid default."""
        code = """
class TestClass(param.Parameterized):
    test_param = param.String(default="valid_string")
"""
        tree = parse(code)
        class_nodes = [node for node in walk_tree(tree) if node.type == "classdef"]
        lines = code.split("\n")

        # Should not create any type errors for valid default
        initial_errors = len(validator.type_errors)
        validator._check_class_parameter_defaults(class_nodes[0], lines)
        assert len(validator.type_errors) == initial_errors

    def test_check_parameter_default_type_invalid(self, validator):
        """Test _check_parameter_default_type with invalid default."""
        code = """
class TestClass(param.Parameterized):
    test_param = param.String(default=123)
"""
        tree = parse(code)
        class_nodes = [node for node in walk_tree(tree) if node.type == "classdef"]
        lines = code.split("\n")

        # Should create a type error for invalid default
        initial_errors = len(validator.type_errors)
        validator._check_class_parameter_defaults(class_nodes[0], lines)
        assert len(validator.type_errors) > initial_errors

    def test_check_parameter_types_integration(self, validator):
        """Test check_parameter_types integration method."""
        code = """
import param

class TestClass(param.Parameterized):
    valid_param = param.String(default="valid")
    invalid_param = param.String(default=123)

TestClass().valid_param = "still_valid"
TestClass().invalid_param = 456
"""
        tree = parse(code)
        lines = code.split("\n")

        # Should find type errors for invalid defaults and assignments
        errors = validator.check_parameter_types(tree, lines)
        assert len(errors) > 0

        # Check that errors contain expected codes
        error_codes = [error["code"] for error in errors]
        assert any(
            "type-mismatch" in code or "runtime-type-mismatch" in code for code in error_codes
        )

    def test_validator_state_isolation(self):
        """Test that validator instances maintain their own state."""
        # Create two validators with different param_classes
        validator1_classes = {"Class1": ParameterizedInfo(name="Class1")}
        validator2_classes = {"Class2": ParameterizedInfo(name="Class2")}

        mock_inspector = Mock()
        mock_inspector.analyze_external_class_ast.return_value = None

        validator1 = ParameterValidator(
            param_classes=validator1_classes,
            external_param_classes={},
            imports={},
            is_parameter_assignment_func=lambda x, y: True,
            external_inspector=mock_inspector,
            workspace_root=None,
        )

        validator2 = ParameterValidator(
            param_classes=validator2_classes,
            external_param_classes={},
            imports={},
            is_parameter_assignment_func=lambda x, y: True,
            external_inspector=mock_inspector,
            workspace_root=None,
        )

        # Each validator should only know about its own classes
        assert "Class1" in validator1.param_classes
        assert "Class1" not in validator2.param_classes
        assert "Class2" in validator2.param_classes
        assert "Class2" not in validator1.param_classes

        # Each validator should maintain separate error lists
        validator1._create_type_error(None, "Error 1", "test-code-1")
        validator2._create_type_error(None, "Error 2", "test-code-2")

        assert len(validator1.type_errors) == 1
        assert len(validator2.type_errors) == 1
        assert validator1.type_errors[0]["message"] == "Error 1"
        assert validator2.type_errors[0]["message"] == "Error 2"
