"""Tests for static external analyzer.

These tests verify that the static analyzer produces results equivalent
to runtime introspection for external Parameterized classes.
"""

from __future__ import annotations

import pytest

from param_lsp._analyzer.static_external_analyzer import ExternalClassInspector


class TestExternalClassInspector:
    """Test the static external analyzer against runtime introspection."""

    def setup_method(self):
        """Set up test instances."""
        self.static_analyzer = ExternalClassInspector()

    @pytest.mark.parametrize(
        "class_path",
        [
            "panel.widgets.IntSlider",
            "panel.widgets.TextInput",
            "panel.widgets.Checkbox",
            "holoviews.Curve",
            "holoviews.Scatter",
        ],
    )
    def test_static_analysis_external_classes(self, class_path: str):
        """Test that static analysis successfully analyzes common external classes."""
        # Skip if library not available
        root_module = class_path.split(".")[0]
        pytest.importorskip(root_module)

        # Get result from static analyzer
        static_result = self.static_analyzer.analyze_external_class(class_path)

        # Should successfully analyze common external classes
        assert static_result is not None, f"Static analyzer should find {class_path}"

        # Check that found parameters have reasonable structure
        assert len(static_result.parameters) > 0, f"Should find parameters for {class_path}"

        for param_name, param_info in static_result.parameters.items():
            assert param_info.name == param_name
            assert param_info.cls is not None, f"Parameter {param_name} missing class"

        # Class name should match expected
        expected_class_name = class_path.split(".")[-1]
        assert static_result.name == expected_class_name

    def test_panel_intslider_detailed(self):
        """Detailed test for Panel IntSlider parameter extraction."""
        pytest.importorskip("panel")

        class_path = "panel.widgets.IntSlider"
        static_result = self.static_analyzer.analyze_external_class(class_path)

        assert static_result is not None

        # Check that 'value' parameter exists
        assert "value" in static_result.parameters

        static_value = static_result.parameters["value"]

        # Value should be Integer type
        assert static_value.cls == "Integer"

    def test_holoviews_curve_detailed(self):
        """Detailed test for HoloViews Curve parameter extraction."""
        pytest.importorskip("holoviews")

        class_path = "holoviews.Curve"
        static_result = self.static_analyzer.analyze_external_class(class_path)

        assert static_result is not None

        # Check that 'label' parameter exists
        assert "label" in static_result.parameters

        static_label = static_result.parameters["label"]

        # Label should be String type
        assert static_label.cls == "String"

    def test_source_file_discovery(self):
        """Test that source files can be discovered for external libraries."""
        pytest.importorskip("panel")

        # Test source file discovery
        panel_sources = self.static_analyzer._discover_library_sources("panel")
        assert len(panel_sources) > 0, "Should find Panel source files"

        # Check that files are actually Python files
        python_files = [f for f in panel_sources if f.suffix == ".py"]
        assert len(python_files) > 0, "Should find .py files"

    def test_class_inheritance_detection(self):
        """Test detection of param.Parameterized inheritance."""
        # Create a test Python file content
        test_code = """
import param

class MyWidget(param.Parameterized):
    value = param.Integer(default=10)
    name = param.String(default="test")

class NotParameterized:
    value = 42
"""

        # Parse with tree-sitter
        from src.param_lsp._treesitter import parser

        tree = parser.parse(test_code)

        # Analyze the file
        file_analysis = self.static_analyzer._analyze_file_ast(tree.root_node, test_code)

        # Should find MyWidget but not NotParameterized
        assert "MyWidget" in file_analysis
        assert "NotParameterized" not in file_analysis or file_analysis["NotParameterized"] is None

        # MyWidget should have parameters
        my_widget_info = file_analysis["MyWidget"]
        assert my_widget_info is not None
        assert "value" in my_widget_info.parameters
        assert "name" in my_widget_info.parameters

        # Check parameter types
        assert my_widget_info.parameters["value"].cls == "Integer"
        assert my_widget_info.parameters["name"].cls == "String"

    def test_complex_parameter_extraction(self):
        """Test extraction of complex parameter definitions."""
        test_code = """
import param

class ComplexWidget(param.Parameterized):
    # Simple parameter
    count = param.Integer(default=5, bounds=(0, 100), doc="Number of items")

    # Multiline parameter
    options = param.Selector(
        default="option1",
        objects=["option1", "option2", "option3"],
        doc="Available options"
    )

    # Boolean parameter
    enabled = param.Boolean(default=True, doc="Enable feature")
"""

        from src.param_lsp._treesitter import parser

        tree = parser.parse(test_code)
        file_analysis = self.static_analyzer._analyze_file_ast(tree.root_node, test_code)

        assert "ComplexWidget" in file_analysis
        widget_info = file_analysis["ComplexWidget"]
        assert widget_info is not None

        # Check count parameter
        assert "count" in widget_info.parameters
        count_param = widget_info.parameters["count"]
        assert count_param.cls == "Integer"
        assert count_param.default == "5"
        assert count_param.doc == "Number of items"

        # Check options parameter
        assert "options" in widget_info.parameters
        options_param = widget_info.parameters["options"]
        assert options_param.cls == "Selector"
        assert options_param.default == '"option1"'
        if options_param.objects:
            assert "option1" in options_param.objects
            assert "option2" in options_param.objects

        # Check enabled parameter
        assert "enabled" in widget_info.parameters
        enabled_param = widget_info.parameters["enabled"]
        assert enabled_param.cls == "Boolean"
        assert enabled_param.default == "True"

    def test_import_variations(self):
        """Test handling of different import styles."""
        test_code = """
# Test different import styles
import param
from param import Integer, String
from param import Selector as ParamSelector

class Widget1(param.Parameterized):
    value = param.Integer(default=1)

class Widget2(param.Parameterized):
    value = Integer(default=2)

class Widget3(param.Parameterized):
    choice = ParamSelector(default="a", objects=["a", "b"])
"""

        from src.param_lsp._treesitter import parser

        tree = parser.parse(test_code)
        file_analysis = self.static_analyzer._analyze_file_ast(tree.root_node, test_code)

        # All three widgets should be found
        assert "Widget1" in file_analysis
        assert "Widget2" in file_analysis
        assert "Widget3" in file_analysis

        # Check that parameters are correctly identified
        widget1 = file_analysis["Widget1"]
        widget2 = file_analysis["Widget2"]
        widget3 = file_analysis["Widget3"]

        assert widget1 is not None
        assert "value" in widget1.parameters
        assert widget2 is not None
        assert "value" in widget2.parameters
        assert widget3 is not None
        assert "choice" in widget3.parameters

        # Check parameter types
        assert widget1.parameters["value"].cls == "Integer"
        assert widget2.parameters["value"].cls == "Integer"
        assert widget3.parameters["choice"].cls == "Selector"

    def test_nonexistent_library(self):
        """Test handling of nonexistent libraries."""
        result = self.static_analyzer.analyze_external_class("nonexistent.module.Class")
        assert result is None

    def test_caching_behavior(self):
        """Test that analysis results are properly cached."""
        pytest.importorskip("panel")

        class_path = "panel.widgets.IntSlider"

        # First call
        result1 = self.static_analyzer.analyze_external_class(class_path)

        # Second call should use cache
        result2 = self.static_analyzer.analyze_external_class(class_path)

        # Results should be identical (same object due to caching)
        assert result1 is result2

    def test_error_handling(self):
        """Test graceful handling of parsing errors."""
        # Create analyzer and test with invalid file path
        analyzer = ExternalClassInspector()

        # Should not crash on invalid paths
        result = analyzer.analyze_external_class("invalid.module.Class")
        assert result is None

    @pytest.mark.parametrize(
        ("test_class_code", "expected_params"),
        [
            (
                """
import param
class TestWidget(param.Parameterized):
    value = param.Number(default=1.0)
""",
                {"value": "Number"},
            ),
            (
                """
import param
class TestWidget(param.Parameterized):
    items = param.List(default=[])
""",
                {"items": "List"},
            ),
            (
                """
import param
class TestWidget(param.Parameterized):
    data = param.Tuple(default=())
""",
                {"data": "Tuple"},
            ),
        ],
    )
    def test_parameter_type_detection(self, test_class_code: str, expected_params: dict[str, str]):
        """Test detection of various parameter types."""
        from src.param_lsp._treesitter import parser

        tree = parser.parse(test_class_code)
        file_analysis = self.static_analyzer._analyze_file_ast(tree.root_node, test_class_code)

        assert "TestWidget" in file_analysis
        widget_info = file_analysis["TestWidget"]
        assert widget_info is not None

        for param_name, param_type in expected_params.items():
            assert param_name in widget_info.parameters
            assert widget_info.parameters[param_name].cls == param_type
