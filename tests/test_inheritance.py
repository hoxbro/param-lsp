"""Tests for parameter inheritance functionality."""

from __future__ import annotations


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

        assert "P" in result["param_classes"]
        assert "S" in result["param_classes"]
        assert result["param_parameters"]["P"] == []
        assert result["param_parameters"]["S"] == ["b"]
        assert result["param_parameter_types"]["S"]["b"] == "Boolean"

        # Should detect type error
        assert len(result["type_errors"]) == 1
        error = result["type_errors"][0]
        assert error["code"] == "runtime-boolean-type-mismatch"
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

        assert "P" in result["param_classes"]
        assert "S" in result["param_classes"]
        assert "T" in result["param_classes"]

        # Check parameter inheritance
        assert result["param_parameters"]["P"] == ["x"]
        assert set(result["param_parameters"]["S"]) == {"x", "b"}
        assert set(result["param_parameters"]["T"]) == {"x", "b", "name"}

        # Check type inheritance
        assert result["param_parameter_types"]["T"]["x"] == "Integer"
        assert result["param_parameter_types"]["T"]["b"] == "Boolean"
        assert result["param_parameter_types"]["T"]["name"] == "String"

        # Should detect 3 type errors
        assert len(result["type_errors"]) == 3
        error_codes = [e["code"] for e in result["type_errors"]]
        assert "runtime-type-mismatch" in error_codes
        assert "runtime-boolean-type-mismatch" in error_codes

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

        assert "P" in result["param_classes"]
        assert "S" in result["param_classes"]

        # Child class should override parent parameter type
        assert result["param_parameter_types"]["P"]["value"] == "Integer"
        assert result["param_parameter_types"]["S"]["value"] == "String"

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

        assert "P" in result["param_classes"]
        assert "S" in result["param_classes"]

        # Check bounds inheritance
        assert "x" in result["param_parameter_bounds"]["S"]
        assert "y" in result["param_parameter_bounds"]["S"]

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

        assert "P" in result["param_classes"]
        assert "S" in result["param_classes"]

        # Check doc inheritance
        assert result["param_parameter_docs"]["S"]["x"] == "Parent parameter"
        assert result["param_parameter_docs"]["S"]["y"] == "Child parameter"

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

        # All classes should be recognized
        expected_classes = {"Base", "A", "B", "C"}
        assert result["param_classes"] == expected_classes

        # Check parameter inheritance for class C
        c_params = set(result["param_parameters"]["C"])
        assert c_params == {"base_param", "a_param", "c_param"}

        # Check type inheritance
        assert result["param_parameter_types"]["C"]["base_param"] == "String"
        assert result["param_parameter_types"]["C"]["a_param"] == "Integer"
        assert result["param_parameter_types"]["C"]["c_param"] == "Number"

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

        assert "P" in result["param_classes"]
        assert "S" in result["param_classes"]

        # Child should inherit parent's parameter
        assert "x" in result["param_parameters"]["S"]
        assert result["param_parameter_types"]["S"]["x"] == "Integer"

        # Should detect type error
        assert len(result["type_errors"]) == 1
        assert result["type_errors"][0]["code"] == "runtime-type-mismatch"
