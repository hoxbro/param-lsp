"""Tests for hover functionality with cross-file inheritance."""

from __future__ import annotations

from param_lsp.server import ParamLanguageServer


class TestHoverCrossFile:
    """Test hover functionality with cross-file parameter inheritance."""

    def test_hover_inherited_parameter(self, tmp_path):
        """Test hover information for parameters inherited from imported classes."""
        # Create parent module
        parent_file = tmp_path / "parent.py"
        parent_file.write_text("""
import param

class Parent(param.Parameterized):
    x = param.Integer(10, doc="Integer parameter from parent class")
    name = param.String("parent", doc="String parameter with default")
""")

        # Create child module
        child_file = tmp_path / "child.py"
        child_file.write_text("""
import param
from parent import Parent

class Child(Parent):
    local_param = param.Boolean(True, doc="Local parameter in child class")

# Use inherited parameters
Child().x = "invalid"
Child().name = 123
Child().local_param = "wrong"
""")

        # Set up language server
        server = ParamLanguageServer("param-lsp", "v0.1.0")
        server.workspace_root = str(tmp_path)
        server.analyzer = server.analyzer.__class__(str(tmp_path))

        # Analyze the child file
        with open(child_file) as f:
            content = f.read()

        uri = f"file://{child_file}"
        server._analyze_document(uri, content)

        # Test hover for inherited parameter 'x'
        hover_info_x = server._get_hover_info(uri, "Child().x = 'invalid'", "x")
        assert hover_info_x is not None, "Should provide hover info for inherited parameter 'x'"
        assert "Integer Parameter 'x'" in hover_info_x
        assert "Allowed types: int" in hover_info_x
        assert "Integer parameter" in hover_info_x

        # Test hover for inherited parameter 'name'
        hover_info_name = server._get_hover_info(uri, "Child().name = 123", "name")
        assert hover_info_name is not None, (
            "Should provide hover info for inherited parameter 'name'"
        )
        assert "String Parameter 'name'" in hover_info_name
        assert "Allowed types: str" in hover_info_name
        assert "String parameter with default" in hover_info_name

        # Test hover for local parameter
        hover_info_local = server._get_hover_info(
            uri, "Child().local_param = 'wrong'", "local_param"
        )
        assert hover_info_local is not None, "Should provide hover info for local parameter"
        assert "Boolean Parameter 'local_param'" in hover_info_local
        assert "Allowed types: bool" in hover_info_local
        assert "Local parameter in child class" in hover_info_local

    def test_hover_inherited_parameter_with_bounds(self, tmp_path):
        """Test hover information includes inherited bounds."""
        # Create parent module with bounds
        parent_file = tmp_path / "parent.py"
        parent_file.write_text("""
import param

class Parent(param.Parameterized):
    bounded_num = param.Number(5.0, bounds=(0, 10), doc="Number with bounds")
""")

        # Create child module
        child_file = tmp_path / "child.py"
        child_file.write_text("""
import param
from parent import Parent

class Child(Parent):
    pass

Child().bounded_num = 15  # Should violate bounds
""")

        # Set up language server
        server = ParamLanguageServer("param-lsp", "v0.1.0")
        server.workspace_root = str(tmp_path)
        server.analyzer = server.analyzer.__class__(str(tmp_path))

        # Analyze the child file
        with open(child_file) as f:
            content = f.read()

        uri = f"file://{child_file}"
        server._analyze_document(uri, content)

        # Test hover for inherited parameter with bounds
        hover_info = server._get_hover_info(uri, "Child().bounded_num = 15", "bounded_num")
        assert hover_info is not None, (
            "Should provide hover info for inherited parameter with bounds"
        )
        assert "Number Parameter 'bounded_num'" in hover_info
        assert "Number" in hover_info
        assert "Bounds: `[0, 10]`" in hover_info
        assert "Number with bounds" in hover_info

    def test_hover_multi_level_inheritance(self, tmp_path):
        """Test hover information for multi-level inheritance."""
        # Create base module
        base_file = tmp_path / "base.py"
        base_file.write_text("""
import param

class Base(param.Parameterized):
    base_value = param.String("base", doc="Base class parameter")
""")

        # Create intermediate module
        intermediate_file = tmp_path / "intermediate.py"
        intermediate_file.write_text("""
import param
from base import Base

class Intermediate(Base):
    intermediate_value = param.Integer(42, doc="Intermediate class parameter")
""")

        # Create final module
        final_file = tmp_path / "final.py"
        final_file.write_text("""
import param
from intermediate import Intermediate

class Final(Intermediate):
    final_value = param.Boolean(True, doc="Final class parameter")

Final().base_value = 123         # From Base
Final().intermediate_value = "x" # From Intermediate
Final().final_value = "wrong"    # From Final
""")

        # Set up language server
        server = ParamLanguageServer("param-lsp", "v0.1.0")
        server.workspace_root = str(tmp_path)
        server.analyzer = server.analyzer.__class__(str(tmp_path))

        # Analyze the final file
        with open(final_file) as f:
            content = f.read()

        uri = f"file://{final_file}"
        server._analyze_document(uri, content)

        # Test hover for parameter from Base
        hover_base = server._get_hover_info(uri, "Final().base_value = 123", "base_value")
        assert hover_base is not None
        assert "String Parameter 'base_value'" in hover_base
        assert "String" in hover_base
        assert "Base class parameter" in hover_base

        # Test hover for parameter from Intermediate
        hover_intermediate = server._get_hover_info(
            uri, "Final().intermediate_value = 'x'", "intermediate_value"
        )
        assert hover_intermediate is not None
        assert "Integer Parameter 'intermediate_value'" in hover_intermediate
        assert "Integer" in hover_intermediate
        assert "Intermediate class parameter" in hover_intermediate

        # Test hover for parameter from Final
        hover_final = server._get_hover_info(uri, "Final().final_value = 'wrong'", "final_value")
        assert hover_final is not None
        assert "Boolean Parameter 'final_value'" in hover_final
        assert "Boolean" in hover_final
        assert "Final class parameter" in hover_final

    def test_hover_parameter_overriding(self, tmp_path):
        """Test hover information for overridden parameters."""
        # Create parent module
        parent_file = tmp_path / "parent.py"
        parent_file.write_text("""
import param

class Parent(param.Parameterized):
    value = param.Integer(1, doc="Original integer parameter")
""")

        # Create child module that overrides parameter
        child_file = tmp_path / "child.py"
        child_file.write_text("""
import param
from parent import Parent

class Child(Parent):
    value = param.String("override", doc="Overridden as string parameter")

Child().value = 123  # Should error based on overridden type
""")

        # Set up language server
        server = ParamLanguageServer("param-lsp", "v0.1.0")
        server.workspace_root = str(tmp_path)
        server.analyzer = server.analyzer.__class__(str(tmp_path))

        # Analyze the child file
        with open(child_file) as f:
            content = f.read()

        uri = f"file://{child_file}"
        server._analyze_document(uri, content)

        # Test hover shows overridden parameter info, not parent
        hover_info = server._get_hover_info(uri, "Child().value = 123", "value")
        assert hover_info is not None
        assert "String Parameter 'value'" in hover_info
        assert "String" in hover_info  # Should show child type, not parent Integer
        assert "Overridden as string parameter" in hover_info  # Should show child doc, not parent

    def test_hover_no_info_for_unknown_parameter(self, tmp_path):
        """Test that hover returns None for unknown parameters."""
        # Create simple module
        simple_file = tmp_path / "simple.py"
        simple_file.write_text("""
import param

class Simple(param.Parameterized):
    known_param = param.String("test")

obj = Simple()
obj.unknown_param = "value"  # This parameter doesn't exist
""")

        # Set up language server
        server = ParamLanguageServer("param-lsp", "v0.1.0")
        server.workspace_root = str(tmp_path)
        server.analyzer = server.analyzer.__class__(str(tmp_path))

        # Analyze the file
        with open(simple_file) as f:
            content = f.read()

        uri = f"file://{simple_file}"
        server._analyze_document(uri, content)

        # Test hover for unknown parameter returns None
        hover_info = server._get_hover_info(uri, "obj.unknown_param = 'value'", "unknown_param")
        assert hover_info is None, "Should return None for unknown parameters"

        # Test hover for known parameter works
        hover_known = server._get_hover_info(uri, "obj.known_param = 'value'", "known_param")
        assert hover_known is not None, "Should provide hover info for known parameter"
