"""Test reactive expression completion functionality."""

from __future__ import annotations

from lsprotocol.types import CompletionItemKind, Position

from param_lsp.server import ParamLanguageServer


class TestReactiveExpressionCompletion:
    """Test reactive expression completion like P().param.x.rx.method()."""

    def test_param_object_rx_method_completion(self):
        """Test that rx property is available on parameter objects."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=5, doc="An integer parameter")

# Test parameter object method completion
P().param.x."""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion at end of P().param.x.
        position = Position(line=6, character=12)  # After "P().param.x."
        completions = server._get_param_object_attribute_completions(
            "file:///test.py", "P().param.x.", position.character
        )

        # Should include rx property among other attributes
        completion_labels = [item.label for item in completions]
        assert "rx" in completion_labels, "Should suggest 'rx' property"

        # Check rx property details
        rx_completion = next((c for c in completions if c.label == "rx"), None)
        assert rx_completion is not None, "Should have completion for rx"
        assert rx_completion.kind == CompletionItemKind.Property, "rx should be a property"
        assert isinstance(rx_completion.documentation, str), "Documentation should be a string"
        assert "reactive expression" in rx_completion.documentation.lower()

    def test_reactive_expression_method_completions(self):
        """Test reactive expression method completions after P().param.x.rx."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=5)
    y = param.String(default="hello")

# Test reactive expression completions
P().param.x.rx."""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion at end of P().param.x.rx.
        position = Position(line=7, character=17)  # After "P().param.x.rx."
        completions = server._get_reactive_expression_completions(
            "file:///test.py", "P().param.x.rx.", position.character
        )

        # Should have completions for reactive expression methods
        assert len(completions) > 10, f"Expected many rx completions, got {len(completions)}"

        completion_labels = [item.label for item in completions]

        # Check that key reactive expression methods are included
        expected_methods = [
            "and_()",
            "bool()",
            "in_()",
            "is_()",
            "len()",
            "map()",
            "or_()",
            "pipe()",
            "watch()",
        ]
        for method in expected_methods:
            assert method in completion_labels, f"Should suggest '{method}' method"

        # Check that value property is included
        assert "value" in completion_labels, "Should suggest 'value' property"

        # Check method vs property kinds
        and_completion = next((c for c in completions if c.label == "and_()"), None)
        value_completion = next((c for c in completions if c.label == "value"), None)

        assert and_completion is not None, "Should have completion for and_()"
        assert value_completion is not None, "Should have completion for value"

        assert and_completion.kind == CompletionItemKind.Method, "and_() should be a method"
        assert value_completion.kind == CompletionItemKind.Property, "value should be a property"

    def test_reactive_expression_method_filtering(self):
        """Test that reactive expression method completions are filtered by partial text."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=5)

# Test partial reactive expression completion
P().param.x.rx.w"""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion after partial typing "w"
        position = Position(line=6, character=18)  # After "P().param.x.rx.w"
        completions = server._get_reactive_expression_completions(
            "file:///test.py", "P().param.x.rx.w", position.character
        )

        # Should only suggest methods that start with "w"
        completion_labels = [item.label for item in completions]
        assert "watch()" in completion_labels, "Should suggest 'watch()' method"
        assert "when()" in completion_labels, "Should suggest 'when()' method"
        assert "where()" in completion_labels, "Should suggest 'where()' method"

        # Should not suggest methods that don't start with "w"
        assert "and_()" not in completion_labels, "Should NOT suggest 'and_()' method"
        assert "bool()" not in completion_labels, "Should NOT suggest 'bool()' method"

    def test_reactive_expression_value_property_filtering(self):
        """Test filtering for the value property."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=5)

# Test partial reactive expression completion
P().param.x.rx.v"""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion after partial typing "v"
        position = Position(line=6, character=18)  # After "P().param.x.rx.v"
        completions = server._get_reactive_expression_completions(
            "file:///test.py", "P().param.x.rx.v", position.character
        )

        # Should suggest value property
        completion_labels = [item.label for item in completions]
        assert "value" in completion_labels, "Should suggest 'value' property"

    def test_reactive_expression_invalid_parameter(self):
        """Test that no reactive expression completions are returned for invalid parameter names."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=5)

# Test completion for non-existent parameter
P().param.nonexistent.rx."""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion for invalid parameter name
        position = Position(line=6, character=28)  # After "P().param.nonexistent.rx."
        completions = server._get_reactive_expression_completions(
            "file:///test.py", "P().param.nonexistent.rx.", position.character
        )

        # Should not have any completions for invalid parameter
        assert len(completions) == 0, (
            f"Expected 0 completions for invalid parameter, got {len(completions)}"
        )

    def test_reactive_expression_unknown_class(self):
        """Test reactive expression completions for unknown class."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
# Unknown class
UnknownClass().param.x.rx."""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion for unknown class
        position = Position(line=1, character=30)  # After "UnknownClass().param.x.rx."
        completions = server._get_reactive_expression_completions(
            "file:///test.py", "UnknownClass().param.x.rx.", position.character
        )

        # Should not have any completions for unknown class
        assert len(completions) == 0, (
            f"Expected 0 completions for unknown class, got {len(completions)}"
        )

    def test_reactive_expression_documentation_quality(self):
        """Test that reactive expression completions have good documentation."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    temperature = param.Number(default=20.0, doc="Temperature in celsius")

# Test reactive expression documentation
P().param.temperature.rx."""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test completion
        position = Position(line=6, character=28)  # After "P().param.temperature.rx."
        completions = server._get_reactive_expression_completions(
            "file:///test.py", "P().param.temperature.rx.", position.character
        )

        # Check documentation quality for various methods
        map_completion = next((c for c in completions if c.label == "map()"), None)
        watch_completion = next((c for c in completions if c.label == "watch()"), None)
        value_completion = next((c for c in completions if c.label == "value"), None)

        assert map_completion is not None, "Should have completion for map()"
        assert watch_completion is not None, "Should have completion for watch()"
        assert value_completion is not None, "Should have completion for value"

        # Check documentation contains expected info
        assert isinstance(map_completion.documentation, str), "Documentation should be a string"
        assert "Maps a function" in map_completion.documentation, "Should explain what map does"
        assert "temperature" in map_completion.documentation, "Should mention parameter name"

        assert isinstance(watch_completion.documentation, str), "Documentation should be a string"
        assert "side-effect" in watch_completion.documentation, "Should explain what watch does"

        assert isinstance(value_completion.documentation, str), "Documentation should be a string"
        assert "current value" in value_completion.documentation, (
            "Should explain what value property does"
        )


class TestReactiveExpressionHover:
    """Test hover information for reactive expressions."""

    def test_rx_method_hover(self):
        """Test hover information for the rx property."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=5)

# Test rx method hover
P().param.x.rx
"""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test hover for rx method
        hover_info = server._get_hover_info("file:///test.py", "P().param.x.rx", "rx")

        assert hover_info is not None, "Should have hover info for rx method"
        assert "**rx Property**" in hover_info, "Should have property title"
        assert "reactive expression" in hover_info.lower(), "Should mention reactive expressions"
        assert "https://param.holoviz.org/user_guide/Reactive_Expressions.html" in hover_info, (
            "Should include documentation link"
        )

    def test_reactive_expression_method_hover(self):
        """Test hover information for reactive expression methods."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=5)

# Test reactive expression method hover
P().param.x.rx.map(lambda x: x * 2)
"""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test hover for map method
        hover_info = server._get_hover_info(
            "file:///test.py", "P().param.x.rx.map(lambda x: x * 2)", "map"
        )

        assert hover_info is not None, "Should have hover info for map method"
        assert "**map(func, *args, **kwargs)**" in hover_info, "Should have method signature"
        assert "maps a function" in hover_info.lower(), "Should explain what map does"
        assert "param_rx.map" in hover_info, "Should have example usage"

    def test_reactive_expression_value_property_hover(self):
        """Test hover information for the value property."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    temperature = param.Number(default=20.0)

# Test reactive expression value property hover
current_temp = P().param.temperature.rx.value
"""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test hover for value property
        hover_info = server._get_hover_info(
            "file:///test.py", "P().param.temperature.rx.value", "value"
        )

        assert hover_info is not None, "Should have hover info for value property"
        assert "**value**" in hover_info, "Should have property title"
        assert "current value" in hover_info.lower(), "Should explain what value property does"
        assert "param_rx.value" in hover_info, "Should have example usage"

    def test_reactive_expression_multiple_methods_hover(self):
        """Test hover information for various reactive expression methods."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    flag = param.Boolean(default=True)

# Test various reactive expression methods
P().param.flag.rx.and_(other_condition)
P().param.flag.rx.watch(callback)
P().param.flag.rx.when(condition)
"""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test hover for and_ method
        hover_info = server._get_hover_info(
            "file:///test.py", "P().param.flag.rx.and_(other_condition)", "and_"
        )
        assert hover_info is not None, "Should have hover info for and_ method"
        assert "**and_(other)**" in hover_info, "Should have correct signature for and_"
        assert "`and` operator" in hover_info, "Should explain and_ functionality"

        # Test hover for watch method
        hover_info = server._get_hover_info(
            "file:///test.py", "P().param.flag.rx.watch(callback)", "watch"
        )
        assert hover_info is not None, "Should have hover info for watch method"
        assert "**watch(callback, onlychanged=True)**" in hover_info, (
            "Should have correct signature for watch"
        )
        assert "side-effect" in hover_info.lower(), "Should explain watch functionality"

        # Test hover for when method
        hover_info = server._get_hover_info(
            "file:///test.py", "P().param.flag.rx.when(condition)", "when"
        )
        assert hover_info is not None, "Should have hover info for when method"
        assert "**when(*conditions)**" in hover_info, "Should have correct signature for when"
        assert "conditions are met" in hover_info, "Should explain when functionality"

    def test_non_reactive_expression_context_no_hover(self):
        """Test that reactive expression method names outside of rx context don't get hover info."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=5)

# Test non-reactive context - should not get rx method hover
def map(items):
    return [item * 2 for item in items]

result = map([1, 2, 3])
"""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test that map outside rx context doesn't get rx hover info
        hover_info = server._get_hover_info("file:///test.py", "result = map([1, 2, 3])", "map")

        # Should not get reactive expression hover info for regular map function
        if hover_info is not None:
            assert "reactive expression" not in hover_info.lower(), (
                "Should not get rx hover info for regular map function"
            )

    def test_rx_method_context_detection(self):
        """Test that rx method is only detected in proper parameter context."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=5)

# Test proper rx context
P().param.x.rx

# Test non-parameter rx (should not get reactive hover)
def rx():
    return "not reactive"

result = rx()
"""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test rx in parameter context
        hover_info = server._get_hover_info("file:///test.py", "P().param.x.rx", "rx")
        assert hover_info is not None, "Should have hover info for parameter rx method"
        assert "reactive expression" in hover_info.lower(), "Should be about reactive expressions"

        # Test rx outside parameter context
        hover_info = server._get_hover_info("file:///test.py", "result = rx()", "rx")
        # Should not get reactive expression hover info for regular rx function
        if hover_info is not None:
            assert "reactive expression" not in hover_info.lower(), (
                "Should not get rx hover info for regular rx function"
            )


class TestParamNamespaceMethodHover:
    """Test hover information for param namespace methods like values() and objects()."""

    def test_param_values_method_hover(self):
        """Test hover information for obj.param.values() method."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=5)
    y = param.String(default="hello")

# Test param.values() method hover
for value in P().param.values():
    print(value)
"""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test hover for values method
        hover_info = server._get_hover_info(
            "file:///test.py", "for value in P().param.values():", "values"
        )

        assert hover_info is not None, "Should have hover info for values method"
        assert "**obj.param.values()**" in hover_info, "Should have method signature"
        assert "current values" in hover_info.lower(), "Should explain what values returns"
        assert "Dict[str, Any] (actual parameter values)" in hover_info, (
            "Should specify return type"
        )
        assert "obj.param.values()" in hover_info, (
            "Should include example usage showing list conversion"
        )
        assert "Output: {'x': 5, 'y': 'hello', 'z': True}" in hover_info, (
            "Should show simple output example"
        )

    def test_param_objects_method_hover(self):
        """Test hover information for obj.param.objects() method."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    temperature = param.Number(default=20.0)
    enabled = param.Boolean(default=True)

# Test param.objects() method hover
param_dict = P().param.objects()
"""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test hover for objects method
        hover_info = server._get_hover_info(
            "file:///test.py", "param_dict = P().param.objects()", "objects"
        )

        assert hover_info is not None, "Should have hover info for objects method"
        assert "**obj.param.objects()**" in hover_info, "Should have method signature"
        assert "dictionary mapping parameter names to their Parameter objects" in hover_info, (
            "Should explain what objects returns"
        )
        assert "Dict[str, Parameter] (parameter objects with metadata)" in hover_info, (
            "Should specify return type"
        )
        assert "obj.param.objects()" in hover_info, "Should include example usage"
        assert (
            "Output: {'x': Integer(default=5), 'y': String(default='hello'), 'z': Boolean(default=True)}"
            in hover_info
        ), "Should show simple output example"
        assert "Parameter objects themselves (with metadata)" in hover_info, (
            "Should clarify it returns Parameter objects"
        )

    def test_param_namespace_method_context_detection(self):
        """Test that param namespace methods are only detected in proper param context."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class P(param.Parameterized):
    x = param.Integer(default=5)

# Test proper param context
result = P().param.values()

# Test non-param context - should not get param hover
def values():
    return [1, 2, 3]

other_result = values()
"""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test values in param context
        hover_info = server._get_hover_info(
            "file:///test.py", "result = P().param.values()", "values"
        )
        assert hover_info is not None, "Should have hover info for param.values method"
        assert "param.values()" in hover_info, "Should be about param values method"

        # Test values outside param context
        hover_info = server._get_hover_info("file:///test.py", "other_result = values()", "values")
        # Should not get param namespace hover info for regular values function
        if hover_info is not None:
            assert "param.values()" not in hover_info, (
                "Should not get param hover info for regular values function"
            )

    def test_both_namespace_methods_different_contexts(self):
        """Test both values() and objects() in different contexts."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

class Settings(param.Parameterized):
    debug = param.Boolean(default=False)
    timeout = param.Number(default=30.0)
    name = param.String(default="app")

# Test both methods
settings = Settings()
all_values = settings.param.values()
all_objects = settings.param.objects()
"""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test values method hover
        values_hover_info = server._get_hover_info(
            "file:///test.py", "all_values = settings.param.values()", "values"
        )
        assert values_hover_info is not None, "Should have hover info for values method"
        assert "current values" in values_hover_info.lower(), "Should explain values method"

        # Test objects method hover
        objects_hover_info = server._get_hover_info(
            "file:///test.py", "all_objects = settings.param.objects()", "objects"
        )
        assert objects_hover_info is not None, "Should have hover info for objects method"
        assert (
            "dictionary mapping parameter names to their Parameter objects" in objects_hover_info
        ), "Should explain objects method"

        # Verify they're different
        assert values_hover_info != objects_hover_info, (
            "Should have different hover info for different methods"
        )

    def test_param_namespace_method_no_match_outside_context(self):
        """Test that regular functions with same names don't get param namespace hover."""
        server = ParamLanguageServer("test-server", "1.0.0")

        code_py = """\
import param

# Regular functions with same names
def values(data):
    return list(data.values())

def objects(data):
    return data.items()

# Usage outside param context
my_dict = {"a": 1, "b": 2}
result1 = values(my_dict)
result2 = objects(my_dict)
"""

        # Simulate document analysis
        server._analyze_document("file:///test.py", code_py)

        # Test that regular functions don't get param namespace hover
        values_hover = server._get_hover_info(
            "file:///test.py", "result1 = values(my_dict)", "values"
        )
        objects_hover = server._get_hover_info(
            "file:///test.py", "result2 = objects(my_dict)", "objects"
        )

        # Should not get param namespace hover info
        if values_hover is not None:
            assert "param.values()" not in values_hover, (
                "Should not get param hover for regular values function"
            )

        if objects_hover is not None:
            assert "param.objects()" not in objects_hover, (
                "Should not get param hover for regular objects function"
            )
