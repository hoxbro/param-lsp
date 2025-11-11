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
        assert "Allowed types: int | float" in hover_info
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
        assert "Allowed types: int | float" in hover_info
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
        # Should include source location but not documentation section
        assert "Definition (line 4):" in hover_info
        assert hover_info.count("\n\n") <= 4  # Header, type info, separator, and source location

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

    def test_hover_with_allow_None(self, lsp_server):
        """Test hover information for parameters with allow_None=True."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    optional_string = param.String(default=None, allow_None=True, doc="String that allows None")
    optional_int = param.Integer(allow_None=True, doc="Integer that allows None")
    required_string = param.String(default="required", doc="String that doesn't allow None")
    default_none = param.Number(default=None, doc="Number with default=None (auto allow_None)")
"""

        uri = "file:///test.py"
        lsp_server._analyze_document(uri, code_py)

        # Test hover for string parameter with explicit allow_None=True
        hover_info = lsp_server._get_hover_info(uri, "optional_string", "optional_string")

        assert hover_info is not None
        assert "String Parameter 'optional_string'" in hover_info
        assert "Allowed types: str | None" in hover_info
        assert "String that allows None" in hover_info

        # Test hover for integer parameter with allow_None=True
        hover_info = lsp_server._get_hover_info(uri, "optional_int", "optional_int")

        assert hover_info is not None
        assert "Integer Parameter 'optional_int'" in hover_info
        assert "Allowed types: int | None" in hover_info
        assert "Integer that allows None" in hover_info

        # Test hover for parameter without allow_None (should not show None)
        hover_info = lsp_server._get_hover_info(uri, "required_string", "required_string")

        assert hover_info is not None
        assert "String Parameter 'required_string'" in hover_info
        assert "Allowed types: str" in hover_info  # Should NOT include None
        assert "String that doesn't allow None" in hover_info

        # Test hover for parameter with default=None (auto allow_None=True)
        hover_info = lsp_server._get_hover_info(uri, "default_none", "default_none")

        assert hover_info is not None
        assert "Number Parameter 'default_none'" in hover_info
        assert (
            "Allowed types: int | float | None" in hover_info
        )  # Should include None due to default=None
        assert "Number with default=None" in hover_info

    def test_hover_allow_None_with_bounds(self, lsp_server):
        """Test hover information for parameters with both allow_None and bounds."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    bounded_optional = param.Number(
        default=5.0,
        bounds=(0, 10),
        allow_None=True,
        doc="Number with bounds that allows None"
    )
"""

        uri = "file:///test.py"
        lsp_server._analyze_document(uri, code_py)

        hover_info = lsp_server._get_hover_info(uri, "bounded_optional", "bounded_optional")

        assert hover_info is not None
        assert "Number Parameter 'bounded_optional'" in hover_info
        assert "Allowed types: int | float | None" in hover_info
        assert "Bounds: `[0, 10]`" in hover_info
        assert "Number with bounds that allows None" in hover_info

    def test_param_update_method_hover(self, lsp_server):
        """Test hover information for obj.param.update() method."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    x = param.Integer(default=5, doc="An integer parameter")
    y = param.String(default="hello", doc="A string parameter")

# Test obj.param.update() hover
obj = TestClass()
obj.param.update(x=10, y="world")
"""

        uri = "file:///test.py"
        lsp_server._analyze_document(uri, code_py)

        # Test hover for the "update" word in obj.param.update() context
        line_with_update = 'obj.param.update(x=10, y="world")'
        hover_info = lsp_server._get_hover_info(uri, line_with_update, "update")

        assert hover_info is not None
        assert "obj.param.update(**params)" in hover_info
        assert "Update multiple parameters at once" in hover_info
        assert "keyword arguments" in hover_info
        assert "Returns**: `None`" in hover_info
        assert "Example" in hover_info
        assert "obj.param.update(x=10, y='new_value')" in hover_info
        assert "Efficiently updates multiple parameters" in hover_info

    def test_hover_selector_with_numeric_objects(self, lsp_server):
        """Test hover information for Selector parameter with numeric objects."""
        code_py = """\
import param

class TestClass(param.Parameterized):
    numeric_selector = param.Selector(default=1, objects=[1, 2, 3], doc="Selector with numeric objects")
    string_selector = param.Selector(default="a", objects=["a", "b", "c"], doc="Selector with string objects")
"""

        uri = "file:///test.py"
        lsp_server._analyze_document(uri, code_py)

        # Test hover for numeric selector parameter
        hover_info = lsp_server._get_hover_info(uri, "numeric_selector", "numeric_selector")

        assert hover_info is not None
        assert "Selector Parameter 'numeric_selector'" in hover_info
        assert "Allowed objects:" in hover_info
        assert "[1, 2, 3]" in hover_info  # Numbers without quotes
        assert "Selector with numeric objects" in hover_info

        # Test hover for string selector parameter
        hover_info = lsp_server._get_hover_info(uri, "string_selector", "string_selector")

        assert hover_info is not None
        assert "Selector Parameter 'string_selector'" in hover_info
        assert "Allowed objects:" in hover_info
        assert '["a", "b", "c"]' in hover_info  # Strings with quotes
        assert "Selector with string objects" in hover_info
