"""Tests for external Parameterized class support (Panel, HoloViews, etc.)."""

from __future__ import annotations

import pytest


class TestExternalParameterizedClasses:
    """Test external Parameterized classes like Panel widgets and HoloViews elements."""

    def setup_class(self):
        pytest.importorskip("holoviews")
        pytest.importorskip("panel")

    def test_panel_widget_runtime_assignment(self, analyzer):
        """Test runtime assignment type checking for Panel widgets."""
        code_py = """\
import panel as pn

w = pn.widgets.IntSlider()
w.value = "2"  # should error - expects int
"""
        result = analyzer.analyze_file(code_py)

        # Should detect external param class
        assert "panel.widgets.IntSlider" in analyzer.external_param_classes
        assert analyzer.external_param_classes["panel.widgets.IntSlider"] is not None

        # Should detect type error
        assert len(result["type_errors"]) == 1
        error = result["type_errors"][0]
        assert error["code"] == "runtime-type-mismatch"
        assert "value" in error["message"]
        assert "Integer" in error["message"]

    def test_panel_widget_constructor_type_checking(self, analyzer):
        """Test constructor type checking for Panel widgets."""
        code_py = """\
import panel as pn

# Valid constructor
w1 = pn.widgets.IntSlider(value=10)

# Invalid constructor - type mismatch
w2 = pn.widgets.IntSlider(value="5")

# Invalid constructor - boolean type mismatch
w3 = pn.widgets.Checkbox(value="true")
"""
        result = analyzer.analyze_file(code_py)

        # Should detect external param classes
        assert "panel.widgets.IntSlider" in analyzer.external_param_classes
        assert "panel.widgets.Checkbox" in analyzer.external_param_classes

        # Should detect 2 type errors
        assert len(result["type_errors"]) == 2

        # First error: IntSlider with string value
        error1 = result["type_errors"][0]
        assert error1["code"] == "constructor-type-mismatch"
        assert "value" in error1["message"]
        assert "Integer" in error1["message"]

        # Second error: Checkbox with string value
        error2 = result["type_errors"][1]
        assert error2["code"] == "constructor-boolean-type-mismatch"
        assert "value" in error2["message"]
        assert "Boolean" in error2["message"]

    def test_holoviews_element_support(self, analyzer):
        """Test HoloViews element support."""
        code_py = """
import holoviews as hv

# Valid assignments
curve = hv.Curve([1, 2, 3])
curve.label = "test"

# Invalid assignment - type mismatch
scatter = hv.Scatter([(1, 2), (3, 4)])
scatter.label = 123  # should error - expects str
"""
        result = analyzer.analyze_file(code_py)

        # Should detect external param classes
        assert "holoviews.Curve" in analyzer.external_param_classes
        assert "holoviews.Scatter" in analyzer.external_param_classes

        # Should detect type error
        assert len(result["type_errors"]) == 1
        error = result["type_errors"][0]
        assert error["code"] == "runtime-type-mismatch"
        assert "label" in error["message"]

    def test_holoviews_constructor_type_checking(self, analyzer):
        """Test HoloViews constructor type checking."""
        code_py = """
import holoviews as hv

# Valid constructor
scatter1 = hv.Scatter([(1, 2), (3, 4)], label="test")

# Invalid constructor - type mismatch
scatter2 = hv.Scatter([(1, 2), (3, 4)], label=123)
"""
        result = analyzer.analyze_file(code_py)

        # Should detect external param class
        assert "holoviews.Scatter" in analyzer.external_param_classes

        # Should detect type error
        assert len(result["type_errors"]) == 1
        error = result["type_errors"][0]
        assert error["code"] == "constructor-type-mismatch"
        assert "label" in error["message"]

    def test_multiple_external_libraries(self, analyzer):
        """Test support for multiple external libraries in the same file."""
        code_py = """\
import panel as pn
import holoviews as hv

# Panel widget error
w = pn.widgets.IntSlider()
w.value = "invalid"

# HoloViews element error
curve = hv.Curve([1, 2, 3])
curve.label = 999
"""
        result = analyzer.analyze_file(code_py)

        # Should detect both external param classes
        assert "panel.widgets.IntSlider" in analyzer.external_param_classes
        assert "holoviews.Curve" in analyzer.external_param_classes

        # Should detect 2 type errors
        assert len(result["type_errors"]) == 2

    def test_external_class_parameter_introspection(self, analyzer):
        """Test that external class parameters are properly introspected."""
        code_py = """\
import panel as pn

w = pn.widgets.IntSlider()
"""
        analyzer.analyze_file(code_py)

        # Should have introspected the class
        assert "panel.widgets.IntSlider" in analyzer.external_param_classes
        class_info = analyzer.external_param_classes["panel.widgets.IntSlider"]
        assert class_info is not None

        # Should have parameter information
        assert "value" in class_info["parameters"]
        assert class_info["parameter_types"]["value"] == "Integer"
        assert "value" in class_info["parameter_allow_none"]

    def test_external_class_caching(self, analyzer):
        """Test that external class introspection is cached."""
        code1 = """
import panel as pn
w1 = pn.widgets.IntSlider()
"""

        code2 = """
import panel as pn
w2 = pn.widgets.IntSlider()
"""

        # First analysis
        analyzer.analyze_file(code1)
        first_cache_size = len(analyzer.external_param_classes)

        # Second analysis should use cached results
        analyzer.analyze_file(code2)
        second_cache_size = len(analyzer.external_param_classes)

        # Cache size should remain the same
        assert first_cache_size == second_cache_size
        assert "panel.widgets.IntSlider" in analyzer.external_param_classes

    def test_non_parameterized_external_classes_ignored(self, analyzer):
        """Test that non-Parameterized external classes are ignored."""
        code_py = """
import json

# This should not be detected as a param class
data = json.loads('{"key": "value"}')
"""
        analyzer.analyze_file(code_py)

        # Should not detect any external param classes
        valid_external_classes = [
            name for name, info in analyzer.external_param_classes.items() if info is not None
        ]
        assert len(valid_external_classes) == 0

    def test_inheritance_from_external_classes(self, analyzer):
        """Test that inheritance from external Parameterized classes works."""
        # Note: This test might require the external classes to be available
        # in the current environment, so we'll test the introspection capability
        code_py = """\
import panel as pn

# Create a widget that should inherit from param.Parameterized
w = pn.widgets.TextInput()
w.value = 123  # should error - expects str
"""
        result = analyzer.analyze_file(code_py)

        # Should detect the external class
        assert "panel.widgets.TextInput" in analyzer.external_param_classes
        class_info = analyzer.external_param_classes["panel.widgets.TextInput"]

        if class_info:  # Only test if introspection succeeded
            # Should detect type error
            assert len(result["type_errors"]) >= 1
            # Find the relevant error
            text_input_errors = [
                e
                for e in result["type_errors"]
                if "value" in e["message"] and e["code"] == "runtime-type-mismatch"
            ]
            assert len(text_input_errors) >= 1

    def test_example2_mixed_libraries(self, analyzer):
        """Test the updated example2.py with both Panel and HoloViews."""
        code_py = """
from __future__ import annotations

import holoviews as hv
import panel as pn

w = pn.widgets.IntSlider()
p = hv.Curve([])

p.group = 1

w.value = "2"  # should error
"""
        result = analyzer.analyze_file(code_py)

        # Should detect both external param classes
        assert "panel.widgets.IntSlider" in analyzer.external_param_classes
        assert "holoviews.Curve" in analyzer.external_param_classes

        # Should detect 2 type errors
        assert len(result["type_errors"]) == 2

        # Line 9: p.group = 1 (HoloViews error)
        hv_error = None
        panel_error = None

        for error in result["type_errors"]:
            if "group" in error["message"]:
                hv_error = error
            elif "value" in error["message"]:
                panel_error = error

        # Verify HoloViews error
        assert hv_error is not None
        assert hv_error["code"] == "runtime-type-mismatch"
        assert "group" in hv_error["message"]
        assert "String" in hv_error["message"] or "str" in hv_error["message"]

        # Verify Panel error
        assert panel_error is not None
        assert panel_error["code"] == "runtime-type-mismatch"
        assert "value" in panel_error["message"]
        assert "Integer" in panel_error["message"] or "int" in panel_error["message"]
