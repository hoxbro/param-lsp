"""Tests for the AST navigator module."""

from __future__ import annotations

from param_lsp._analyzer.ast_navigator import (
    ImportHandler,
    ParameterDetector,
    SourceAnalyzer,
)
from param_lsp._treesitter import parser


def _get_first_statement(code: str):
    """Helper to parse code and get the first statement node."""
    tree = parser.parse(code)
    # For tree-sitter, we need to find the first meaningful node
    # The root is a module node, first child is usually the statement
    for child in tree.root_node.children:
        if child.type in (
            "expression_statement",
            "assignment",
            "import_statement",
            "import_from_statement",
        ):
            # For expression statements, we might need to go one level deeper
            if (
                child.type == "expression_statement"
                and child.children
                and child.children[0].type in ("assignment", "call", "attribute")
            ):
                # Return the actual expression (assignment or call)
                return child.children[0]
            return child
    return tree.root_node.children[0] if tree.root_node.children else tree.root_node


class TestParameterDetector:
    """Test ParameterDetector functionality."""

    def test_is_parameter_assignment_with_param_integer(self):
        """Test detection of param.Integer assignment."""
        code = "width = param.Integer(default=100)"
        assignment = _get_first_statement(code)

        imports = {"param": "param"}
        detector = ParameterDetector(imports)

        assert detector.is_parameter_assignment(assignment)

    def test_is_parameter_assignment_with_direct_call(self):
        """Test detection of direct parameter type call."""
        code = "height = Integer(default=50)"
        assignment = _get_first_statement(code)

        imports = {"Integer": "param.Integer"}
        detector = ParameterDetector(imports)

        assert detector.is_parameter_assignment(assignment)

    def test_is_parameter_assignment_not_parameter(self):
        """Test that non-parameter assignments are not detected."""
        code = "value = 42"
        assignment = _get_first_statement(code)

        imports = {}
        detector = ParameterDetector(imports)

        assert not detector.is_parameter_assignment(assignment)

    def test_is_parameter_call_direct_type(self):
        """Test detection of direct parameter type calls."""
        code = "param.Integer(default=100)"
        call_node = _get_first_statement(code)

        imports = {"param": "param"}
        detector = ParameterDetector(imports)

        assert detector.is_parameter_call(call_node)

    def test_is_parameter_call_imported_type(self):
        """Test detection of imported parameter type calls."""
        code = "Integer(default=100)"
        call_node = _get_first_statement(code)

        imports = {"Integer": "param.Integer"}
        detector = ParameterDetector(imports)

        assert detector.is_parameter_call(call_node)

    def test_is_parameter_call_not_parameter(self):
        """Test that non-parameter calls are not detected."""
        code = "some_function(arg=value)"
        call_node = _get_first_statement(code)

        imports = {}
        detector = ParameterDetector(imports)

        assert not detector.is_parameter_call(call_node)


class TestImportHandler:
    """Test ImportHandler functionality."""

    def test_handle_import_simple(self):
        """Test handling of simple import statement."""
        code = "import param"
        import_node = _get_first_statement(code)

        imports = {}
        handler = ImportHandler(imports)
        handler.handle_import(import_node)

        assert imports == {"param": "param"}

    def test_handle_import_with_alias(self):
        """Test handling of import with alias."""
        code = "import param as p"
        import_node = _get_first_statement(code)

        imports = {}
        handler = ImportHandler(imports)
        handler.handle_import(import_node)

        assert imports == {"p": "param"}

    def test_handle_import_dotted(self):
        """Test handling of dotted import."""
        code = "import param.version"
        import_node = _get_first_statement(code)

        imports = {}
        handler = ImportHandler(imports)
        handler.handle_import(import_node)

        assert imports == {"param.version": "param.version"}

    def test_handle_import_from_simple(self):
        """Test handling of from-import statement."""
        code = "from param import Integer"
        import_node = _get_first_statement(code)

        imports = {}
        handler = ImportHandler(imports)
        handler.handle_import_from(import_node)

        assert imports == {"Integer": "param.Integer"}

    def test_handle_import_from_multiple(self):
        """Test handling of from-import with multiple names."""
        code = "from param import Integer, String"
        import_node = _get_first_statement(code)

        imports = {}
        handler = ImportHandler(imports)
        handler.handle_import_from(import_node)

        expected = {"Integer": "param.Integer", "String": "param.String"}
        assert imports == expected

    def test_handle_import_from_with_alias(self):
        """Test handling of from-import with alias."""
        code = "from param import Integer as Int"
        import_node = _get_first_statement(code)

        imports = {}
        handler = ImportHandler(imports)
        handler.handle_import_from(import_node)

        assert imports == {"Int": "param.Integer"}


class TestSourceAnalyzer:
    """Test SourceAnalyzer functionality."""

    def test_looks_like_parameter_assignment_true(self):
        """Test detection of parameter-like assignments."""
        line = "width = param.Integer(default=100, bounds=(1, 1000))"
        assert SourceAnalyzer.looks_like_parameter_assignment(line)

    def test_looks_like_parameter_assignment_false_simple_value(self):
        """Test that simple value assignments are not detected."""
        line = "width = 100"
        assert not SourceAnalyzer.looks_like_parameter_assignment(line)

    def test_looks_like_parameter_assignment_false_string(self):
        """Test that string assignments are not detected."""
        line = 'title = "Widget"'
        assert not SourceAnalyzer.looks_like_parameter_assignment(line)

    def test_looks_like_parameter_assignment_false_list(self):
        """Test that list assignments are not detected."""
        line = "items = [1, 2, 3]"
        assert not SourceAnalyzer.looks_like_parameter_assignment(line)

    def test_extract_multiline_definition_simple(self):
        """Test extraction of simple single-line definition."""
        source_lines = ["width = param.Integer(default=100)"]
        result = SourceAnalyzer.extract_multiline_definition(source_lines, 0)
        assert result == "width = param.Integer(default=100)"

    def test_extract_multiline_definition_complex(self):
        """Test extraction of complex multiline definition."""
        source_lines = [
            "width = param.Integer(",
            "    default=100,",
            "    bounds=(1, 1000),",
            "    doc='Widget width'",
            ")",
        ]
        result = SourceAnalyzer.extract_multiline_definition(source_lines, 0)
        expected = "\n".join(source_lines)
        assert result == expected

    def test_extract_multiline_definition_with_nested_parens(self):
        """Test extraction with nested parentheses."""
        source_lines = [
            "items = param.List(",
            "    default=[func(a, b), other(x, y)],",
            "    doc='List of items'",
            ")",
        ]
        result = SourceAnalyzer.extract_multiline_definition(source_lines, 0)
        expected = "\n".join(source_lines)
        assert result == expected

    def test_extract_complete_parameter_definition_found(self):
        """Test finding complete parameter definition."""
        source_lines = [
            "class MyWidget(param.Parameterized):",
            "    width = param.Integer(default=100)",
            "    height = param.Integer(default=50)",
        ]
        result = SourceAnalyzer.extract_complete_parameter_definition(source_lines, "width")
        assert result == "width = param.Integer(default=100)"

    def test_extract_complete_parameter_definition_not_found(self):
        """Test when parameter definition is not found."""
        source_lines = [
            "class MyWidget(param.Parameterized):",
            "    height = param.Integer(default=50)",
        ]
        result = SourceAnalyzer.extract_complete_parameter_definition(source_lines, "width")
        assert result is None

    def test_find_parameter_line_in_source_found(self):
        """Test finding parameter line number."""
        source_lines = [
            "class MyWidget(param.Parameterized):",
            "    width = param.Integer(default=100)",
            "    height = param.Integer(default=50)",
        ]
        result = SourceAnalyzer.find_parameter_line_in_source(source_lines, 0, "width")
        assert result == 1  # 0-based index + start_line

    def test_find_parameter_line_in_source_not_found(self):
        """Test when parameter line is not found."""
        source_lines = [
            "class MyWidget(param.Parameterized):",
            "    height = param.Integer(default=50)",
        ]
        result = SourceAnalyzer.find_parameter_line_in_source(source_lines, 0, "width")
        assert result is None
