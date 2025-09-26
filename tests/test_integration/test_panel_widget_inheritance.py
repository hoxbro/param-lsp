"""Tests for Panel widget parameter inheritance."""

from __future__ import annotations

import pytest

from param_lsp.analyzer import ParamAnalyzer


class TestPanelWidgetInheritance:
    """Test parameter inheritance from Panel widgets."""

    def test_panel_intslider_inheritance(self):
        """Test that classes inheriting from Panel IntSlider get all parameters."""
        pytest.importorskip("panel")  # Skip if panel not available

        code_py = """\
import param
import panel as pn

class T(pn.widgets.IntSlider):
    @param.depends("value")
    def test(self):
        return self.value * 2
"""

        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)

        # Verify class is detected as Parameterized
        assert "T" in result["param_classes"]
        t_class = result["param_classes"]["T"]

        # Verify T inherits Panel IntSlider parameters
        t_params = list(t_class.parameters.keys())
        assert len(t_params) > 10  # Panel IntSlider has many parameters

        # Verify key parameters are available
        assert "value" in t_params
        assert "start" in t_params
        assert "end" in t_params
        assert "step" in t_params
        # Note: 'name' parameter is excluded from autocompletion

        # Verify parameter types are correctly inherited
        assert t_class.parameters["value"].cls == "Integer"

    def test_panel_widget_chain_inheritance(self):
        """Test inheritance chain through Panel widgets."""
        pytest.importorskip("panel")

        code_py = """\
import param
import panel as pn

class CustomSlider(pn.widgets.IntSlider):
    custom_param = param.String(default="custom")

class MyWidget(CustomSlider):
    my_param = param.Boolean(default=True)
"""

        analyzer = ParamAnalyzer()
        result = analyzer.analyze_file(code_py)

        # Both classes should be detected
        assert "CustomSlider" in result["param_classes"]
        assert "MyWidget" in result["param_classes"]

        custom_slider_class = result["param_classes"]["CustomSlider"]
        my_widget_class = result["param_classes"]["MyWidget"]

        # CustomSlider should have Panel IntSlider params + custom_param
        custom_params = list(custom_slider_class.parameters.keys())
        assert "value" in custom_params
        assert "custom_param" in custom_params

        # MyWidget should inherit everything
        my_params = list(my_widget_class.parameters.keys())
        assert "value" in my_params  # From Panel IntSlider
        assert "custom_param" in my_params  # From CustomSlider
        assert "my_param" in my_params  # Own parameter
