"""Test smart parentheses detection for param namespace methods."""

from __future__ import annotations

from param_lsp.server import ParamLanguageServer


class TestParamMethodInsertText:
    """Test param namespace methods' smart insert_text behavior."""

    def test_param_objects_method_includes_parentheses_when_none_present(self):
        """Test that objects() method includes parentheses when none are already present."""
        server = ParamLanguageServer("param-lsp", "test")

        # Create test document
        test_content = """
import param

class MyClass(param.Parameterized):
    x = param.Integer(default=1)
    y = param.String(default="hello")

obj = MyClass()
result = obj.param.o  # cursor here - should suggest objects() with parentheses
"""

        uri = "file:///test.py"
        server._analyze_document(uri, test_content)

        # Get completions at the position after "obj.param.o"
        line = "result = obj.param.o"
        character = len(line)

        completions = server._get_param_attribute_completions(uri, line, character)

        # Find the objects completion
        objects_completion = None
        for completion in completions:
            if completion.filter_text == "objects":
                objects_completion = completion
                break

        assert objects_completion is not None, "objects method completion should be found"
        assert objects_completion.insert_text == "objects()", (
            f"Expected 'objects()', got '{objects_completion.insert_text}'"
        )
        assert objects_completion.label == "objects()", "Label should show parentheses"

    def test_param_objects_method_excludes_parentheses_when_already_present(self):
        """Test that objects() method excludes parentheses when they are already present."""
        server = ParamLanguageServer("param-lsp", "test")

        # Create test document
        test_content = """
import param

class MyClass(param.Parameterized):
    x = param.Integer(default=1)
    y = param.String(default="hello")

obj = MyClass()
result = obj.param.objects()  # cursor here - should suggest objects without parentheses
"""

        uri = "file:///test.py"
        server._analyze_document(uri, test_content)

        # Get completions at the position after "obj.param.objects()"
        line = "result = obj.param.objects()"
        character = len(line)

        completions = server._get_param_attribute_completions(uri, line, character)

        # Find the objects completion
        objects_completion = None
        for completion in completions:
            if completion.filter_text == "objects":
                objects_completion = completion
                break

        assert objects_completion is not None, "objects method completion should be found"
        assert objects_completion.insert_text == "objects", (
            f"Expected 'objects', got '{objects_completion.insert_text}'"
        )
        assert objects_completion.label == "objects()", "Label should still show parentheses"

    def test_param_values_method_smart_parentheses(self):
        """Test that values() method has smart parentheses detection."""
        server = ParamLanguageServer("param-lsp", "test")

        # Test case 1: No parentheses present - should include them
        test_content = """
import param

class MyClass(param.Parameterized):
    x = param.Integer(default=1)
    y = param.String(default="hello")

obj = MyClass()
result = obj.param.v  # cursor here - should suggest values() with parentheses
"""

        uri = "file:///test.py"
        server._analyze_document(uri, test_content)

        line = "result = obj.param.v"
        character = len(line)

        completions = server._get_param_attribute_completions(uri, line, character)

        values_completion = None
        for completion in completions:
            if completion.filter_text == "values":
                values_completion = completion
                break

        assert values_completion is not None, "values method completion should be found"
        assert values_completion.insert_text == "values()", (
            f"Expected 'values()', got '{values_completion.insert_text}'"
        )

        # Test case 2: Parentheses already present - should exclude them
        line = "result = obj.param.values()"
        character = len(line)

        completions = server._get_param_attribute_completions(uri, line, character)

        values_completion = None
        for completion in completions:
            if completion.filter_text == "values":
                values_completion = completion
                break

        assert values_completion is not None, "values method completion should be found"
        assert values_completion.insert_text == "values", (
            f"Expected 'values', got '{values_completion.insert_text}'"
        )

    def test_param_rx_method_smart_parentheses(self):
        """Test that rx property completion works correctly."""
        server = ParamLanguageServer("param-lsp", "test")

        test_content = """
import param

class MyClass(param.Parameterized):
    x = param.Integer(default=1)
    y = param.String(default="hello")

obj = MyClass()
"""

        uri = "file:///test.py"
        server._analyze_document(uri, test_content)

        # Test case 1: No parentheses present - should include them
        line = "result = obj.param.x.r"
        character = len(line)

        completions = server._get_param_object_attribute_completions(uri, line, character)

        rx_completion = None
        for completion in completions:
            if completion.filter_text == "rx":
                rx_completion = completion
                break

        assert rx_completion is not None, "rx property completion should be found"
        assert rx_completion.insert_text == "rx", (
            f"Expected 'rx', got '{rx_completion.insert_text}'"
        )

        # Test case 2: Property already completed
        line = "result = obj.param.x.rx"
        character = len(line)

        completions = server._get_param_object_attribute_completions(uri, line, character)

        rx_completion = None
        for completion in completions:
            if completion.filter_text == "rx":
                rx_completion = completion
                break

        assert rx_completion is not None, "rx method completion should be found"
        assert rx_completion.insert_text == "rx", (
            f"Expected 'rx', got '{rx_completion.insert_text}'"
        )

    def test_param_methods_clean_cursor_position(self):
        """Test that all param namespace methods work correctly at clean cursor positions."""
        server = ParamLanguageServer("param-lsp", "test")

        test_content = """
import param

class MyClass(param.Parameterized):
    x = param.Integer(default=1)
    y = param.String(default="hello")

obj = MyClass()
result = obj.param.  # cursor here - should show all methods with parentheses
"""

        uri = "file:///test.py"
        server._analyze_document(uri, test_content)

        line = "result = obj.param."
        character = len(line)

        completions = server._get_param_attribute_completions(uri, line, character)

        method_completions = {}
        for completion in completions:
            if completion.filter_text in ["objects", "values"]:
                method_completions[completion.filter_text] = completion

        assert "objects" in method_completions, "objects method should be suggested"
        assert "values" in method_completions, "values method should be suggested"

        # Should include parentheses when no parentheses are present
        assert method_completions["objects"].insert_text == "objects()"
        assert method_completions["values"].insert_text == "values()"

        # Labels should always show parentheses
        assert method_completions["objects"].label == "objects()"
        assert method_completions["values"].label == "values()"

    def test_reactive_expression_and_method_smart_parentheses(self):
        """Test that reactive expression and_() method has smart parentheses detection."""
        server = ParamLanguageServer("param-lsp", "test")

        test_content = """
import param

class MyClass(param.Parameterized):
    x = param.Integer(default=1)
    y = param.String(default="hello")

obj = MyClass()
"""

        uri = "file:///test.py"
        server._analyze_document(uri, test_content)

        # Test case 1: No parentheses present - should include them
        line = "result = obj.param.x.rx.and"
        character = len(line)

        completions = server._get_reactive_expression_completions(uri, line, character)

        and_completion = None
        for completion in completions:
            if completion.filter_text == "and_":
                and_completion = completion
                break

        assert and_completion is not None, "and_ method completion should be found"
        assert and_completion.insert_text == "and_()", (
            f"Expected 'and_()', got '{and_completion.insert_text}'"
        )
        assert and_completion.label == "and_()", "Label should show parentheses"

        # Test case 2: Parentheses already present - should exclude them
        line = "result = obj.param.x.rx.and_()"
        character = len(line)

        completions = server._get_reactive_expression_completions(uri, line, character)

        and_completion = None
        for completion in completions:
            if completion.filter_text == "and_":
                and_completion = completion
                break

        assert and_completion is not None, "and_ method completion should be found"
        assert and_completion.insert_text == "and_", (
            f"Expected 'and_', got '{and_completion.insert_text}'"
        )
        assert and_completion.label == "and_()", "Label should still show parentheses"

    def test_multiple_reactive_expression_methods_smart_parentheses(self):
        """Test that multiple reactive expression methods have smart parentheses detection."""
        server = ParamLanguageServer("param-lsp", "test")

        test_content = """
import param

class MyClass(param.Parameterized):
    x = param.Integer(default=1)
    y = param.String(default="hello")

obj = MyClass()
"""

        uri = "file:///test.py"
        server._analyze_document(uri, test_content)

        # Test clean case - should include parentheses
        line = "result = obj.param.x.rx."
        character = len(line)

        completions = server._get_reactive_expression_completions(uri, line, character)

        method_completions = {}
        for completion in completions:
            if completion.filter_text in ["and_", "or_", "map", "pipe", "when"]:
                method_completions[completion.filter_text] = completion

        # Should have found several methods
        assert len(method_completions) >= 3, "Should find multiple reactive expression methods"

        # All should include parentheses when none are present
        for method_name, completion in method_completions.items():
            assert completion.insert_text == f"{method_name}()", (
                f"Expected '{method_name}()' for {method_name}"
            )
            assert completion.label == f"{method_name}()", (
                f"Label should show parentheses for {method_name}"
            )

        # Test case with existing parentheses - should exclude them
        line = "result = obj.param.x.rx.and_()"
        character = len(line)

        completions = server._get_reactive_expression_completions(uri, line, character)

        and_completion = None
        for completion in completions:
            if completion.filter_text == "and_":
                and_completion = completion
                break

        assert and_completion is not None, "and_ method completion should be found"
        assert and_completion.insert_text == "and_", (
            "Should not include parentheses when already present"
        )
