"""Tests for hover information functionality."""

from __future__ import annotations


class TestHoverInformation:
    """Test hover information generation for parameters."""

    def test_parameter_hover_basic_info(self, lsp_server):
        """Test basic parameter hover information."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    string_param = param.String(default="hello", doc="A string parameter")
    int_param = param.Integer(default=5)
"""

        # Simulate document analysis
        uri = "file:///test.py"
        lsp_server._analyze_document(uri, code_py)

        # Test hover for documented parameter
        hover_info = lsp_server._get_hover_info(uri, "string_param", "string_param")

        assert hover_info is not None
        assert "String Parameter 'string_param'" in hover_info
        assert "Allowed types: str" in hover_info
        assert "A string parameter" in hover_info

        # Test hover for undocumented parameter
        hover_info = lsp_server._get_hover_info(uri, "int_param", "int_param")

        assert hover_info is not None
        assert "Integer Parameter 'int_param'" in hover_info
        assert "Allowed types: int" in hover_info

    def test_parameter_hover_with_bounds(self, lsp_server):
        """Test parameter hover information with bounds."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    bounded_int = param.Integer(
        default=5,
        bounds=(0, 10),
        doc="An integer with bounds"
    )

    exclusive_bounds = param.Number(
        default=2.5,
        bounds=(0, 5),
        inclusive_bounds=(False, True),
        doc="A number with exclusive left bound"
    )
"""

        uri = "file:///test.py"
        lsp_server._analyze_document(uri, code_py)

        # Test hover for parameter with inclusive bounds
        hover_info = lsp_server._get_hover_info(uri, "bounded_int", "bounded_int")

        assert hover_info is not None
        assert "Allowed types: int" in hover_info
        assert "Bounds: `[0, 10]`" in hover_info
        assert "An integer with bounds" in hover_info

        # Test hover for parameter with exclusive bounds
        hover_info = lsp_server._get_hover_info(uri, "exclusive_bounds", "exclusive_bounds")

        assert hover_info is not None
        assert "Allowed types: int or float" in hover_info
        assert "Bounds: `(0, 5]`" in hover_info
        assert "A number with exclusive left bound" in hover_info

    def test_parameter_hover_comprehensive(self, lsp_server):
        """Test comprehensive parameter hover information."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    comprehensive_param = param.Number(
        default=2.5,
        bounds=(1.0, 10.0),
        inclusive_bounds=(True, False),
        doc="A comprehensive parameter with all the information"
    )
"""

        uri = "file:///test.py"
        lsp_server._analyze_document(uri, code_py)

        hover_info = lsp_server._get_hover_info(uri, "comprehensive_param", "comprehensive_param")

        assert hover_info is not None

        # Check all components are present
        assert "**Number Parameter 'comprehensive_param'**" in hover_info
        assert "Allowed types: int or float" in hover_info
        assert "Bounds: `[1.0, 10.0)`" in hover_info  # Left inclusive, right exclusive
        assert "A comprehensive parameter with all the information" in hover_info

        # Check formatting with newlines
        lines = hover_info.split("\n\n")
        assert len(lines) >= 3  # Header, type/bounds info, documentation

    def test_parameter_type_hover(self, lsp_server):
        """Test hover information for parameter types."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    test_param = param.String(default="test")
"""

        uri = "file:///test.py"
        lsp_server._analyze_document(uri, code_py)

        # Test hover for parameter type (if param module is available)
        hover_info = lsp_server._get_hover_info(uri, "String", "String")

        # This should return param type information
        if hover_info:
            assert "String" in hover_info or "Param parameter type" in hover_info

    def test_hover_for_non_parameter(self, lsp_server):
        """Test hover for non-parameter words returns None."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    test_param = param.String(default="test")

regular_variable = "not a parameter"
"""

        uri = "file:///test.py"
        lsp_server._analyze_document(uri, code_py)

        # Test hover for non-parameter word
        hover_info = lsp_server._get_hover_info(uri, "regular_variable", "regular_variable")

        assert hover_info is None

    def test_hover_multiple_classes(self, lsp_server):
        """Test hover information with multiple param classes."""
        code_py = """\
import param

class ClassA(param.Parameterized):
    param_a = param.String(default="a", doc="Parameter from class A")

class ClassB(param.Parameterized):
    param_b = param.Integer(default=1, doc="Parameter from class B")
    param_a = param.Boolean(default=True, doc="Different param_a in class B")
"""

        uri = "file:///test.py"
        lsp_server._analyze_document(uri, code_py)

        # Test hover for param_a (should find the first matching one)
        hover_info = lsp_server._get_hover_info(uri, "param_a", "param_a")

        assert hover_info is not None
        # Should contain information about one of the param_a parameters
        assert "param_a" in hover_info
        assert "class" in hover_info

    def test_hover_with_different_import_styles(self, lsp_server):
        """Test hover information with different import styles."""
        code_py = """\
import param as p
from param import String

class TestClass(p.Parameterized):
    param1 = p.String(default="test1", doc="Using param alias")
    param2 = String(default="test2", doc="Using direct import")
"""

        uri = "file:///test.py"
        lsp_server._analyze_document(uri, code_py)

        # Test hover for parameter using alias
        hover_info = lsp_server._get_hover_info(uri, "param1", "param1")

        assert hover_info is not None
        assert "param1" in hover_info
        assert "Allowed types: str" in hover_info
        assert "Using param alias" in hover_info

        # Test hover for parameter using direct import
        hover_info = lsp_server._get_hover_info(uri, "param2", "param2")

        assert hover_info is not None
        assert "param2" in hover_info
        assert "Allowed types: str" in hover_info
        assert "Using direct import" in hover_info

    def test_hover_bounds_notation(self, lsp_server):
        """Test correct bounds notation in hover information."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    inclusive_both = param.Number(
        default=5.0,
        bounds=(0, 10),
        inclusive_bounds=(True, True)
    )

    exclusive_both = param.Number(
        default=5.0,
        bounds=(0, 10),
        inclusive_bounds=(False, False)
    )

    mixed_bounds = param.Number(
        default=5.0,
        bounds=(0, 10),
        inclusive_bounds=(False, True)
    )
"""

        uri = "file:///test.py"
        lsp_server._analyze_document(uri, code_py)

        # Test inclusive bounds [0, 10]
        hover_info = lsp_server._get_hover_info(uri, "inclusive_both", "inclusive_both")
        assert "Bounds: `[0, 10]`" in hover_info

        # Test exclusive bounds (0, 10)
        hover_info = lsp_server._get_hover_info(uri, "exclusive_both", "exclusive_both")
        assert "Bounds: `(0, 10)`" in hover_info

        # Test mixed bounds (0, 10]
        hover_info = lsp_server._get_hover_info(uri, "mixed_bounds", "mixed_bounds")
        assert "Bounds: `(0, 10]`" in hover_info

    def test_hover_with_no_documentation(self, lsp_server):
        """Test hover information for parameters without documentation."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    undocumented = param.String(default="test")
    with_bounds = param.Integer(default=5, bounds=(0, 10))
"""

        uri = "file:///test.py"
        lsp_server._analyze_document(uri, code_py)

        # Test hover for undocumented parameter
        hover_info = lsp_server._get_hover_info(uri, "undocumented", "undocumented")

        assert hover_info is not None
        assert "String Parameter 'undocumented'" in hover_info
        assert "Allowed types: str" in hover_info
        # Should not have documentation section
        assert hover_info.count("\n\n") <= 2  # Just header and type info

        # Test hover for parameter with bounds but no doc
        hover_info = lsp_server._get_hover_info(uri, "with_bounds", "with_bounds")

        assert hover_info is not None
        assert "Allowed types: int" in hover_info
        assert "Bounds: `[0, 10]`" in hover_info

    def test_hover_markdown_formatting(self, lsp_server):
        """Test that hover information uses proper markdown formatting."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    test_param = param.String(default="test", doc="Test documentation")
"""

        uri = "file:///test.py"
        lsp_server._analyze_document(uri, code_py)

        hover_info = lsp_server._get_hover_info(uri, "test_param", "test_param")

        assert hover_info is not None

        # Check markdown formatting
        assert hover_info.startswith("**String Parameter")  # Bold header
        assert "Allowed types: str" in hover_info  # Type information

        # Check structure with double newlines
        sections = hover_info.split("\n\n")
        assert len(sections) >= 2  # At least header and documentation
