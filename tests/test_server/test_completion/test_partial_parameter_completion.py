"""Test partial parameter completion functionality."""

from __future__ import annotations

from lsprotocol.types import Position, TextEdit

from param_lsp.server import ParamLanguageServer


class TestPartialParameterCompletion:
    """Test partial parameter completion features."""

    def test_partial_parameter_completion_basic(self):
        """Test that 'w=' completes to 'width=100' not 'w=width=100'."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param


class MyClass(param.Parameterized):
    width = param.Integer(default=100, bounds=(1, 1000))


instance = MyClass(w="""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion at end of w=
        line = "instance = MyClass(w="
        position = Position(line=7, character=len(line))
        completions = server._get_constructor_parameter_completions(
            "file:///test.py", line, position
        )

        # Should have exactly one completion for width
        assert len(completions) == 1, f"Expected 1 completion, got {len(completions)}"

        completion = completions[0]
        assert completion.label == "width=100", f"Expected 'width=100', got '{completion.label}'"
        assert completion.insert_text is None, "Should not use insert_text when using text_edit"
        assert completion.text_edit is not None, "Should have text_edit for replacing partial text"

        # Verify the text_edit replaces "w=" with "width=100"
        text_edit = completion.text_edit
        assert hasattr(text_edit, "new_text"), "text_edit should have new_text attribute"
        assert text_edit.new_text == "width=100", (
            f"Expected 'width=100', got '{text_edit.new_text}'"
        )

        # The range should cover just the "w=" part
        expected_start = line.rfind("w=")  # Position where "w=" starts
        expected_end = len(line)  # End of the line (after "=")

        # Check if it's a TextEdit (which has a 'range' attribute)
        if isinstance(text_edit, TextEdit):
            assert text_edit.range.start.character == expected_start, (
                f"Expected range start at {expected_start}, got {text_edit.range.start.character}"
            )
            assert text_edit.range.end.character == expected_end, (
                f"Expected range end at {expected_end}, got {text_edit.range.end.character}"
            )

    def test_partial_parameter_completion_no_default(self):
        """Test partial completion for parameter without default value."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param


class MyClass(param.Parameterized):
    width = param.Integer()  # No default value


instance = MyClass(w="""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion at end of w=
        line = "instance = MyClass(w="
        position = Position(line=7, character=len(line))
        completions = server._get_constructor_parameter_completions(
            "file:///test.py", line, position
        )

        # Should have exactly one completion for width
        assert len(completions) == 1, f"Expected 1 completion, got {len(completions)}"

        completion = completions[0]
        assert completion.label == "width", f"Expected 'width', got '{completion.label}'"
        assert completion.insert_text is None, "Should not use insert_text when using text_edit"
        assert completion.text_edit is not None, "Should have text_edit for replacing partial text"

        # Verify the text_edit replaces "w=" with "width="
        text_edit = completion.text_edit
        assert hasattr(text_edit, "new_text"), "text_edit should have new_text attribute"
        assert text_edit.new_text == "width=", f"Expected 'width=', got '{text_edit.new_text}'"

    def test_partial_parameter_multiple_matches(self):
        """Test partial completion when multiple parameters start with same prefix."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param


class MyClass(param.Parameterized):
    width = param.Integer(default=100)
    weight = param.Number(default=50.0)


instance = MyClass(w="""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion at end of w=
        line = "instance = MyClass(w="
        position = Position(line=8, character=len(line))
        completions = server._get_constructor_parameter_completions(
            "file:///test.py", line, position
        )

        # Should match the first parameter that starts with "w" (alphabetically: weight comes before width)
        assert len(completions) == 1, f"Expected 1 completion, got {len(completions)}"

        completion = completions[0]
        # Should complete to the first matching parameter (weight comes before width alphabetically)
        # Note: The actual order depends on the iteration order of class_info.get_parameter_names()
        assert completion.label in ["weight=50.0", "width=100"], (
            f"Expected completion for weight or width, got '{completion.label}'"
        )
        assert completion.text_edit is not None, "Should have text_edit for replacing partial text"

    def test_partial_parameter_completion_no_match(self):
        """Test partial completion when no parameter matches the prefix."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param


class MyClass(param.Parameterized):
    height = param.Integer(default=100)


instance = MyClass(w="""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion at end of w=
        line = "instance = MyClass(w="
        position = Position(line=7, character=len(line))
        completions = server._get_constructor_parameter_completions(
            "file:///test.py", line, position
        )

        # Should fall back to normal parameter completion (showing all available parameters)
        assert len(completions) == 1, f"Expected 1 completion, got {len(completions)}"

        completion = completions[0]
        assert completion.label == "height=100", f"Expected 'height=100', got '{completion.label}'"
        # This should use normal insert_text, not text_edit since it's not a partial match
        assert completion.insert_text == "height=100", (
            "Should use insert_text for normal completions"
        )
        assert completion.text_edit is None, "Should not use text_edit for normal completions"

    def test_partial_parameter_with_spaces(self):
        """Test partial completion with spaces around the equals sign."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param


class MyClass(param.Parameterized):
    width = param.Integer(default=100)


instance = MyClass(w ="""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion at end of "w ="
        line = "instance = MyClass(w ="
        position = Position(line=7, character=len(line))
        completions = server._get_constructor_parameter_completions(
            "file:///test.py", line, position
        )

        # Should handle spaces correctly
        assert len(completions) == 1, f"Expected 1 completion, got {len(completions)}"

        completion = completions[0]
        assert completion.label == "width=100", f"Expected 'width=100', got '{completion.label}'"
        assert completion.text_edit is not None, "Should have text_edit for replacing partial text"

        # The text_edit should replace "w =" with "width=100"
        text_edit = completion.text_edit
        assert hasattr(text_edit, "new_text"), "text_edit should have new_text attribute"
        assert text_edit.new_text == "width=100", (
            f"Expected 'width=100', got '{text_edit.new_text}'"
        )
