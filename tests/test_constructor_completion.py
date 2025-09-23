"""Test constructor parameter completion functionality."""

from __future__ import annotations

import pytest
from lsprotocol.types import Position

from src.param_lsp.server import ParamLanguageServer


class TestConstructorCompletion:
    """Test constructor parameter completion."""

    def test_constructor_parameter_completion_basic(self):
        """Test basic constructor parameter completion functionality."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=1, doc="An integer parameter")
    y = param.String(default="hello", doc="A string parameter")

# Test constructor completion
P("""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion at end of P(
        position = Position(line=7, character=2)  # After P(
        completions = server._get_constructor_parameter_completions(
            "file:///test.py", "P(", position.character
        )

        # Should have completions for both x and y parameters
        assert len(completions) == 2, f"Expected 2 completions, got {len(completions)}"

        completion_labels = [item.label for item in completions]
        completion_inserts = [item.insert_text for item in completions]

        # Check that we get parameter assignments
        assert "x=1" in completion_labels, "Should suggest 'x=1' with default value"
        assert 'y="hello"' in completion_labels, (
            "Should suggest 'y=\"hello\"' with quoted string value"
        )
        assert "x=1" in completion_inserts, "Should insert 'x=1'"
        assert 'y="hello"' in completion_inserts, "Should insert quoted string assignment"

    def test_constructor_completion_after_equals(self):
        """Test constructor parameter completion when user has typed 'x='."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=42, doc="An integer parameter")
    y = param.String(default="test", doc="A string parameter")

# Test completion after typing parameter name and equals
P(x="""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion at end of P(x=
        position = Position(line=7, character=4)  # After P(x=
        completions = server._get_constructor_parameter_completions(
            "file:///test.py", "P(x=", position.character
        )

        # Should suggest the default value for x, not the parameter name again
        assert len(completions) == 1, f"Expected 1 completion, got {len(completions)}"

        completion = completions[0]
        assert completion.insert_text == "42", "Should insert only the default value '42'"
        assert completion.label == "x=42", "Label should show 'x=42'"

    def test_constructor_completion_mixed_parameters(self):
        """Test constructor completion with some parameters already provided."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=1)
    y = param.String(default="hello")
    z = param.Boolean(default=True)

# Test completion with one parameter already provided
P(x=5, """

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion after existing parameter
        position = Position(line=7, character=7)  # After P(x=5,
        completions = server._get_constructor_parameter_completions(
            "file:///test.py", "P(x=5, ", position.character
        )

        # Should suggest y and z but not x (already used)
        assert len(completions) == 2, f"Expected 2 completions, got {len(completions)}"

        completion_labels = [item.label for item in completions]
        assert 'y="hello"' in completion_labels, "Should suggest 'y=\"hello\"' with quoted string"
        assert "z=True" in completion_labels, "Should suggest 'z=True'"
        assert "x=1" not in completion_labels, "Should not suggest already used 'x'"

    def test_constructor_completion_no_defaults(self):
        """Test constructor completion for parameters without default values."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer()  # No default
    y = param.String()   # No default

# Test constructor completion
P("""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion at end of P(
        position = Position(line=6, character=2)  # After P(
        completions = server._get_constructor_parameter_completions(
            "file:///test.py", "P(", position.character
        )

        # Should have completions for both parameters
        assert len(completions) == 2, f"Expected 2 completions, got {len(completions)}"

        completion_labels = [item.label for item in completions]
        completion_inserts = [item.insert_text for item in completions]

        # Should suggest parameter names with equals
        assert "x" in completion_labels, "Should suggest 'x'"
        assert "y" in completion_labels, "Should suggest 'y'"
        assert "x=" in completion_inserts, "Should insert 'x='"
        assert "y=" in completion_inserts, "Should insert 'y='"

    def test_constructor_completion_after_equals_no_default(self):
        """Test completion when user typed 'x=' but parameter has no default."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer()  # No default
    y = param.String(default="test")

# Test completion after typing parameter name and equals
P(x="""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion at end of P(x=
        position = Position(line=6, character=4)  # After P(x=
        completions = server._get_constructor_parameter_completions(
            "file:///test.py", "P(x=", position.character
        )

        # Should not suggest anything since x has no default value
        assert len(completions) == 0, f"Expected 0 completions, got {len(completions)}"

    def test_constructor_completion_inheritance(self):
        """Test constructor completion with inherited parameters."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class Base(param.Parameterized):
    base_param = param.String(default="base")

class Child(Base):
    child_param = param.Integer(default=42)

# Test constructor completion
Child("""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion for Child constructor
        position = Position(line=9, character=6)  # After Child(
        completions = server._get_constructor_parameter_completions(
            "file:///test.py", "Child(", position.character
        )

        # Should suggest both inherited and own parameters
        assert len(completions) == 2, f"Expected 2 completions, got {len(completions)}"

        completion_labels = [item.label for item in completions]
        assert 'base_param="base"' in completion_labels, (
            "Should suggest inherited parameter with quoted string"
        )
        assert "child_param=42" in completion_labels, "Should suggest own parameter"

    def test_constructor_completion_with_bounds_info(self):
        """Test that completion includes bounds information in documentation."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=5, bounds=(0, 10), doc="An integer with bounds")
    y = param.Number(default=1.5, bounds=(0.0, 5.0), inclusive_bounds=(False, True))

# Test constructor completion
P("""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion at end of P(
        position = Position(line=6, character=2)  # After P(
        completions = server._get_constructor_parameter_completions(
            "file:///test.py", "P(", position.character
        )

        # Check that completions include bounds information in documentation
        x_completion = next((c for c in completions if c.label == "x=5"), None)
        y_completion = next((c for c in completions if c.label == "y=1.5"), None)

        assert x_completion is not None, "Should have completion for x"
        assert y_completion is not None, "Should have completion for y"

        assert isinstance(x_completion.documentation, str), "Documentation should be a string"
        assert isinstance(y_completion.documentation, str), "Documentation should be a string"
        assert "Bounds: [0, 10]" in x_completion.documentation, "Should include bounds info for x"
        assert "Bounds: (0.0, 5.0]" in y_completion.documentation, (
            "Should include bounds info for y"
        )
        assert "An integer with bounds" in x_completion.documentation, (
            "Should include parameter doc"
        )

    def test_constructor_completion_different_import_styles(self):
        """Test constructor completion with different param import styles."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param as p

class P(p.Parameterized):
    x = p.Integer(default=42)

# Test constructor completion
P("""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion with param imported as 'p'
        position = Position(line=6, character=2)  # After P(
        completions = server._get_constructor_parameter_completions(
            "file:///test.py", "P(", position.character
        )

        # Should still work with aliased import
        assert len(completions) == 1, f"Expected 1 completion, got {len(completions)}"
        assert completions[0].label == "x=42", "Should suggest 'x=42' with aliased import"

    def test_external_class_constructor_completion(self):
        """Test constructor completion for external classes like hv.Curve."""
        pytest.importorskip("holoviews")

        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import holoviews as hv

hv.Curve("""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion after hv.Curve(
        position = Position(line=2, character=9)  # After "hv.Curve("
        completions = server._get_constructor_parameter_completions(
            "file:///test.py", "hv.Curve(", position.character
        )

        # Should have completions for hv.Curve parameters
        assert len(completions) > 0, "Should have completions for hv.Curve parameters"

        completion_labels = [item.label for item in completions]
        # HoloViews Curve should have parameters like 'name', 'label', 'group', etc.
        assert any("label" in label for label in completion_labels), (
            "Should suggest label parameter for hv.Curve"
        )
        # Should have 7 main parameters (name is filtered out)
        assert len(completions) >= 7, (
            f"Should suggest at least 7 parameters, got {len(completions)}"
        )
        # Should NOT suggest name parameter (it's filtered out for constructors)
        assert not any("name" in label for label in completion_labels), (
            "Should NOT suggest name parameter for hv.Curve constructors"
        )

    def test_constructor_completion_no_duplicate_parameters(self):
        """Test that already-used parameters are not suggested again."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param


class P(param.Parameterized):
    x = param.Integer(default=1, allow_None=True)
    y = param.Integer(default=21)

P(x=1, y=21, """

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion after both parameters are already used
        line = "P(x=1, y=21, "
        completions = server._get_constructor_parameter_completions(
            "file:///test.py", line, len(line)
        )

        # Should not suggest any parameters since both x and y are already used
        # (name parameter is filtered out for constructors)
        assert len(completions) == 0, f"Expected 0 completions, got {len(completions)}"

        completion_labels = [item.label for item in completions]
        assert "x=1" not in completion_labels, "Should NOT suggest 'x=1' - already used"
        assert "y=21" not in completion_labels, "Should NOT suggest 'y=21' - already used"
