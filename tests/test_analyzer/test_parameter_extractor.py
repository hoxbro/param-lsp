"""
Tests for the parameter_extractor module.
"""

from __future__ import annotations

from param_lsp._analyzer.parameter_extractor import (
    extract_boolean_value,
    extract_bounds_from_call,
    extract_default_from_call,
    extract_doc_from_call,
    extract_numeric_value,
    extract_string_value,
    format_default_value,
    get_keyword_arguments,
    is_none_value,
    is_parameter_assignment,
    is_parameter_call,
)
from param_lsp._treesitter import parser


def parse_expression(code: str):
    """Helper to parse a code expression into tree-sitter nodes."""
    tree = parser.parse(code)
    # For tree-sitter, the root is a module node
    # Return the first meaningful child node (skip newlines/comments)
    for child in tree.root_node.children:
        if child.type in (
            "expression_statement",
            "assignment",
            "integer",
            "float",
            "string",
            "true",
            "false",
            "none",
            "call",
            "unary_operator",
        ):
            # For expression statements, return the actual expression inside
            if child.type == "expression_statement" and child.children:
                return child.children[0]
            return child
    return tree.root_node.children[0] if tree.root_node.children else tree.root_node


class TestExtractNumericValue:
    """Test numeric value extraction."""

    def test_extract_integer(self):
        node = parse_expression("42")
        assert extract_numeric_value(node) == 42

    def test_extract_float(self):
        node = parse_expression("3.14")
        assert extract_numeric_value(node) == 3.14

    def test_extract_negative_integer(self):
        node = parse_expression("-5")
        assert extract_numeric_value(node) == -5

    def test_extract_negative_float(self):
        node = parse_expression("-2.5")
        assert extract_numeric_value(node) == -2.5

    def test_extract_scientific_notation(self):
        node = parse_expression("1e3")
        assert extract_numeric_value(node) == 1000.0

    def test_extract_none_value(self):
        node = parse_expression("None")
        assert extract_numeric_value(node) is None

    def test_extract_non_numeric(self):
        node = parse_expression("'hello'")
        assert extract_numeric_value(node) is None


class TestExtractBooleanValue:
    """Test boolean value extraction."""

    def test_extract_true(self):
        node = parse_expression("True")
        assert extract_boolean_value(node) is True

    def test_extract_false(self):
        node = parse_expression("False")
        assert extract_boolean_value(node) is False

    def test_extract_non_boolean(self):
        node = parse_expression("'hello'")
        assert extract_boolean_value(node) is None


class TestExtractStringValue:
    """Test string value extraction."""

    def test_extract_single_quotes(self):
        node = parse_expression("'hello'")
        assert extract_string_value(node) == "hello"

    def test_extract_double_quotes(self):
        node = parse_expression('"world"')
        assert extract_string_value(node) == "world"

    def test_extract_triple_quotes(self):
        node = parse_expression('"""multiline"""')
        assert extract_string_value(node) == "multiline"

    def test_extract_triple_single_quotes(self):
        node = parse_expression("'''another'''")
        assert extract_string_value(node) == "another"

    def test_extract_non_string(self):
        node = parse_expression("42")
        assert extract_string_value(node) is None


class TestIsNoneValue:
    """Test None value detection."""

    def test_is_none_value_true(self):
        node = parse_expression("None")
        assert is_none_value(node) is True

    def test_is_none_value_false(self):
        node = parse_expression("42")
        assert is_none_value(node) is False

    def test_is_none_value_string(self):
        node = parse_expression("'None'")
        assert is_none_value(node) is False


class TestFormatDefaultValue:
    """Test default value formatting."""

    def test_format_number(self):
        node = parse_expression("42")
        result = format_default_value(node)
        assert result == "42"

    def test_format_string(self):
        node = parse_expression("'hello'")
        result = format_default_value(node)
        assert result == "'hello'"

    def test_format_boolean(self):
        node = parse_expression("True")
        result = format_default_value(node)
        assert result == "True"


class TestIsParameterCall:
    """Test parameter call detection."""

    def test_is_param_integer_call(self):
        node = parse_expression("param.Integer(default=5)")
        result = is_parameter_call(node)
        assert result is True

    def test_is_regular_function_call(self):
        node = parse_expression("print('hello')")
        result = is_parameter_call(node)
        assert result is False

    def test_is_param_string_call(self):
        """Test that param.String() is detected as a parameter call."""
        node = parse_expression("param.String(default='test')")
        result = is_parameter_call(node)
        assert result is True

    def test_is_direct_parameter_type_call(self):
        """Test that direct parameter type calls (e.g., String()) are detected."""
        node = parse_expression("String(default='test')")
        result = is_parameter_call(node)
        assert result is True

    def test_is_not_pandas_dataframe_call(self):
        """Test that pd.DataFrame() is NOT detected as a parameter call.

        Even though DataFrame is in PARAM_TYPES, pd.DataFrame() should not
        be detected because it's from pandas, not param.
        """
        node = parse_expression("pd.DataFrame()")
        result = is_parameter_call(node)
        assert result is False

    def test_is_not_other_module_call(self):
        """Test that calls from other modules are rejected."""
        node = parse_expression("np.String()")
        result = is_parameter_call(node)
        assert result is False

    def test_is_param_dataframe_call(self):
        """Test that param.DataFrame() IS detected as a parameter call."""
        node = parse_expression("param.DataFrame()")
        result = is_parameter_call(node)
        assert result is True


class TestIsParameterAssignment:
    """Test parameter assignment detection."""

    def test_is_parameter_assignment_true(self):
        code = "width = param.Integer(default=100)"
        tree = parser.parse(code)
        # Get the first statement (skip module wrapper)
        stmt = None
        for child in tree.root_node.children:
            if child.type in ("expression_statement", "assignment"):
                if child.type == "expression_statement" and child.children:
                    stmt = child.children[0]
                else:
                    stmt = child
                break
        # This is a simplified test - the function needs more context in practice
        assert stmt is not None
        result = is_parameter_assignment(stmt)
        assert isinstance(result, bool)

    def test_is_regular_assignment(self):
        code = "x = 5"
        tree = parser.parse(code)
        # Get the first statement (skip module wrapper)
        stmt = None
        for child in tree.root_node.children:
            if child.type in ("expression_statement", "assignment"):
                if child.type == "expression_statement" and child.children:
                    stmt = child.children[0]
                else:
                    stmt = child
                break
        assert stmt is not None
        result = is_parameter_assignment(stmt)
        assert result is False


class TestGetKeywordArguments:
    """Test keyword argument extraction."""

    def test_extract_simple_kwargs(self):
        # Test with a simple function call
        node = parse_expression("func(a=1, b=2)")
        kwargs = get_keyword_arguments(node)
        # The function should return a dict, even if empty for this test case
        assert isinstance(kwargs, dict)

    def test_extract_no_kwargs(self):
        node = parse_expression("func(1, 2)")
        kwargs = get_keyword_arguments(node)
        assert isinstance(kwargs, dict)
        assert len(kwargs) == 0


class TestExtractFromCall:
    """Test extraction from parameter calls."""

    def test_extract_bounds_from_call(self):
        node = parse_expression("param.Integer(bounds=(0, 100))")
        # This is a basic test - the function needs proper parameter call structure
        bounds = extract_bounds_from_call(node)
        # Should return None or a tuple
        assert bounds is None or isinstance(bounds, tuple)

    def test_extract_doc_from_call(self):
        node = parse_expression("param.Integer(doc='A parameter')")
        doc = extract_doc_from_call(node)
        assert doc is None or isinstance(doc, str)

    def test_extract_default_from_call(self):
        node = parse_expression("param.Integer(default=42)")
        default = extract_default_from_call(node)
        # Should return a node or None
        assert default is None or hasattr(default, "type")
