"""Test edge cases for constructor parameter validation."""

from __future__ import annotations

from src.param_lsp.analyzer import ParamAnalyzer


class TestConstructorEdgeCases:
    """Test edge cases and unusual scenarios in constructor validation."""

    def test_constructor_with_nested_calls(self):
        """Test constructor calls with nested function calls as arguments."""
        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer()
    name = param.String()

def get_string():
    return "valid"

def get_number():
    return 42

P(x=get_number(), name=get_string())  # Should not error - can't infer return types
P(x="direct_string")                  # Should error - direct string literal
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        # Should only error on the direct string literal, not the function calls
        assert len(errors) == 1
        assert "Cannot assign str to parameter 'x' of type Integer" in errors[0]["message"]

    def test_constructor_with_variables(self):
        """Test constructor calls with variables as arguments."""
        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer()

my_var = "string"
P(x=my_var)  # Should not error - can't infer variable types at static analysis time
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        # Should not error since we can't infer variable types
        assert len(errors) == 0

    def test_constructor_with_expressions(self):
        """Test constructor calls with arithmetic expressions."""
        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer()
    y = param.Number()

P(x=5 + 3)      # Should not error - arithmetic expression
P(x=1.5 + 2.5)  # Should not error - can't determine result type statically
P(y=10 / 2)     # Should not error - arithmetic expression
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        # Should not error since we don't evaluate expressions
        assert len(errors) == 0

    def test_constructor_with_class_attributes(self):
        """Test constructor calls using class attributes."""
        code_py = """\
import param

class Constants:
    VALUE = 42
    NAME = "test"

class P(param.Parameterized):
    x = param.Integer()
    name = param.String()

P(x=Constants.VALUE, name=Constants.NAME)  # Should not error - can't infer attribute types
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        # Should not error since we don't resolve class attributes
        assert len(errors) == 0

    def test_constructor_with_kwargs_dict(self):
        """Test constructor calls with **kwargs expansion."""
        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer()
    name = param.String()

params = {"x": 42, "name": "test"}
P(**params)  # Should not error - can't analyze **kwargs
P(x=5, **params)  # Should not error - can't analyze **kwargs
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        # Should not error since we skip **kwargs
        assert len(errors) == 0

    def test_constructor_chained_calls(self):
        """Test chained constructor calls."""
        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer()

class Factory:
    def create_p(self):
        return P(x=42)

factory = Factory()
p1 = factory.create_p()  # Should not error
p2 = P(x="error")        # Should error
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 1
        assert "Cannot assign str to parameter 'x' of type Integer" in errors[0]["message"]

    def test_constructor_with_list_comprehension(self):
        """Test constructor with list comprehension arguments."""
        code_py = """\
import param

class P(param.Parameterized):
    items = param.List()

P(items=[x for x in range(10)])  # Should not error - list comprehension creates list
P(items="not a list")            # Should error - direct string
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 1
        assert "Cannot assign str to parameter 'items' of type List" in errors[0]["message"]

    def test_constructor_with_complex_literals(self):
        """Test constructor with complex literal values."""
        code_py = """\
import param

class P(param.Parameterized):
    data = param.Dict()
    coords = param.Tuple()
    items = param.List()

P(data={"key": {"nested": [1, 2, 3]}})     # Valid nested dict
P(coords=((1, 2), (3, 4)))                 # Valid nested tuple
P(items=[[1, 2], [3, 4]])                  # Valid nested list
P(data=[1, 2, 3])                          # Should error - list to Dict
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 1
        assert "Cannot assign list to parameter 'data' of type Dict" in errors[0]["message"]

    def test_constructor_with_empty_collections(self):
        """Test constructor with empty collection literals."""
        code_py = """\
import param

class P(param.Parameterized):
    items = param.List()
    mapping = param.Dict()
    coords = param.Tuple()

P(items=[])       # Valid empty list
P(mapping={})     # Valid empty dict
P(coords=())      # Valid empty tuple
P(items={})       # Should error - dict to List
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 1
        assert "Cannot assign dict to parameter 'items' of type List" in errors[0]["message"]

    def test_constructor_with_multiple_classes_same_param_name(self):
        """Test constructor validation with multiple classes having same parameter names."""
        code_py = """\
import param

class ClassA(param.Parameterized):
    value = param.Integer()

class ClassB(param.Parameterized):
    value = param.String()

ClassA(value=42)     # Valid integer for ClassA
ClassB(value="test") # Valid string for ClassB
ClassA(value="bad")  # Should error - string to Integer in ClassA
ClassB(value=123)    # Should error - integer to String in ClassB
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 2
        error_messages = [error["message"] for error in errors]
        assert any(
            "Cannot assign str to parameter 'value' of type Integer in ClassA() constructor" in msg
            for msg in error_messages
        )
        assert any(
            "Cannot assign int to parameter 'value' of type String in ClassB() constructor" in msg
            for msg in error_messages
        )

    def test_constructor_with_scientific_notation(self):
        """Test constructor with scientific notation numbers."""
        code_py = """\
import param

class P(param.Parameterized):
    small = param.Number(bounds=(0, 1))
    large = param.Number()

P(small=1e-6)    # Valid scientific notation within bounds
P(large=1e10)    # Valid large scientific notation
P(small=1e3)     # Should error - outside bounds (1000 > 1)
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 1
        assert (
            "Value 1000.0 for parameter 'small' in P() constructor is outside bounds [0, 1]"
            in errors[0]["message"]
        )

    def test_constructor_with_boolean_edge_cases(self):
        """Test constructor with various boolean-like values."""
        code_py = """\
import param

class P(param.Parameterized):
    flag = param.Boolean()

P(flag=True)      # Valid boolean
P(flag=False)     # Valid boolean
P(flag=1)         # Should error - integer not boolean
P(flag=0)         # Should error - integer not boolean
P(flag="True")    # Should error - string not boolean
P(flag="false")   # Should error - string not boolean
P(flag=None)      # Should error - None not boolean (unless allow_None=True)
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 5  # All non-boolean values should error
        error_messages = [error["message"] for error in errors]
        assert (
            sum("Cannot assign int to Boolean parameter 'flag'" in msg for msg in error_messages)
            == 2
        )
        assert (
            sum("Cannot assign str to Boolean parameter 'flag'" in msg for msg in error_messages)
            == 2
        )
        assert (
            sum(
                "Cannot assign NoneType to Boolean parameter 'flag'" in msg
                for msg in error_messages
            )
            == 1
        )

    def test_constructor_zero_and_negative_zero(self):
        """Test constructor with zero and negative zero edge cases."""
        code_py = """\
import param

class P(param.Parameterized):
    positive = param.Number(bounds=(0, 10), inclusive_bounds=(False, True))
    non_negative = param.Number(bounds=(0, 10), inclusive_bounds=(True, True))

P(positive=0)      # Should error - left exclusive
P(positive=-0.0)   # Should error - left exclusive (negative zero is still zero)
P(non_negative=0)  # Valid - left inclusive
P(non_negative=-0.0) # Valid - left inclusive
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 2
        error_messages = [error["message"] for error in errors]
        assert (
            sum(
                "Value 0 for parameter 'positive' in P() constructor is outside bounds (0, 10]"
                in msg
                for msg in error_messages
            )
            == 1
        )
        assert (
            sum(
                "Value -0.0 for parameter 'positive' in P() constructor is outside bounds (0, 10]"
                in msg
                for msg in error_messages
            )
            == 1
        )
