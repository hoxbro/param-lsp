"""Test Parameter object attribute completion functionality."""

from __future__ import annotations

from lsprotocol.types import Position

from src.param_lsp.server import ParamLanguageServer


class TestParamObjectAttributeCompletion:
    """Test Parameter object attribute completion like P().param.x.default."""

    def test_param_object_attribute_completion_integer(self):
        """Test Parameter object attribute completion for Integer parameters."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=5, bounds=(0, 10), doc="An integer parameter")

# Test Parameter object attribute completion
P().param.x."""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion at end of P().param.x.
        position = Position(line=6, character=12)  # After "P().param.x."
        completions = server._get_param_object_attribute_completions(
            "file:///test.py", "P().param.x.", position.character
        )

        # Should have completions for Parameter attributes
        assert len(completions) > 10, f"Expected many completions, got {len(completions)}"

        completion_labels = [item.label for item in completions]

        # Check common Parameter attributes
        assert "default" in completion_labels, "Should suggest 'default' attribute"
        assert "doc" in completion_labels, "Should suggest 'doc' attribute"
        assert "name" in completion_labels, "Should suggest 'name' attribute"
        assert "label" in completion_labels, "Should suggest 'label' attribute"
        assert "owner" in completion_labels, "Should suggest 'owner' attribute"
        assert "allow_None" in completion_labels, "Should suggest 'allow_None' attribute"

        # Check Integer-specific attributes
        assert "bounds" in completion_labels, "Should suggest 'bounds' attribute for Integer"
        assert "inclusive_bounds" in completion_labels, (
            "Should suggest 'inclusive_bounds' attribute for Integer"
        )
        assert "step" in completion_labels, "Should suggest 'step' attribute for Integer"

        # Check documentation
        default_completion = next((c for c in completions if c.label == "default"), None)
        bounds_completion = next((c for c in completions if c.label == "bounds"), None)

        assert default_completion is not None, "Should have completion for default"
        assert bounds_completion is not None, "Should have completion for bounds"
        assert isinstance(default_completion.documentation, str), "Documentation should be string"
        assert isinstance(bounds_completion.documentation, str), "Documentation should be string"
        assert "Default value" in default_completion.documentation, (
            "Should include description for default"
        )
        assert "Parameter type: Integer" in default_completion.documentation, (
            "Should include parameter type in documentation"
        )
        assert "Valid range for numeric values" in bounds_completion.documentation, (
            "Should include description for bounds"
        )

    def test_param_object_attribute_completion_string(self):
        """Test Parameter object attribute completion for String parameters."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    y = param.String(default="hello", doc="A string parameter")

# Test Parameter object attribute completion
P().param.y."""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion at end of P().param.y.
        position = Position(line=6, character=12)  # After "P().param.y."
        completions = server._get_param_object_attribute_completions(
            "file:///test.py", "P().param.y.", position.character
        )

        # Should have completions for Parameter attributes
        assert len(completions) > 10, f"Expected many completions, got {len(completions)}"

        completion_labels = [item.label for item in completions]

        # Check common Parameter attributes
        assert "default" in completion_labels, "Should suggest 'default' attribute"
        assert "doc" in completion_labels, "Should suggest 'doc' attribute"
        assert "name" in completion_labels, "Should suggest 'name' attribute"

        # Check String-specific attributes
        assert "regex" in completion_labels, "Should suggest 'regex' attribute for String"

        # Should NOT have Integer-specific attributes
        assert "bounds" not in completion_labels, (
            "Should NOT suggest 'bounds' attribute for String"
        )
        assert "step" not in completion_labels, "Should NOT suggest 'step' attribute for String"

        # Check documentation for String-specific attribute
        regex_completion = next((c for c in completions if c.label == "regex"), None)
        assert regex_completion is not None, "Should have completion for regex"
        assert isinstance(regex_completion.documentation, str), "Documentation should be string"
        assert "Regular expression pattern" in regex_completion.documentation, (
            "Should include description for regex"
        )
        assert "Parameter type: String" in regex_completion.documentation, (
            "Should include parameter type in documentation"
        )

    def test_param_object_attribute_completion_partial_typing(self):
        """Test Parameter object attribute completion with partial typing."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=5, doc="An integer parameter")

# Test partial typing
P().param.x.de"""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion after partial typing "de"
        position = Position(line=6, character=14)  # After "P().param.x.de"
        completions = server._get_param_object_attribute_completions(
            "file:///test.py", "P().param.x.de", position.character
        )

        # Should only suggest attributes that start with "de"
        completion_labels = [item.label for item in completions]
        assert "default" in completion_labels, "Should suggest 'default' attribute"
        # Should not suggest attributes that don't start with "de"
        assert "doc" not in completion_labels, "Should NOT suggest 'doc' attribute"
        assert "name" not in completion_labels, "Should NOT suggest 'name' attribute"

    def test_param_object_attribute_completion_invalid_parameter(self):
        """Test that no completions are returned for invalid parameter names."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=5)

# Test completion for non-existent parameter
P().param.nonexistent."""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion for invalid parameter name
        position = Position(line=6, character=21)  # After "P().param.nonexistent."
        completions = server._get_param_object_attribute_completions(
            "file:///test.py", "P().param.nonexistent.", position.character
        )

        # Should not have any completions for invalid parameter
        assert len(completions) == 0, (
            f"Expected 0 completions for invalid parameter, got {len(completions)}"
        )

    def test_param_object_attribute_completion_no_match(self):
        """Test that no completions are returned when not in Parameter object context."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=5)

# Not in Parameter object context
obj = P()
obj.x."""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion after just "obj.x."
        position = Position(line=7, character=6)  # After "obj.x."
        completions = server._get_param_object_attribute_completions(
            "file:///test.py", "obj.x.", position.character
        )

        # Should not have any completions
        assert len(completions) == 0, f"Expected 0 completions, got {len(completions)}"

    def test_param_object_attribute_completion_unknown_class(self):
        """Test Parameter object attribute completion for unknown class."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
# Unknown class
UnknownClass().param.x."""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion for unknown class
        position = Position(line=1, character=23)  # After "UnknownClass().param.x."
        completions = server._get_param_object_attribute_completions(
            "file:///test.py", "UnknownClass().param.x.", position.character
        )

        # Should not have any completions for unknown class
        assert len(completions) == 0, (
            f"Expected 0 completions for unknown class, got {len(completions)}"
        )
