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

        # Verify T inherits Panel IntSlider parameters
        t_params = result["param_parameters"]["T"]
        assert len(t_params) > 10  # Panel IntSlider has many parameters

        # Verify key parameters are available
        assert "value" in t_params
        assert "start" in t_params
        assert "end" in t_params
        assert "step" in t_params
        # Note: 'name' parameter is excluded from autocompletion

        # Verify parameter types are correctly inherited
        param_types = result["param_parameter_types"]["T"]
        assert param_types["value"] == "Integer"

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

        # CustomSlider should have Panel IntSlider params + custom_param
        custom_params = result["param_parameters"]["CustomSlider"]
        assert "value" in custom_params
        assert "custom_param" in custom_params

        # MyWidget should inherit everything
        my_params = result["param_parameters"]["MyWidget"]
        assert "value" in my_params  # From Panel IntSlider
        assert "custom_param" in my_params  # From CustomSlider
        assert "my_param" in my_params  # Own parameter
