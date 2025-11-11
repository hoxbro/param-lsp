"""Tests for parameter inheritance functionality."""

from __future__ import annotations

from tests.util import get_class


class TestParameterInheritance:
    """Test parameter inheritance in class hierarchies."""

    def test_basic_inheritance(self, analyzer):
        """Test basic parameter inheritance from param.Parameterized."""
        code_py = """\
import param

class P(param.Parameterized):
    pass

class S(P):
    b = param.Boolean(True)

S().b = "a"
"""

        result = analyzer.analyze_file(code_py)

        param_classes = result["param_classes"]
        p_class = get_class(param_classes, "P", raise_if_none=True)

        s_class = get_class(param_classes, "S", raise_if_none=True)

        assert len(p_class.parameters) == 0
        assert list(s_class.parameters.keys()) == ["b"]
        assert s_class.parameters["b"].cls == "Boolean"

        # Should detect type error
        assert len(result["type_errors"]) == 1
        error = result["type_errors"][0]
        assert error["code"] == "runtime-type-mismatch"
        assert "b" in error["message"]

    def test_multi_level_inheritance(self, analyzer):
        """Test inheritance across multiple levels."""
        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(5)

class S(P):
    b = param.Boolean(True)

class T(S):
    name = param.String("test")

# Test type errors
T().x = "not_int"
T().b = "not_bool"
T().name = 123
"""

        result = analyzer.analyze_file(code_py)

        param_classes = result["param_classes"]
        p_class = get_class(param_classes, "P", raise_if_none=True)

        s_class = get_class(param_classes, "S", raise_if_none=True)

        t_class = get_class(param_classes, "T", raise_if_none=True)

        # Check parameter inheritance
        assert list(p_class.parameters.keys()) == ["x"]
        assert set(s_class.parameters.keys()) == {"x", "b"}
        assert set(t_class.parameters.keys()) == {"x", "b", "name"}

        # Check type inheritance
        assert t_class.parameters["x"].cls == "Integer"
        assert t_class.parameters["b"].cls == "Boolean"
        assert t_class.parameters["name"].cls == "String"

        # Should detect 3 type errors
        assert len(result["type_errors"]) == 3
        error_codes = [e["code"] for e in result["type_errors"]]
        assert "runtime-type-mismatch" in error_codes
        assert len([e for e in error_codes if e == "runtime-type-mismatch"]) == 3

    def test_parameter_overriding(self, analyzer):
        """Test parameter overriding in child classes."""
        code_py = """\
import param

class P(param.Parameterized):
    value = param.Integer(1)

class S(P):
    value = param.String("override")  # Override with different type

S().value = 123  # Should error - expecting string now
"""

        result = analyzer.analyze_file(code_py)

        param_classes = result["param_classes"]
        p_class = get_class(param_classes, "P", raise_if_none=True)

        s_class = get_class(param_classes, "S", raise_if_none=True)

        # Child class should override parent parameter type
        assert p_class.parameters["value"].cls == "Integer"
        assert s_class.parameters["value"].cls == "String"

        # Should detect type error based on child class type
        assert len(result["type_errors"]) == 1
        error = result["type_errors"][0]
        assert error["code"] == "runtime-type-mismatch"
        assert "String" in error["message"]

    def test_inheritance_with_bounds(self, analyzer):
        """Test that parameter bounds are inherited correctly."""
        code_py = """\
import param

class P(param.Parameterized):
    x = param.Number(5.0, bounds=(0, 10))

class S(P):
    y = param.Integer(3, bounds=(1, 5))

S().x = 15  # Should violate inherited bounds
S().y = 10  # Should violate local bounds
"""

        result = analyzer.analyze_file(code_py)

        param_classes = result["param_classes"]
        get_class(param_classes, "P", raise_if_none=True)

        s_class = get_class(param_classes, "S", raise_if_none=True)

        # Check bounds inheritance
        assert s_class.parameters["x"].bounds is not None
        assert s_class.parameters["y"].bounds is not None

        # Should detect 2 bounds violations
        bounds_errors = [e for e in result["type_errors"] if e["code"] == "bounds-violation"]
        assert len(bounds_errors) == 2

    def test_inheritance_with_docs(self, analyzer):
        """Test that parameter documentation is inherited correctly."""
        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(5, doc="Parent parameter")

class S(P):
    y = param.String("test", doc="Child parameter")
"""

        result = analyzer.analyze_file(code_py)

        param_classes = result["param_classes"]
        get_class(param_classes, "P", raise_if_none=True)

        s_class = get_class(param_classes, "S", raise_if_none=True)

        # Check doc inheritance
        assert s_class.parameters["x"].doc == "Parent parameter"
        assert s_class.parameters["y"].doc == "Child parameter"

    def test_complex_inheritance_chain(self, analyzer):
        """Test complex inheritance with multiple parents and parameters."""
        code_py = """\
import param

class Base(param.Parameterized):
    base_param = param.String("base")

class A(Base):
    a_param = param.Integer(1)

class B(Base):
    b_param = param.Boolean(True)

class C(A):
    c_param = param.Number(3.14)

# Test assignments
C().base_param = 123      # Should error
C().a_param = "not_int"   # Should error
C().c_param = "not_num"   # Should error
"""

        result = analyzer.analyze_file(code_py)

        # All classes should be recognized with unique keys (name:line_number)
        param_classes = result["param_classes"]
        class_base_names = {name.split(":")[0] for name in param_classes}
        expected_classes = {"Base", "A", "B", "C"}
        assert class_base_names == expected_classes

        # Check parameter inheritance for class C
        c_key = next(k for k in param_classes if k.startswith("C:"))
        c_params = set(param_classes[c_key].parameters.keys())
        assert c_params == {"base_param", "a_param", "c_param"}

        # Check type inheritance
        assert param_classes[c_key].parameters["base_param"].cls == "String"
        assert param_classes[c_key].parameters["a_param"].cls == "Integer"
        assert param_classes[c_key].parameters["c_param"].cls == "Number"

        # Should detect 3 type errors
        assert len(result["type_errors"]) == 3

    def test_inheritance_processing_order(self, analyzer):
        """Test that classes are processed in correct dependency order."""
        code_py = """\
import param

# Define child before parent to test processing order
class S(P):
    b = param.Boolean(True)

class P(param.Parameterized):
    x = param.Integer(5)

S().x = "not_int"  # Should detect error for inherited parameter
"""

        result = analyzer.analyze_file(code_py)

        param_classes = result["param_classes"]
        get_class(param_classes, "P", raise_if_none=True)

        s_class = get_class(param_classes, "S", raise_if_none=True)

        # Child should inherit parent's parameter
        assert "x" in s_class.parameters
        assert s_class.parameters["x"].cls == "Integer"

        # Should detect type error
        assert len(result["type_errors"]) == 1
        assert result["type_errors"][0]["code"] == "runtime-type-mismatch"
