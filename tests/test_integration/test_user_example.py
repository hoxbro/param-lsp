"""Test for the user's specific cross-file inheritance example."""

from __future__ import annotations

from param_lsp.analyzer import ParamAnalyzer


class TestUserExample:
    """Test the exact user example that was requested."""

    def test_user_example_cross_file_inheritance(self, tmp_path):
        """Test the exact pattern the user provided: class P(param.Parameterized): ... -> class S(P): -> S().b = "a" """

        # Create parent_class.py with P class
        parent_file = tmp_path / "parent_class.py"
        parent_file.write_text("""
import param

class P(param.Parameterized):
    x = param.Integer(10, doc="Example integer parameter")
""")

        # Create the user's exact example structure
        example_file = tmp_path / "example.py"
        example_file.write_text("""
from __future__ import annotations

import param

from parent_class import P

# class P(param.Parameterized):
#     pass


class S(P): ...
    # x = param.Intg


S().x = "a"  # This should now trigger a type error!
""")

        analyzer = ParamAnalyzer(workspace_root=str(tmp_path))

        with open(example_file) as f:
            content = f.read()

        result = analyzer.analyze_file(content, str(example_file))

        # Verify S is detected as a param class
        assert "S" in result["param_classes"], "Class S should be detected as a param class"
        s_class = result["param_classes"]["S"]

        # Verify S inherits parameters from P
        assert "x" in s_class.parameters, "S should inherit parameter 'x' from P"
        assert s_class.parameters["x"].cls == "Integer", "Parameter 'x' should be of type Integer"

        # Verify the type error is detected
        assert len(result["type_errors"]) == 1, "Should detect exactly one type error"
        error = result["type_errors"][0]
        assert error["line"] == 15, "Error should be on line 16 (0-indexed line 15)"
        assert "Cannot assign str to parameter 'x' of type Integer" in error["message"], (
            "Should detect string assignment to Integer parameter"
        )
        assert error["code"] == "runtime-type-mismatch", "Should be a runtime type mismatch error"

    def test_original_pattern_class_p_class_s_inheritance(self, tmp_path):
        """Test the original pattern: class P(param.Parameterized): ... class S(P): b = param.Boolean(True) S().b = "a" """

        # Create parent module
        parent_file = tmp_path / "parent_module.py"
        parent_file.write_text("""
import param

class P(param.Parameterized):
    pass
""")

        # Create child module with the exact pattern from the original question
        child_file = tmp_path / "child_module.py"
        child_file.write_text("""
import param
from parent_module import P

class S(P):
    b = param.Boolean(True)

S().b = "a"
""")

        analyzer = ParamAnalyzer(workspace_root=str(tmp_path))

        with open(child_file) as f:
            content = f.read()

        result = analyzer.analyze_file(content, str(child_file))

        # Verify the inheritance works
        assert "S" in result["param_classes"], "Class S should be detected as a param class"
        s_class = result["param_classes"]["S"]
        assert "b" in s_class.parameters, "S should have parameter 'b'"
        assert s_class.parameters["b"].cls == "Boolean", "Parameter 'b' should be Boolean type"

        # Verify the type error is detected
        assert len(result["type_errors"]) == 1, "Should detect exactly one type error"
        error = result["type_errors"][0]
        assert "Cannot assign str to Boolean parameter 'b'" in error["message"], (
            "Should detect string assignment to Boolean parameter"
        )
        assert error["code"] == "runtime-boolean-type-mismatch", (
            "Should be a boolean type mismatch error"
        )

    def test_complex_inheritance_chain_across_files(self, tmp_path):
        """Test inheritance chain across multiple files to ensure robustness."""

        # Create base.py
        base_file = tmp_path / "base.py"
        base_file.write_text("""
import param

class Base(param.Parameterized):
    base_str = param.String("base")
""")

        # Create middle.py that imports from base
        middle_file = tmp_path / "middle.py"
        middle_file.write_text("""
import param
from base import Base

class Middle(Base):
    middle_int = param.Integer(42)
""")

        # Create final.py that imports from middle
        final_file = tmp_path / "final.py"
        final_file.write_text("""
import param
from middle import Middle

class Final(Middle):
    final_bool = param.Boolean(True)

# Test all inherited parameters
obj = Final()
obj.base_str = 123      # Error: String parameter
obj.middle_int = "abc"  # Error: Integer parameter
obj.final_bool = "xyz"  # Error: Boolean parameter
""")

        analyzer = ParamAnalyzer(workspace_root=str(tmp_path))

        with open(final_file) as f:
            content = f.read()

        result = analyzer.analyze_file(content, str(final_file))

        # Verify complete inheritance chain
        assert "Final" in result["param_classes"], (
            "Class Final should be detected as a param class"
        )
        final_class = result["param_classes"]["Final"]

        # Check all inherited parameters
        expected_params = {"base_str", "middle_int", "final_bool"}
        actual_params = set(final_class.parameters.keys())
        assert actual_params == expected_params, (
            f"Final should inherit all parameters: expected {expected_params}, got {actual_params}"
        )

        # Check parameter types
        assert final_class.parameters["base_str"].cls == "String", "base_str should be String type"
        assert final_class.parameters["middle_int"].cls == "Integer", (
            "middle_int should be Integer type"
        )
        assert final_class.parameters["final_bool"].cls == "Boolean", (
            "final_bool should be Boolean type"
        )

        # Verify all type errors are detected
        assert len(result["type_errors"]) == 3, "Should detect exactly three type errors"

        error_lines = [e["line"] for e in result["type_errors"]]
        assert 9 in error_lines, "Should detect error on line with base_str assignment"
        assert 10 in error_lines, "Should detect error on line with middle_int assignment"
        assert 11 in error_lines, "Should detect error on line with final_bool assignment"

    def test_import_styles_compatibility(self, tmp_path):
        """Test different import styles work with inheritance."""

        # Create module with multiple classes
        classes_file = tmp_path / "classes.py"
        classes_file.write_text("""
import param

class A(param.Parameterized):
    a_param = param.String("a")

class B(param.Parameterized):
    b_param = param.Integer(1)
""")

        # Test different import styles
        test_file = tmp_path / "test_imports.py"
        test_file.write_text("""
import param
from classes import A, B

class C(A):
    c_param = param.Boolean(True)

class D(B):
    d_param = param.Number(3.14)

# Test inheritance with different import styles
C().a_param = 123       # Error: inherited String
C().c_param = "wrong"   # Error: Boolean
D().b_param = "wrong"   # Error: inherited Integer
D().d_param = "wrong"   # Error: Number
""")

        analyzer = ParamAnalyzer(workspace_root=str(tmp_path))

        with open(test_file) as f:
            content = f.read()

        result = analyzer.analyze_file(content, str(test_file))

        # Verify both classes are detected
        assert "C" in result["param_classes"], "Class C should be detected"
        assert "D" in result["param_classes"], "Class D should be detected"

        c_class = result["param_classes"]["C"]
        d_class = result["param_classes"]["D"]

        # Verify inheritance for C
        assert set(c_class.parameters.keys()) == {"a_param", "c_param"}, "C should inherit from A"
        assert c_class.parameters["a_param"].cls == "String", "a_param should be String"
        assert c_class.parameters["c_param"].cls == "Boolean", "c_param should be Boolean"

        # Verify inheritance for D
        assert set(d_class.parameters.keys()) == {"b_param", "d_param"}, "D should inherit from B"
        assert d_class.parameters["b_param"].cls == "Integer", "b_param should be Integer"
        assert d_class.parameters["d_param"].cls == "Number", "d_param should be Number"

        # Verify all type errors are detected
        assert len(result["type_errors"]) == 4, "Should detect four type errors"
