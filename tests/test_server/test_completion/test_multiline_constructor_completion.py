"""Test multiline constructor parameter completion functionality."""

from __future__ import annotations

from lsprotocol.types import Position

from param_lsp.server import ParamLanguageServer


class TestMultilineConstructorCompletion:
    """Test multiline constructor parameter completion."""

    def test_multiline_constructor_completion_basic(self):
        """Test basic multiline constructor parameter completion functionality."""
        test_server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class MyClass(param.Parameterized):
    width = param.Integer(default=100, bounds=(1, 1000))
    height = param.Integer(default=50, bounds=(1, 500))

instance = MyClass(

)
"""

        # Simulate document analysis
        uri = "file:///test.py"
        test_server._analyze_document(uri, code_py)

        lines = code_py.split("\n")

        # Test completion on the empty line inside the constructor (line 7, character 0)
        position = Position(line=7, character=0)

        # Test multiline constructor context detection
        is_multiline, class_name = test_server._is_in_constructor_context_multiline(
            uri, lines, position
        )

        assert is_multiline, "Should detect multiline constructor context"
        assert class_name == "MyClass", f"Should identify MyClass, got {class_name}"

        # Test getting completions via the multiline method
        completions = test_server._get_constructor_parameter_completions_multiline(
            uri, lines, position, class_name
        )

        # Should have completions for both width and height parameters
        assert len(completions) == 2, f"Expected 2 completions, got {len(completions)}"

        completion_labels = [item.label for item in completions]
        completion_inserts = [item.insert_text for item in completions]

        # Check that we get parameter assignments
        assert "width=100" in completion_labels, "Should suggest 'width=100' with default value"
        assert "height=50" in completion_labels, "Should suggest 'height=50' with default value"
        assert "width=100" in completion_inserts, "Should insert 'width=100'"
        assert "height=50" in completion_inserts, "Should insert 'height=50'"

    def test_multiline_constructor_completion_via_server(self):
        """Test multiline constructor completion through the full server completion flow."""
        test_server = ParamLanguageServer("test-server", "1.0.0")

        uri = "file:///test_multiline.py"
        code_py = """\
import param

class Widget(param.Parameterized):
    name = param.String(default="widget", doc="Widget name")
    enabled = param.Boolean(default=True, doc="Whether enabled")

my_widget = Widget(

)
"""

        # Simulate document analysis
        test_server._analyze_document(uri, code_py)

        # Test completion on the empty line inside the constructor
        position = Position(line=7, character=0)

        lines = code_py.split("\n")

        # Test multiline constructor context detection
        is_multiline, class_name = test_server._is_in_constructor_context_multiline(
            uri, lines, position
        )

        assert is_multiline, "Should detect multiline constructor context"
        assert class_name == "Widget", f"Should identify Widget, got {class_name}"

        # Get completions via the multiline method
        completions = test_server._get_constructor_parameter_completions_multiline(
            uri, lines, position, class_name
        )

        # Should get completions for name and enabled (but not 'name' since it's skipped)
        assert len(completions) == 1, (
            f"Expected 1 completion (enabled only), got {len(completions)}"
        )

        completion_labels = [item.label for item in completions]
        assert "enabled=True" in completion_labels, "Should suggest 'enabled=True'"

    def test_multiline_constructor_with_existing_params(self):
        """Test multiline constructor completion when some parameters are already used."""
        test_server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class Settings(param.Parameterized):
    threshold = param.Number(default=0.5, bounds=(0, 1))
    mode = param.String(default="auto")
    debug = param.Boolean(default=False)

config = Settings(
    threshold=0.8,

)
"""

        # Simulate document analysis
        uri = "file:///settings.py"
        test_server._analyze_document(uri, code_py)

        lines = code_py.split("\n")

        # Test completion on the empty line inside the constructor (line 9, character 0)
        position = Position(line=9, character=0)

        # Test multiline constructor context detection
        is_multiline, class_name = test_server._is_in_constructor_context_multiline(
            uri, lines, position
        )

        assert is_multiline, "Should detect multiline constructor context"
        assert class_name == "Settings", f"Should identify Settings, got {class_name}"

        # Test getting completions
        completions = test_server._get_constructor_parameter_completions_multiline(
            uri, lines, position, class_name
        )

        # Should only suggest unused parameters (mode and debug, not threshold)
        completion_labels = [item.label for item in completions]

        assert "threshold" not in [label.split("=")[0] for label in completion_labels], (
            "Should not suggest already used 'threshold'"
        )
        assert any("mode=" in label for label in completion_labels), "Should suggest 'mode'"
        assert any("debug=" in label for label in completion_labels), "Should suggest 'debug'"

    def test_multiline_constructor_complex_nesting(self):
        """Test multiline constructor completion with complex parentheses nesting."""
        test_server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class ComplexClass(param.Parameterized):
    value = param.Integer(default=42)

# Complex nesting case
result = ComplexClass(
    # This should still work despite the complex context

)
"""

        # Simulate document analysis
        uri = "file:///complex.py"
        test_server._analyze_document(uri, code_py)

        lines = code_py.split("\n")

        # Test completion on the empty line inside the constructor (line 8, character 0)
        position = Position(line=8, character=0)

        # Test multiline constructor context detection
        is_multiline, class_name = test_server._is_in_constructor_context_multiline(
            uri, lines, position
        )

        assert is_multiline, "Should detect multiline constructor context even with comments"
        assert class_name == "ComplexClass", f"Should identify ComplexClass, got {class_name}"

        # Test getting completions
        completions = test_server._get_constructor_parameter_completions_multiline(
            uri, lines, position, class_name
        )

        # Should have completion for value parameter
        assert len(completions) == 1, f"Expected 1 completion, got {len(completions)}"

        completion_labels = [item.label for item in completions]
        assert "value=42" in completion_labels, "Should suggest 'value=42'"

    def test_multiline_constructor_unfinished_parenthesis(self):
        """Test multiline constructor completion with unfinished parenthesis and comments."""
        test_server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param


class MyClass(param.Parameterized):
    width = param.Integer(default=100, bounds=(1, 1000))


instance = MyClass(

    # test
"""

        # Simulate document analysis
        uri = "file:///unfinished.py"
        test_server._analyze_document(uri, code_py)

        lines = code_py.split("\n")

        # Test completion after the comment line (line 10, character 0)
        position = Position(line=10, character=0)

        # Test multiline constructor context detection
        is_multiline, class_name = test_server._is_in_constructor_context_multiline(
            uri, lines, position
        )

        assert is_multiline, (
            "Should detect multiline constructor context with unfinished parenthesis"
        )
        assert class_name == "MyClass", f"Should identify MyClass, got {class_name}"

        # Test getting completions
        completions = test_server._get_constructor_parameter_completions_multiline(
            uri, lines, position, class_name
        )

        # Should have completion for width parameter
        assert len(completions) == 1, f"Expected 1 completion, got {len(completions)}"

        completion_labels = [item.label for item in completions]
        assert "width=100" in completion_labels, "Should suggest 'width=100'"

    def test_not_in_multiline_constructor_context(self):
        """Test that multiline detection correctly identifies when NOT in constructor context."""
        test_server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class SomeClass(param.Parameterized):
    param1 = param.String(default="test")

# Not in constructor context
x = 5

def some_function():
    pass
"""

        # Simulate document analysis
        uri = "file:///not_constructor.py"
        test_server._analyze_document(uri, code_py)

        lines = code_py.split("\n")

        # Test at a position that's clearly not in a constructor
        position = Position(line=7, character=0)  # Line with "def some_function():"

        # Test multiline constructor context detection
        is_multiline, class_name = test_server._is_in_constructor_context_multiline(
            uri, lines, position
        )

        assert not is_multiline, "Should NOT detect multiline constructor context"
        assert class_name is None, "Should not identify any class name"
