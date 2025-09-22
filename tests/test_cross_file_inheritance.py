"""Tests for cross-file parameter inheritance functionality."""

from __future__ import annotations

from param_lsp.analyzer import ParamAnalyzer


class TestCrossFileInheritance:
    """Test parameter inheritance across multiple files."""

    def test_basic_cross_file_inheritance(self, tmp_path):
        """Test basic inheritance from an imported parent class."""
        # Create parent module
        parent_file = tmp_path / "parent.py"
        parent_file.write_text("""
import param

class P(param.Parameterized):
    x = param.Integer(5)
    name = param.String("parent")
""")

        # Create child module
        child_file = tmp_path / "child.py"
        child_file.write_text("""
import param
from parent import P

class S(P):
    b = param.Boolean(True)

# Test assignments
S().x = "not_int"      # Should error - inherited Integer
S().b = "not_bool"     # Should error - Boolean
S().name = 123         # Should error - inherited String
""")

        # Analyze with workspace context

        analyzer = ParamAnalyzer(str(tmp_path))

        with open(child_file) as f:
            content = f.read()

        result = analyzer.analyze_file(content, str(child_file))

        assert "S" in result["param_classes"]
        assert set(result["param_parameters"]["S"]) == {"x", "name", "b"}
        assert result["param_parameter_types"]["S"]["x"] == "Integer"
        assert result["param_parameter_types"]["S"]["name"] == "String"
        assert result["param_parameter_types"]["S"]["b"] == "Boolean"

        # Should detect 3 type errors
        assert len(result["type_errors"]) == 3
        error_messages = [e["message"] for e in result["type_errors"]]
        assert any("Integer" in msg for msg in error_messages)
        assert any("Boolean" in msg for msg in error_messages)
        assert any("String" in msg for msg in error_messages)

    def test_multi_level_cross_file_inheritance(self, tmp_path):
        """Test inheritance across multiple levels and files."""
        # Create base module
        base_file = tmp_path / "base.py"
        base_file.write_text("""
import param

class Base(param.Parameterized):
    base_value = param.String("base")
""")

        # Create intermediate module
        intermediate_file = tmp_path / "intermediate.py"
        intermediate_file.write_text("""
import param
from base import Base

class Intermediate(Base):
    intermediate_num = param.Number(3.14, bounds=(0, 10))
""")

        # Create final module
        final_file = tmp_path / "final.py"
        final_file.write_text("""
import param
from intermediate import Intermediate

class Final(Intermediate):
    final_bool = param.Boolean(False)

# Test multi-level inheritance
obj = Final()
obj.base_value = 123        # Error - String from Base
obj.intermediate_num = 15   # Error - bounds violation
obj.final_bool = "invalid"  # Error - Boolean
""")

        analyzer = ParamAnalyzer(str(tmp_path))

        with open(final_file) as f:
            content = f.read()

        result = analyzer.analyze_file(content, str(final_file))

        assert "Final" in result["param_classes"]
        assert set(result["param_parameters"]["Final"]) == {
            "base_value",
            "intermediate_num",
            "final_bool",
        }

        # Check inherited types
        assert result["param_parameter_types"]["Final"]["base_value"] == "String"
        assert result["param_parameter_types"]["Final"]["intermediate_num"] == "Number"
        assert result["param_parameter_types"]["Final"]["final_bool"] == "Boolean"

        # Check inherited bounds
        assert "intermediate_num" in result["param_parameter_bounds"]["Final"]

        # Should detect 3 errors
        assert len(result["type_errors"]) == 3

    def test_cross_file_parameter_overriding(self, tmp_path):
        """Test parameter overriding across files."""
        # Create parent module
        parent_file = tmp_path / "parent.py"
        parent_file.write_text("""
import param

class Parent(param.Parameterized):
    value = param.Integer(1)
""")

        # Create child module that overrides parameter
        child_file = tmp_path / "child.py"
        child_file.write_text("""
import param
from parent import Parent

class Child(Parent):
    value = param.String("override")  # Override with different type

Child().value = 123  # Should error - expecting string now
""")

        analyzer = ParamAnalyzer(str(tmp_path))

        with open(child_file) as f:
            content = f.read()

        result = analyzer.analyze_file(content, str(child_file))

        assert "Child" in result["param_classes"]
        # Child should override parent parameter type
        assert result["param_parameter_types"]["Child"]["value"] == "String"

        # Should detect type error based on child class type
        assert len(result["type_errors"]) == 1
        assert "String" in result["type_errors"][0]["message"]

    def test_cross_file_bounds_inheritance(self, tmp_path):
        """Test that parameter bounds are inherited across files."""
        # Create parent module with bounds
        parent_file = tmp_path / "parent.py"
        parent_file.write_text("""
import param

class Parent(param.Parameterized):
    x = param.Number(5.0, bounds=(0, 10))
""")

        # Create child module
        child_file = tmp_path / "child.py"
        child_file.write_text("""
import param
from parent import Parent

class Child(Parent):
    y = param.Integer(3, bounds=(1, 5))

Child().x = 15  # Should violate inherited bounds
Child().y = 10  # Should violate local bounds
""")

        analyzer = ParamAnalyzer(str(tmp_path))

        with open(child_file) as f:
            content = f.read()

        result = analyzer.analyze_file(content, str(child_file))

        assert "Child" in result["param_classes"]

        # Check bounds inheritance
        assert "x" in result["param_parameter_bounds"]["Child"]
        assert "y" in result["param_parameter_bounds"]["Child"]

        # Should detect 2 bounds violations
        bounds_errors = [e for e in result["type_errors"] if e["code"] == "bounds-violation"]
        assert len(bounds_errors) == 2

    def test_cross_file_docs_inheritance(self, tmp_path):
        """Test that parameter documentation is inherited across files."""
        # Create parent module with docs
        parent_file = tmp_path / "parent.py"
        parent_file.write_text("""
import param

class Parent(param.Parameterized):
    x = param.Integer(5, doc="Parent parameter documentation")
""")

        # Create child module
        child_file = tmp_path / "child.py"
        child_file.write_text("""
import param
from parent import Parent

class Child(Parent):
    y = param.String("test", doc="Child parameter documentation")
""")

        analyzer = ParamAnalyzer(str(tmp_path))

        with open(child_file) as f:
            content = f.read()

        result = analyzer.analyze_file(content, str(child_file))

        assert "Child" in result["param_classes"]

        # Check doc inheritance
        assert result["param_parameter_docs"]["Child"]["x"] == "Parent parameter documentation"
        assert result["param_parameter_docs"]["Child"]["y"] == "Child parameter documentation"

    def test_missing_import_module(self, tmp_path):
        """Test graceful handling when imported module doesn't exist."""
        # Create child module with missing import
        child_file = tmp_path / "child.py"
        child_file.write_text("""
import param
from nonexistent import P

class S(P):
    b = param.Boolean(True)

S().b = "test"  # No error should be detected since P is unknown
""")

        analyzer = ParamAnalyzer(str(tmp_path))

        with open(child_file) as f:
            content = f.read()

        result = analyzer.analyze_file(content, str(child_file))

        # S should not be detected as a param class since P is unknown
        assert "S" not in result["param_classes"]
        assert len(result["type_errors"]) == 0

    def test_non_param_parent_class(self, tmp_path):
        """Test inheritance from non-param classes."""
        # Create parent module with regular class
        parent_file = tmp_path / "parent.py"
        parent_file.write_text("""
class RegularClass:
    def __init__(self):
        self.value = 1
""")

        # Create child module
        child_file = tmp_path / "child.py"
        child_file.write_text("""
import param
from parent import RegularClass

class S(RegularClass):
    b = param.Boolean(True)

S().b = "test"  # No error since S doesn't inherit from param.Parameterized
""")

        analyzer = ParamAnalyzer(str(tmp_path))

        with open(child_file) as f:
            content = f.read()

        result = analyzer.analyze_file(content, str(child_file))

        # S should not be detected as a param class
        assert "S" not in result["param_classes"]
        assert len(result["type_errors"]) == 0
