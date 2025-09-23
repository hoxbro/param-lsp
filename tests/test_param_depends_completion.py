"""Test param.depends completion functionality."""

from __future__ import annotations

from lsprotocol.types import Position

from src.param_lsp.server import ParamLanguageServer


class TestParamDependsCompletion:
    """Test param.depends decorator parameter completion."""

    def test_param_depends_completion_basic(self):
        """Test basic param.depends completion functionality."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=1, allow_None=True)
    y = param.Integer(default=21)

    @param.depends(
    def tmp(self):
        ..."""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        lines = [str(line) for line in code_py.split("\n")]
        position = Position(line=7, character=18)  # After the opening parenthesis

        # Test if we detect param.depends context
        is_in_depends = server._is_in_param_depends_decorator(lines, position)
        assert is_in_depends, "Should detect that we're in a param.depends decorator"

        # Test finding containing class
        containing_class = server._find_containing_class(lines, position.line)
        assert containing_class == "P", f"Should find class P, got {containing_class}"

        # Test getting completions
        completions = server._get_param_depends_completions("file:///test.py", lines, position)

        # Should have completions for both x and y parameters
        assert len(completions) == 2, f"Expected 2 completions, got {len(completions)}"

        completion_labels = [item.label for item in completions]
        assert '"x"' in completion_labels, "Should suggest 'x' parameter"
        assert '"y"' in completion_labels, "Should suggest 'y' parameter"

        # Check that completions have proper format
        for completion in completions:
            assert completion.label.startswith('"'), (
                "Parameter suggestions should start with quote"
            )
            assert completion.label.endswith('"'), "Parameter suggestions should end with quote"
            assert completion.insert_text == completion.label, "Insert text should match label"

    def test_param_depends_with_existing_parameters(self):
        """Test that already used parameters are not suggested again."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=1)
    y = param.Integer(default=21)
    z = param.String(default="test")

    @param.depends("x",
    def tmp(self):
        ..."""

        server._analyze_document("file:///test.py", code_py)

        lines = [str(line) for line in code_py.split("\n")]
        position = Position(line=7, character=23)  # After "x", (the comma)

        completions = server._get_param_depends_completions("file:///test.py", lines, position)

        # Should only have y and z, not x since it's already used
        assert len(completions) == 2, f"Expected 2 completions, got {len(completions)}"

        completion_labels = [item.label for item in completions]
        assert '"x"' not in completion_labels, "Should not suggest already used 'x' parameter"
        assert '"y"' in completion_labels, "Should suggest 'y' parameter"
        assert '"z"' in completion_labels, "Should suggest 'z' parameter"

    def test_param_depends_multiline_decorator(self):
        """Test param.depends completion across multiple lines."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=1)
    y = param.Integer(default=21)

    @param.depends(
        "x",

    def tmp(self):
        ..."""

        server._analyze_document("file:///test.py", code_py)

        lines = [str(line) for line in code_py.split("\n")]
        position = Position(line=8, character=8)  # On the empty line inside decorator

        # Should still detect param.depends context
        is_in_depends = server._is_in_param_depends_decorator(lines, position)
        assert is_in_depends, "Should detect param.depends context across multiple lines"

        completions = server._get_param_depends_completions("file:///test.py", lines, position)

        # Should suggest y but not x (already used)
        assert len(completions) == 1, f"Expected 1 completion, got {len(completions)}"
        assert completions[0].label == '"y"', "Should suggest 'y' parameter"

    def test_param_depends_not_in_decorator_context(self):
        """Test that completions are not provided outside param.depends context."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=1)
    y = param.Integer(default=21)

    def tmp(self):
        # Regular method, not in decorator
        ..."""

        server._analyze_document("file:///test.py", code_py)

        lines = [str(line) for line in code_py.split("\n")]
        position = Position(line=7, character=8)  # Inside regular method

        # Should not detect param.depends context
        is_in_depends = server._is_in_param_depends_decorator(lines, position)
        assert not is_in_depends, "Should not detect param.depends context in regular method"

        completions = server._get_param_depends_completions("file:///test.py", lines, position)

        # Should not provide completions
        assert len(completions) == 0, (
            "Should not provide completions outside param.depends context"
        )

    def test_param_depends_completion_with_inheritance(self):
        """Test param.depends completion with inherited parameters."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class Base(param.Parameterized):
    base_param = param.String(default="base")

class Child(Base):
    child_param = param.Integer(default=42)

    @param.depends(
    def method(self):
        ..."""

        server._analyze_document("file:///test.py", code_py)

        lines = [str(line) for line in code_py.split("\n")]
        position = Position(line=9, character=18)  # After the opening parenthesis

        completions = server._get_param_depends_completions("file:///test.py", lines, position)

        # Should suggest both inherited and own parameters
        assert len(completions) == 2, f"Expected 2 completions, got {len(completions)}"

        completion_labels = [item.label for item in completions]
        assert '"base_param"' in completion_labels, "Should suggest inherited parameter"
        assert '"child_param"' in completion_labels, "Should suggest own parameter"

    def test_param_depends_ignores_commented_lines(self):
        """Test that commented param.depends lines are ignored."""
        server = ParamLanguageServer("test-server", "1.0.0")

        # Test line comment
        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=1)
    y = param.Integer(default=21)

    # @param.depends(
    def tmp(self):
        ..."""

        server._analyze_document("file:///test.py", code_py)

        lines = [str(line) for line in code_py.split("\n")]
        position = Position(line=7, character=18)  # After the commented @param.depends(

        # Should NOT detect param.depends context
        is_in_depends = server._is_in_param_depends_decorator(lines, position)
        assert not is_in_depends, "Should not detect param.depends context in commented line"

        # Should not provide param.depends completions
        completions = server._get_param_depends_completions("file:///test.py", lines, position)
        assert len(completions) == 0, "Should not provide completions for commented param.depends"

    def test_param_depends_ignores_inline_comments(self):
        """Test that inline commented param.depends are ignored."""
        server = ParamLanguageServer("test-server", "1.0.0")

        # Test inline comment
        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=1)
    y = param.Integer(default=21)

    def tmp(self):  # @param.depends(
        ..."""

        server._analyze_document("file:///test.py", code_py)

        lines = [str(line) for line in code_py.split("\n")]
        position = Position(line=7, character=30)  # After the inline commented @param.depends(

        # Should NOT detect param.depends context
        is_in_depends = server._is_in_param_depends_decorator(lines, position)
        assert not is_in_depends, "Should not detect param.depends context in inline comment"

        # Should not provide param.depends completions
        completions = server._get_param_depends_completions("file:///test.py", lines, position)
        assert len(completions) == 0, (
            "Should not provide completions for inline commented param.depends"
        )

    def test_extract_used_depends_parameters(self):
        """Test extraction of already used parameters from param.depends line."""
        server = ParamLanguageServer("test-server", "1.0.0")

        # Test different patterns of parameter usage
        test_cases = [
            ('    @param.depends("x", "y",', {"x", "y"}),
            ('    @param.depends("param1",', {"param1"}),
            ("    @param.depends('single_quote',", {"single_quote"}),
            ("    @param.depends(\"mixed\", 'quotes',", {"mixed", "quotes"}),
            ("    @param.depends(", set()),  # No parameters yet
        ]

        for line, expected_params in test_cases:
            used_params = server._extract_used_depends_parameters(line, len(line))
            assert used_params == expected_params, (
                f"For line '{line}', expected {expected_params}, got {used_params}"
            )
