"""Tests for parameter type checking functionality."""

from __future__ import annotations


class TestParameterTypeChecking:
    """Test parameter type checking in class definitions."""

    def test_valid_parameter_types(self, analyzer):
        """Test that valid parameter types don't generate errors."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    string_param = param.String(default="hello")
    int_param = param.Integer(default=5)
    bool_param = param.Boolean(default=True)
    number_param = param.Number(default=1.5)
    list_param = param.List(default=[])
    tuple_param = param.Tuple(default=())
    dict_param = param.Dict(default={})
"""

        result = analyzer.analyze_file(code_py)

        assert "TestClass" in result["param_classes"]
        assert len(result["type_errors"]) == 0

    def test_string_type_mismatch(self, analyzer):
        """Test String parameter with non-string default."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    string_param = param.String(default=123)
"""

        result = analyzer.analyze_file(code_py)

        assert len(result["type_errors"]) == 1
        error = result["type_errors"][0]
        assert error["code"] == "type-mismatch"
        assert "string_param" in error["message"]
        assert "String" in error["message"]
        assert "int" in error["message"]

    def test_integer_type_mismatch(self, analyzer):
        """Test Integer parameter with non-integer default."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    int_param = param.Integer(default="not_int")
"""

        result = analyzer.analyze_file(code_py)

        assert len(result["type_errors"]) == 1
        error = result["type_errors"][0]
        assert error["code"] == "type-mismatch"
        assert "int_param" in error["message"]
        assert "Integer" in error["message"]
        assert "str" in error["message"]

    def test_boolean_type_strict_checking(self, analyzer):
        """Test Boolean parameter strict type checking (should only accept True/False)."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    bool_with_int = param.Boolean(default=1)
    bool_with_zero = param.Boolean(default=0)
    bool_with_string = param.Boolean(default="yes")
"""

        result = analyzer.analyze_file(code_py)

        # Should have 3 errors - Boolean parameters should only accept True/False
        assert len(result["type_errors"]) == 3

        for error in result["type_errors"]:
            assert error["code"] == "boolean-type-mismatch"
            assert "Boolean expects bool" in error["message"]

    def test_boolean_valid_values(self, analyzer):
        """Test Boolean parameter with valid True/False values."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    bool_true = param.Boolean(default=True)
    bool_false = param.Boolean(default=False)
"""

        result = analyzer.analyze_file(code_py)

        assert len(result["type_errors"]) == 0

    def test_number_type_accepts_int_and_float(self, analyzer):
        """Test Number parameter accepts both int and float."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    number_int = param.Number(default=5)
    number_float = param.Number(default=5.5)
"""

        result = analyzer.analyze_file(code_py)

        assert len(result["type_errors"]) == 0

    def test_list_tuple_dict_types(self, analyzer):
        """Test List, Tuple, and Dict parameter types."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    list_param = param.List(default=[1, 2, 3])
    tuple_param = param.Tuple(default=(1, 2, 3))
    dict_param = param.Dict(default={"key": "value"})

    # Type mismatches
    list_wrong = param.List(default="not_list")
    tuple_wrong = param.Tuple(default=123)
    dict_wrong = param.Dict(default=[])
"""

        result = analyzer.analyze_file(code_py)

        # Should have 3 errors for the wrong types
        type_errors = [e for e in result["type_errors"] if e["code"] == "type-mismatch"]
        assert len(type_errors) == 3

    def test_parameter_with_different_import_styles(self, analyzer):
        """Test parameter detection with different import styles."""
        code_py = """\
import param as p
from param import Integer, String

class TestClass(p.Parameterized):
    param1 = p.String(default=123)      # Error
    param2 = String(default="valid")    # Valid
    param3 = Integer(default="invalid") # Error
"""

        result = analyzer.analyze_file(code_py)

        assert "TestClass" in result["param_classes"]
        type_errors = [e for e in result["type_errors"] if e["code"] == "type-mismatch"]
        assert len(type_errors) == 2  # param1 and param3 should error

    def test_non_param_classes_ignored(self, analyzer):
        """Test that non-param classes are ignored."""
        code_py = """\
import param

class RegularClass:
    regular_attr = "not_a_param"

class ParamClass(param.Parameterized):
    param_attr = param.String(default="valid")
"""

        result = analyzer.analyze_file(code_py)

        assert result["param_classes"] == {"ParamClass"}
        assert "RegularClass" not in result["param_classes"]
        assert len(result["type_errors"]) == 0
