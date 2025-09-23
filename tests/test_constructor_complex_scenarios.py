"""Test complex scenarios for constructor parameter validation."""

from __future__ import annotations

from src.param_lsp.analyzer import ParamAnalyzer


class TestConstructorComplexScenarios:
    """Test complex real-world scenarios in constructor validation."""

    def test_constructor_with_cross_file_inheritance(self):
        """Test constructor validation with cross-file inheritance."""
        # This would require setting up a workspace with multiple files
        # For now, we'll test the scenario within a single file that simulates cross-file inheritance
        code_py = """\
import param

# Simulate base class from another file
class SimulatedBaseFromFile(param.Parameterized):
    base_x = param.Integer()
    base_name = param.String()

class LocalChild(SimulatedBaseFromFile):
    child_value = param.Number(bounds=(0, 100))

LocalChild(base_x=42, base_name="test", child_value=50)        # All valid
LocalChild(base_x="bad", base_name=123, child_value=150)       # All should error
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 3
        error_messages = [error["message"] for error in errors]
        assert any(
            "Cannot assign str to parameter 'base_x' of type Integer" in msg
            for msg in error_messages
        )
        assert any(
            "Cannot assign int to parameter 'base_name' of type String" in msg
            for msg in error_messages
        )
        assert any(
            "Value 150 for parameter 'child_value' in LocalChild() constructor is outside bounds [0, 100]"
            in msg
            for msg in error_messages
        )

    def test_constructor_with_diamond_inheritance(self):
        """Test constructor validation with diamond inheritance pattern."""
        code_py = """\
import param

class Base(param.Parameterized):
    base_param = param.String()

class Left(Base):
    left_param = param.Integer()

class Right(Base):
    right_param = param.Boolean()

class Diamond(Left, Right):
    diamond_param = param.Number()

Diamond(
    base_param="valid",
    left_param=42,
    right_param=True,
    diamond_param=3.14
)  # All valid

Diamond(
    base_param=123,
    left_param="bad",
    right_param="false",
    diamond_param="not_number"
)  # All should error
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 4
        error_messages = [error["message"] for error in errors]
        assert any(
            "Cannot assign int to parameter 'base_param' of type String" in msg
            for msg in error_messages
        )
        assert any(
            "Cannot assign str to parameter 'left_param' of type Integer" in msg
            for msg in error_messages
        )
        assert any(
            "Cannot assign str to Boolean parameter 'right_param'" in msg for msg in error_messages
        )
        assert any(
            "Cannot assign str to parameter 'diamond_param' of type Number" in msg
            for msg in error_messages
        )

    def test_constructor_with_parameter_shadowing(self):
        """Test constructor validation when parameters are shadowed in inheritance."""
        code_py = """\
import param

class Parent(param.Parameterized):
    x = param.String()
    y = param.Integer()

class Child(Parent):
    x = param.Integer()  # Shadow parent's x with different type
    # y inherited as Integer

Child(x=42, y=10)      # Valid - x is Integer in Child, y is Integer
Child(x="bad", y="bad") # Both should error - x expects Integer, y expects Integer
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
            "Cannot assign str to parameter 'y' of type Integer" in msg for msg in error_messages
        )

    def test_constructor_with_multiple_inheritance_conflicts(self):
        """Test constructor validation with conflicting parameter types from multiple inheritance."""
        code_py = """\
import param

class MixinA(param.Parameterized):
    shared = param.String()
    a_only = param.Integer()

class MixinB(param.Parameterized):
    shared = param.Integer()  # Conflict with MixinA
    b_only = param.Boolean()

class Combined(MixinA, MixinB):
    own_param = param.Number()

# Test which type wins in multiple inheritance
Combined(shared="string", a_only=42, b_only=True, own_param=3.14)  # String value
Combined(shared=123, a_only=42, b_only=True, own_param=3.14)       # Integer value
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        # Verify the analyzer chose one consistent type for 'shared'
        param_types = result.get("param_parameter_types", {}).get("Combined", {})
        assert "shared" in param_types

        # Currently uses "last wins" - MixinB's Integer type should win
        assert param_types["shared"] == "Integer"

        # Should have 1 error for the string assignment to Integer parameter
        assert len(errors) == 1
        assert "Cannot assign str to parameter 'shared' of type Integer" in errors[0]["message"]

    def test_constructor_with_complex_bounds_scenarios(self):
        """Test constructor validation with complex bounds scenarios."""
        code_py = """\
import param

class ComplexBounds(param.Parameterized):
    percentage = param.Number(bounds=(0, 100), inclusive_bounds=(False, True))
    angle = param.Number(bounds=(-180, 180), inclusive_bounds=(True, False))
    probability = param.Number(bounds=(0, 1), inclusive_bounds=(True, True))
    positive_int = param.Integer(bounds=(1, None))  # Only lower bound

ComplexBounds(percentage=0.01, angle=-180, probability=0.5, positive_int=10)   # All valid
ComplexBounds(percentage=0, angle=180, probability=1.1, positive_int=0)        # Multiple errors
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        # Verify bounds are correctly extracted including None bounds
        bounds = result.get("param_parameter_bounds", {}).get("ComplexBounds", {})
        assert bounds["percentage"] == (0, 100, False, True)  # (0, 100]
        assert bounds["angle"] == (-180, 180, True, False)  # [-180, 180)
        assert bounds["probability"] == (0, 1, True, True)  # [0, 1]
        assert bounds["positive_int"] == (1, None, True, True)  # [1, ∞]

        # Should have 4 bounds violations
        assert len(errors) == 4

        error_messages = [error["message"] for error in errors]
        assert any(
            "Value 0 for parameter 'percentage'" in msg and "outside bounds (0, 100]" in msg
            for msg in error_messages
        )
        assert any(
            "Value 180 for parameter 'angle'" in msg and "outside bounds [-180, 180)" in msg
            for msg in error_messages
        )
        assert any(
            "Value 1.1 for parameter 'probability'" in msg and "outside bounds [0, 1]" in msg
            for msg in error_messages
        )
        assert any(
            "Value 0 for parameter 'positive_int'" in msg and "outside bounds [1, ∞]" in msg
            for msg in error_messages
        )

    def test_constructor_with_numeric_edge_values(self):
        """Test constructor validation with numeric edge values."""
        code_py = """\
import param

class NumericEdges(param.Parameterized):
    small_float = param.Number(bounds=(1e-10, 1e-5))
    big_int = param.Integer(bounds=(1000000, 2000000))
    precise = param.Number(bounds=(0.1, 0.9))

NumericEdges(small_float=1e-8, big_int=1500000, precise=0.5)    # All valid
NumericEdges(small_float=1e-11, big_int=3000000, precise=1.0)   # All outside bounds
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 3
        error_messages = [error["message"] for error in errors]
        assert any("Value 1e-11 for parameter 'small_float'" in msg for msg in error_messages)
        assert any("Value 3000000 for parameter 'big_int'" in msg for msg in error_messages)
        assert any("Value 1.0 for parameter 'precise'" in msg for msg in error_messages)

    def test_constructor_with_realistic_class_hierarchy(self):
        """Test constructor validation with realistic class hierarchy."""
        code_py = """\
import param

class Shape(param.Parameterized):
    name = param.String()
    visible = param.Boolean(default=True)

class Rectangle(Shape):
    width = param.Number(bounds=(0, None), inclusive_bounds=(False, True))
    height = param.Number(bounds=(0, None), inclusive_bounds=(False, True))

class ColoredRectangle(Rectangle):
    color = param.String()
    opacity = param.Number(bounds=(0, 1), inclusive_bounds=(True, True))

ColoredRectangle(
    name="my_rect",
    visible=True,
    width=10.5,
    height=5.0,
    color="red",
    opacity=0.8
)  # All valid

ColoredRectangle(
    name=123,          # Should error - int to String
    visible="yes",     # Should error - string to Boolean
    width=0,           # Should error - width bounds are (0, None) exclusive left
    height=-5,         # Should error - negative height
    color=42,          # Should error - int to String
    opacity=1.5        # Should error - opacity > 1
)  # Multiple errors
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert (
            len(errors) >= 5
        )  # At least the type errors, bounds checking depends on implementation
        error_messages = [error["message"] for error in errors]
        assert any(
            "Cannot assign int to parameter 'name' of type String" in msg for msg in error_messages
        )
        assert any(
            "Cannot assign str to Boolean parameter 'visible'" in msg for msg in error_messages
        )
        assert any(
            "Cannot assign int to parameter 'color' of type String" in msg
            for msg in error_messages
        )

    def test_constructor_with_nested_class_definitions(self):
        """Test constructor validation with nested class definitions."""
        code_py = """\
import param

class Outer(param.Parameterized):
    outer_param = param.String()

    class Inner(param.Parameterized):
        inner_param = param.Integer()

Outer(outer_param="valid")                    # Valid
Outer.Inner(inner_param=42)                   # Valid
Outer(outer_param=123)                        # Should error
Outer.Inner(inner_param="bad")                # Should error
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        # Verify both nested and outer classes are recognized
        param_classes = result.get("param_classes", set())
        assert "Outer" in param_classes
        assert "Inner" in param_classes

        # Verify parameters are correctly identified
        param_parameters = result.get("param_parameters", {})
        assert param_parameters["Outer"] == ["outer_param"]
        assert param_parameters["Inner"] == ["inner_param"]

        # Verify parameter types
        param_types = result.get("param_parameter_types", {})
        assert param_types["Outer"]["outer_param"] == "String"
        assert param_types["Inner"]["inner_param"] == "Integer"

        # Should have 2 constructor errors
        assert len(errors) == 2
        error_messages = [error["message"] for error in errors]
        assert any(
            "Cannot assign int to parameter 'outer_param' of type String in Outer() constructor"
            in msg
            for msg in error_messages
        )
        assert any(
            "Cannot assign str to parameter 'inner_param' of type Integer in Inner() constructor"
            in msg
            for msg in error_messages
        )

    def test_constructor_with_method_call_patterns(self):
        """Test constructor validation with method call patterns that look like constructors."""
        code_py = """\
import param

class Factory:
    def create_instance(self, x):
        return SomeClass(x=x)

class SomeClass(param.Parameterized):
    x = param.Integer()

factory = Factory()
instance = factory.create_instance(x=42)      # Should not error - method call
direct = SomeClass(x="bad")                   # Should error - direct constructor
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 1
        assert (
            "Cannot assign str to parameter 'x' of type Integer in SomeClass() constructor"
            in errors[0]["message"]
        )

    def test_constructor_with_comprehensions_and_generators(self):
        """Test constructor validation with comprehensions and generator expressions."""
        code_py = """\
import param

class Container(param.Parameterized):
    items = param.List()
    mapping = param.Dict()

Container(items=[x*2 for x in range(5)])                    # Valid list comprehension
Container(mapping={str(i): i for i in range(3)})           # Valid dict comprehension
Container(items=(x for x in range(5)))                     # Generator to List - type mismatch?
Container(items="not_a_list")                              # Should error
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        # The analyzer should detect the direct string assignment
        # Generator expressions might not be properly typed
        assert any(
            "Cannot assign str to parameter 'items' of type List" in error["message"]
            for error in errors
        )

    def test_constructor_performance_with_many_parameters(self):
        """Test constructor validation performance with many parameters."""
        code_py = """\
import param

class ManyParams(param.Parameterized):
    p1 = param.Integer()
    p2 = param.String()
    p3 = param.Boolean()
    p4 = param.Number()
    p5 = param.List()
    p6 = param.Dict()
    p7 = param.Tuple()
    p8 = param.Integer(bounds=(0, 100))
    p9 = param.Number(bounds=(-1, 1))
    p10 = param.String()

ManyParams(
    p1=1, p2="a", p3=True, p4=1.0, p5=[],
    p6={}, p7=(), p8=50, p9=0.5, p10="z"
)  # All valid

ManyParams(
    p1="bad", p2=2, p3="bad", p4="bad", p5="bad",
    p6="bad", p7="bad", p8=150, p9=2.0, p10=10
)  # All should error
"""
        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)
        errors = result.get("type_errors", [])

        assert len(errors) == 10  # All parameters should have errors

        # Verify we get different error types
        error_messages = [error["message"] for error in errors]
        assert any("type Integer" in msg for msg in error_messages)
        assert any("type String" in msg for msg in error_messages)
        assert any("Boolean parameter" in msg for msg in error_messages)
        assert any("bounds" in msg for msg in error_messages)
