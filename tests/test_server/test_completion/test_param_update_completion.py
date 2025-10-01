"""Test param.update() completion functionality."""

from __future__ import annotations

import pytest
from lsprotocol.types import CompletionItemKind, Position

from param_lsp.server import ParamLanguageServer


class TestParamUpdateCompletion:
    """Test param.update() completion functionality."""

    def test_param_attribute_completion_includes_update_method(self):
        """Test that update() method appears in param attribute completions."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=1)
    y = param.String(default="hello")

# Test param attribute completion
P().param."""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion at end of P().param.
        position = Position(line=7, character=10)  # After "P().param."
        completions = server._get_param_attribute_completions(
            "file:///test.py", "P().param.", position.character
        )

        # Should have completions for methods (including update) and parameters
        assert len(completions) == 5, (
            f"Expected 5 completions (3 methods + 2 parameters), got {len(completions)}"
        )

        completion_labels = [item.label for item in completions]
        assert "update()" in completion_labels, "Should suggest 'update()' method"
        assert "objects()" in completion_labels, "Should suggest 'objects()' method"
        assert "values()" in completion_labels, "Should suggest 'values()' method"
        assert "x" in completion_labels, "Should suggest 'x' parameter"
        assert "y" in completion_labels, "Should suggest 'y' parameter"

        # Check that update method has correct documentation
        update_completion = next((c for c in completions if c.label == "update()"), None)
        assert update_completion is not None, "Should have completion for update()"
        assert update_completion.kind == CompletionItemKind.Method, "update() should be a method"
        assert isinstance(update_completion.documentation, str), "Documentation should be a string"
        assert "Update multiple parameters at once" in update_completion.documentation

    def test_param_update_completion_basic(self):
        """Test basic param.update() parameter completion functionality."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=1, doc="An integer parameter")
    y = param.String(default="hello", doc="A string parameter")

# Test param.update() completion
P().param.update("""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion inside update parentheses
        position = Position(line=7, character=17)  # After "P().param.update("
        completions = server._get_param_update_completions(
            "file:///test.py", "P().param.update(", position.character
        )

        # Should have completions for both parameters (name is skipped)
        assert len(completions) == 2, f"Expected 2 completions, got {len(completions)}"

        completion_labels = [item.label for item in completions]
        assert any("x=" in label for label in completion_labels), (
            "Should suggest 'x' parameter as keyword"
        )
        assert any("y=" in label for label in completion_labels), (
            "Should suggest 'y' parameter as keyword"
        )

        # Check that completions have correct insert text with equals and defaults
        x_completion = next((c for c in completions if "x=" in c.label), None)
        y_completion = next((c for c in completions if "y=" in c.label), None)

        assert x_completion is not None, "Should have completion for x"
        assert y_completion is not None, "Should have completion for y"

        assert x_completion.insert_text == "x=1", "Should insert parameter with default value"
        assert y_completion.insert_text == 'y="hello"', (
            "Should insert parameter with default value"
        )

        # Check documentation includes type information
        assert isinstance(x_completion.documentation, str), "Documentation should be a string"
        assert isinstance(y_completion.documentation, str), "Documentation should be a string"
        assert "Integer" in x_completion.documentation, "Should include parameter type for x"
        assert "String" in y_completion.documentation, "Should include parameter type for y"

    def test_param_update_completion_partial_typing(self):
        """Test param.update() completion with partial parameter typing."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x_value = param.Integer(default=1)
    y_value = param.String(default="hello")
    z_other = param.Boolean(default=True)

# Test partial typing in update - this would happen during actual typing
P().param.update(x"""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion after partial typing 'x' - this tests the filtering logic
        # but the actual filtering happens at the LSP client level based on filter_text
        position = Position(line=8, character=18)  # After 'P().param.update(x'
        completions = server._get_param_update_completions(
            "file:///test.py", "P().param.update(x", position.character
        )

        # Should suggest all parameters since server-side filtering may not apply
        # The client will filter based on 'x' prefix using filter_text
        assert len(completions) == 3, f"Expected 3 completions, got {len(completions)}"

        # Check that x_value parameter exists in completions
        x_completion = next((c for c in completions if "x_value" in c.label), None)
        assert x_completion is not None, "Should have completion for x_value"
        assert x_completion.filter_text == "x_value", "Filter text should be parameter name"

    def test_param_update_completion_inheritance(self):
        """Test param.update() completion with inherited parameters."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class Base(param.Parameterized):
    base_param = param.String(default="base")

class Child(Base):
    child_param = param.Integer(default=42)

# Test completion with inheritance in update
Child().param.update("""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion for Child instance
        position = Position(line=9, character=21)  # After "Child().param.update("
        completions = server._get_param_update_completions(
            "file:///test.py", "Child().param.update(", position.character
        )

        # Should suggest both inherited and own parameters
        assert len(completions) == 2, f"Expected 2 completions, got {len(completions)}"

        completion_labels = [item.label for item in completions]
        assert any("base_param=" in label for label in completion_labels), (
            "Should suggest inherited parameter"
        )
        assert any("child_param=" in label for label in completion_labels), (
            "Should suggest own parameter"
        )

    def test_param_update_completion_external_class(self):
        """Test param.update() completion for external classes."""
        pytest.importorskip("holoviews")

        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import holoviews as hv

# Test completion on external class update
hv.Curve([]).param.update("""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion after hv.Curve([]).param.update(
        position = Position(line=3, character=26)  # After "hv.Curve([]).param.update("
        completions = server._get_param_update_completions(
            "file:///test.py", "hv.Curve([]).param.update(", position.character
        )

        # Should have completions for hv.Curve parameters
        assert len(completions) > 0, "Should have completions for hv.Curve parameters"

        completion_labels = [item.label for item in completions]
        # HoloViews Curve should have parameters like 'group', 'label', etc.
        assert any("group=" in label for label in completion_labels), (
            "Should suggest group parameter for hv.Curve"
        )

    def test_param_update_completion_no_match(self):
        """Test that no completions are returned when not in param.update() context."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=1)

# Not in param.update context
obj = P()
obj.some_method("""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion after just "obj.some_method("
        position = Position(line=7, character=15)  # After "obj.some_method("
        completions = server._get_param_update_completions(
            "file:///test.py", "obj.some_method(", position.character
        )

        # Should not have any completions
        assert len(completions) == 0, f"Expected 0 completions, got {len(completions)}"

    def test_param_update_completion_with_bounds_and_docs(self):
        """Test that completion includes bounds and documentation in param.update()."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=5, bounds=(0, 10), doc="An integer with bounds")
    y = param.Number(default=1.5, bounds=(0.0, 5.0), inclusive_bounds=(False, True))
    z = param.String(default="test", allow_None=True, doc="A string parameter")

# Test completion in update
P().param.update("""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion
        position = Position(line=7, character=17)  # After "P().param.update("
        completions = server._get_param_update_completions(
            "file:///test.py", "P().param.update(", position.character
        )

        # Should have completions for all parameters
        assert len(completions) == 3, f"Expected 3 completions, got {len(completions)}"

        # Check specific parameter documentation
        x_completion = next((c for c in completions if "x=" in c.label), None)
        y_completion = next((c for c in completions if "y=" in c.label), None)
        z_completion = next((c for c in completions if "z=" in c.label), None)

        assert x_completion is not None, "Should have completion for x"
        assert y_completion is not None, "Should have completion for y"
        assert z_completion is not None, "Should have completion for z"

        # Check x documentation
        assert isinstance(x_completion.documentation, str), "Documentation should be a string"
        assert "Type: Integer" in x_completion.documentation, "Should include type info for x"
        assert "Bounds: [0, 10]" in x_completion.documentation, "Should include bounds info for x"
        assert "An integer with bounds" in x_completion.documentation, (
            "Should include description for x"
        )

        # Check y documentation (different bounds format)
        assert isinstance(y_completion.documentation, str), "Documentation should be a string"
        assert "Bounds: (0.0, 5.0]" in y_completion.documentation, (
            "Should include bounds info for y"
        )

        # Check z documentation (allow_None)
        assert isinstance(z_completion.documentation, str), "Documentation should be a string"
        assert "Allows None" in z_completion.documentation, "Should include allow_None info for z"
        assert "A string parameter" in z_completion.documentation, (
            "Should include description for z"
        )

    def test_param_update_completion_skips_name_parameter(self):
        """Test that param.update() completion skips the 'name' parameter."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=1)
    y = param.String(default="hello")
    # The 'name' parameter is inherited from Parameterized

# Test completion in update
P().param.update("""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion
        position = Position(line=8, character=17)  # After "P().param.update("
        completions = server._get_param_update_completions(
            "file:///test.py", "P().param.update(", position.character
        )

        # Should have completions for x and y, but not name
        completion_labels = [item.label for item in completions]
        assert any("x=" in label for label in completion_labels), "Should suggest 'x' parameter"
        assert any("y=" in label for label in completion_labels), "Should suggest 'y' parameter"
        assert not any("name=" in label for label in completion_labels), (
            "Should not suggest 'name' parameter"
        )

    def test_param_update_completion_with_constructor_args(self):
        """Test param.update() completion on constructor with arguments."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=1)
    y = param.String(default="hello")

# Test completion on constructor call with arguments
P(x=5).param.update("""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion after P(x=5).param.update(
        position = Position(line=7, character=20)  # After "P(x=5).param.update("
        completions = server._get_param_update_completions(
            "file:///test.py", "P(x=5).param.update(", position.character
        )

        # Should have completions for all parameters (constructor args don't affect availability)
        # The implementation might filter out already used parameters from constructor
        assert len(completions) >= 1, f"Expected at least 1 completion, got {len(completions)}"

        completion_labels = [item.label for item in completions]
        # Should suggest available parameters - y should always be available
        assert any("y=" in label for label in completion_labels), "Should suggest 'y' parameter"

    def test_param_update_completion_unknown_class(self):
        """Test param.update() completion for unknown class."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
# Unknown class
UnknownClass().param.update("""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion for unknown class
        position = Position(line=1, character=28)  # After "UnknownClass().param.update("
        completions = server._get_param_update_completions(
            "file:///test.py", "UnknownClass().param.update(", position.character
        )

        # Should not have any completions for unknown class
        assert len(completions) == 0, f"Expected 0 completions, got {len(completions)}"

    def test_param_update_completion_avoid_duplicates(self):
        """Test param.update() completion avoids suggesting already used parameters."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=1)
    y = param.String(default="hello")
    z = param.Boolean(default=True)

# Test completion with one parameter already used
P().param.update(x=5, """

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion after x=5,
        position = Position(line=8, character=22)  # After "P().param.update(x=5, "
        completions = server._get_param_update_completions(
            "file:///test.py", "P().param.update(x=5, ", position.character
        )

        # Should have completions for y and z, but not x (already used)
        assert len(completions) == 2, f"Expected 2 completions, got {len(completions)}"

        completion_labels = [item.label for item in completions]
        assert any("y=" in label for label in completion_labels), "Should suggest 'y' parameter"
        assert any("z=" in label for label in completion_labels), "Should suggest 'z' parameter"
        assert not any("x=" in label for label in completion_labels), (
            "Should not suggest already used 'x' parameter"
        )
