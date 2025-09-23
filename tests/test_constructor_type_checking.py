"""Test constructor parameter type checking functionality."""

from __future__ import annotations

from src.param_lsp.analyzer import ParamAnalyzer


class TestConstructorTypeChecking:
    """Test constructor parameter type checking."""

    def test_constructor_integer_type_mismatch(self):
        """Test that constructor calls with wrong integer types are detected."""
        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer()

P(x="A")  # Should trigger error
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 1
        assert (
            "Cannot assign str to parameter 'x' of type Integer in P() constructor"
            in errors[0]["message"]
        )
        assert errors[0]["code"] == "constructor-type-mismatch"
        assert errors[0]["line"] == 5  # 0-based line number

    def test_constructor_boolean_type_mismatch(self):
        """Test that constructor calls with wrong boolean types are detected."""
        code_py = """\
import param

class P(param.Parameterized):
    flag = param.Boolean()

P(flag="true")  # Should trigger error
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 1
        assert (
            "Cannot assign str to Boolean parameter 'flag' in P() constructor"
            in errors[0]["message"]
        )
        assert errors[0]["code"] == "constructor-boolean-type-mismatch"

    def test_constructor_bounds_violation(self):
        """Test that constructor calls with values outside bounds are detected."""
        code_py = """\
import param

class P(param.Parameterized):
    y = param.Number(bounds=(0, 10))

P(y=15)  # Should trigger bounds error
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 1
        assert (
            "Value 15 for parameter 'y' in P() constructor is outside bounds [0, 10]"
            in errors[0]["message"]
        )
        assert errors[0]["code"] == "constructor-bounds-violation"

    def test_constructor_valid_assignments(self):
        """Test that valid constructor calls don't trigger errors."""
        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer()
    y = param.Number(bounds=(0, 10))
    flag = param.Boolean()
    name = param.String()

P(x=5)                           # Valid integer
P(y=5.5)                        # Valid number within bounds
P(flag=True)                    # Valid boolean
P(name="test")                  # Valid string
P(x=5, y=2.5, flag=False, name="valid")  # All valid
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 0

    def test_constructor_multiple_errors(self):
        """Test that multiple constructor errors are detected."""
        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer()
    y = param.Number(bounds=(0, 10))
    flag = param.Boolean()

P(x="A", y=15, flag="true")  # Should trigger 3 errors
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 3

        # Check that all three expected errors are present
        error_messages = [error["message"] for error in errors]
        assert any(
            "Cannot assign str to parameter 'x' of type Integer" in msg for msg in error_messages
        )
        assert any(
            "Value 15 for parameter 'y' in P() constructor is outside bounds [0, 10]" in msg
            for msg in error_messages
        )
        assert any(
            "Cannot assign str to Boolean parameter 'flag'" in msg for msg in error_messages
        )

    def test_constructor_inherited_parameters(self):
        """Test that constructor type checking works with inherited parameters."""
        code_py = """\
import param

class Base(param.Parameterized):
    x = param.Integer()

class Child(Base):
    y = param.String()

Child(x="A", y=123)  # Should trigger 2 errors
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 2

        error_messages = [error["message"] for error in errors]
        assert any(
            "Cannot assign str to parameter 'x' of type Integer" in msg for msg in error_messages
        )
        assert any(
            "Cannot assign int to parameter 'y' of type String" in msg for msg in error_messages
        )

    def test_constructor_unknown_parameters_ignored(self):
        """Test that unknown parameters in constructor don't cause issues."""
        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer()

P(x=5, unknown_param="value")  # Should only check known parameters
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 0

    def test_constructor_non_param_classes_ignored(self):
        """Test that non-param classes are ignored."""
        code_py = """\
import param

class NonParamClass:
    def __init__(self, x):
        self.x = x

class P(param.Parameterized):
    x = param.Integer()

NonParamClass(x="anything")  # Should be ignored
P(x=5)                       # Valid param class call
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 0

    def test_constructor_inclusive_bounds_checking(self):
        """Test that inclusive bounds are properly checked in constructors."""
        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(bounds=(0, 10), inclusive_bounds=(False, True))

P(x=0)   # Should trigger error (left exclusive)
P(x=10)  # Should be valid (right inclusive)
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 1
        assert (
            "Value 0 for parameter 'x' in P() constructor is outside bounds (0, 10]"
            in errors[0]["message"]
        )
        assert errors[0]["code"] == "constructor-bounds-violation"

    def test_constructor_number_type_accepts_int_and_float(self):
        """Test that Number parameters accept both int and float in constructors."""
        code_py = """\
import param

class P(param.Parameterized):
    value = param.Number()

P(value=5)     # Should be valid (int)
P(value=5.5)   # Should be valid (float)
P(value="5")   # Should trigger error (string)
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 1
        assert "Cannot assign str to parameter 'value' of type Number" in errors[0]["message"]

    def test_constructor_list_tuple_dict_types(self):
        """Test that collection types work correctly in constructors."""
        code_py = """\
import param

class P(param.Parameterized):
    items = param.List()
    coords = param.Tuple()
    mapping = param.Dict()

P(items=[1, 2, 3])        # Valid list
P(coords=(1, 2))          # Valid tuple
P(mapping={"a": 1})       # Valid dict
P(items="not a list")     # Should trigger error
P(coords=123)             # Should trigger error
P(mapping=[1, 2, 3])      # Should trigger error
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 3
        error_messages = [error["message"] for error in errors]
        assert any(
            "Cannot assign str to parameter 'items' of type List" in msg for msg in error_messages
        )
        assert any(
            "Cannot assign int to parameter 'coords' of type Tuple" in msg
            for msg in error_messages
        )
        assert any(
            "Cannot assign list to parameter 'mapping' of type Dict" in msg
            for msg in error_messages
        )

    def test_constructor_with_different_import_styles(self):
        """Test constructor checking with different import styles."""
        code_py = """\
import param as p

class P(p.Parameterized):
    x = p.Integer()

P(x="A")  # Should trigger error
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 1
        assert "Cannot assign str to parameter 'x' of type Integer" in errors[0]["message"]

    def test_constructor_from_import_style(self):
        """Test constructor checking with 'from param import' style."""
        code_py = """
from param import Parameterized, Integer, String

class P(Parameterized):
    x = Integer()
    name = String()

P(x="A", name=123)  # Should trigger 2 errors
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 2
        error_messages = [error["message"] for error in errors]
        assert any(
            "Cannot assign str to parameter 'x' of type Integer" in msg for msg in error_messages
        )
        assert any(
            "Cannot assign int to parameter 'name' of type String" in msg for msg in error_messages
        )

    def test_constructor_negative_numbers_and_bounds(self):
        """Test constructor with negative numbers and bounds."""
        code_py = """\
import param

class P(param.Parameterized):
    temp = param.Number(bounds=(-10, 10))
    count = param.Integer(bounds=(0, 100))

P(temp=-5)    # Valid negative within bounds
P(temp=-15)   # Should trigger bounds error
P(count=-1)   # Should trigger bounds error
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 2
        error_messages = [error["message"] for error in errors]
        assert any(
            "Value -15 for parameter 'temp' in P() constructor is outside bounds [-10, 10]" in msg
            for msg in error_messages
        )
        assert any(
            "Value -1 for parameter 'count' in P() constructor is outside bounds [0, 100]" in msg
            for msg in error_messages
        )

    def test_constructor_complex_inheritance_chain(self):
        """Test constructor checking with complex inheritance chains."""
        code_py = """\
import param

class Base(param.Parameterized):
    base_param = param.String()

class Middle(Base):
    middle_param = param.Integer()

class Child(Middle):
    child_param = param.Boolean()

Child(base_param=123, middle_param="abc", child_param="true")  # All should error
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 3
        error_messages = [error["message"] for error in errors]
        assert any(
            "Cannot assign int to parameter 'base_param' of type String" in msg
            for msg in error_messages
        )
        assert any(
            "Cannot assign str to parameter 'middle_param' of type Integer" in msg
            for msg in error_messages
        )
        assert any(
            "Cannot assign str to Boolean parameter 'child_param'" in msg for msg in error_messages
        )

    def test_constructor_mixed_valid_invalid_parameters(self):
        """Test constructor with mix of valid and invalid parameters."""
        code_py = """\
import param

class P(param.Parameterized):
    a = param.Integer()
    b = param.String()
    c = param.Boolean()
    d = param.Number(bounds=(0, 10))

P(a=5, b="valid", c="invalid", d=15)  # 2 should error, 2 should be valid
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 2
        error_messages = [error["message"] for error in errors]
        assert any("Cannot assign str to Boolean parameter 'c'" in msg for msg in error_messages)
        assert any(
            "Value 15 for parameter 'd' in P() constructor is outside bounds [0, 10]" in msg
            for msg in error_messages
        )

    def test_constructor_parameter_overriding_in_inheritance(self):
        """Test constructor checking when child class overrides parent parameters."""
        code_py = """\
import param

class Parent(param.Parameterized):
    x = param.String()

class Child(Parent):
    x = param.Integer()  # Override with different type

Child(x="should_error")  # Should error because x is now Integer in Child
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 1
        assert "Cannot assign str to parameter 'x' of type Integer" in errors[0]["message"]

    def test_constructor_with_None_values(self):
        """Test constructor with None values and allow_None parameter."""
        code_py = """\
import param

class P(param.Parameterized):
    required = param.Integer()
    optional = param.Integer(allow_None=True)

P(required=None)   # Should error - None not allowed
P(optional=None)   # Should NOT error - allow_None=True
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        # With allow_None implemented, we should get:
        # - 1 error for 'required' (None not allowed)
        # - 0 errors for 'optional' (allow_None=True should permit None)
        assert len(errors) == 1

        error_messages = [error["message"] for error in errors]
        assert any(
            "Cannot assign NoneType to parameter 'required' of type Integer" in msg
            for msg in error_messages
        )
        # No error should be generated for 'optional' since allow_None=True

    def test_constructor_exclusive_bounds_both_sides(self):
        """Test constructor with exclusive bounds on both sides."""
        code_py = """\
import param

class P(param.Parameterized):
    x = param.Number(bounds=(0, 10), inclusive_bounds=(False, False))

P(x=0)    # Should error (left exclusive)
P(x=10)   # Should error (right exclusive)
P(x=5)    # Should be valid
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 2
        error_messages = [error["message"] for error in errors]
        assert any(
            "Value 0 for parameter 'x' in P() constructor is outside bounds (0, 10)" in msg
            for msg in error_messages
        )
        assert any(
            "Value 10 for parameter 'x' in P() constructor is outside bounds (0, 10)" in msg
            for msg in error_messages
        )

    def test_constructor_float_vs_integer_bounds(self):
        """Test constructor bounds checking with float vs integer boundaries."""
        code_py = """\
import param

class P(param.Parameterized):
    int_param = param.Integer(bounds=(1, 10))
    num_param = param.Number(bounds=(1.5, 9.5))

P(int_param=1.5)    # Should error - float to Integer parameter
P(num_param=1.2)    # Should error - outside bounds
P(num_param=2.0)    # Should be valid
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 2
        error_messages = [error["message"] for error in errors]
        assert any(
            "Cannot assign float to parameter 'int_param' of type Integer" in msg
            for msg in error_messages
        )
        assert any(
            "Value 1.2 for parameter 'num_param' in P() constructor is outside bounds [1.5, 9.5]"
            in msg
            for msg in error_messages
        )
