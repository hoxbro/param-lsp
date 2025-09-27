"""Test deprecation warnings for parameter types."""

from __future__ import annotations


class TestDeprecationWarnings:
    """Test deprecated parameter type warnings."""

    def test_object_selector_deprecation_warning(self, analyzer):
        """Test that ObjectSelector usage emits a deprecation warning."""
        code = """
import param

class MyClass(param.Parameterized):
    selection = param.ObjectSelector(default="a", objects=["a", "b", "c"])
"""
        result = analyzer.analyze_file(code)

        # Check that a deprecation warning was generated
        warnings = [error for error in result["type_errors"] if error["severity"] == "warning"]
        assert len(warnings) == 1

        warning = warnings[0]
        assert warning["code"] == "deprecated-parameter"
        assert "ObjectSelector is deprecated, use Selector instead" in warning["message"]
        assert "param 2.0+" in warning["message"]
        assert warning["line"] == 4  # 0-based line number

    def test_selector_no_deprecation_warning(self, analyzer):
        """Test that Selector usage does not emit a deprecation warning."""
        code = """
import param

class MyClass(param.Parameterized):
    selection = param.Selector(default="a", objects=["a", "b", "c"])
"""
        result = analyzer.analyze_file(code)

        # Check that no deprecation warning was generated
        warnings = [error for error in result["type_errors"] if error["severity"] == "warning"]
        assert len(warnings) == 0

    def test_object_selector_with_alias_import(self, analyzer):
        """Test ObjectSelector deprecation warning with aliased import."""
        code = """
import param as p

class MyClass(p.Parameterized):
    selection = p.ObjectSelector(default="a", objects=["a", "b", "c"])
"""
        result = analyzer.analyze_file(code)

        # Check that a deprecation warning was generated
        warnings = [error for error in result["type_errors"] if error["severity"] == "warning"]
        assert len(warnings) == 1

        warning = warnings[0]
        assert warning["code"] == "deprecated-parameter"
        assert "ObjectSelector is deprecated, use Selector instead" in warning["message"]

    def test_multiple_object_selector_warnings(self, analyzer):
        """Test multiple ObjectSelector usages emit multiple warnings."""
        code = """
import param

class MyClass(param.Parameterized):
    selection1 = param.ObjectSelector(default="a", objects=["a", "b"])
    selection2 = param.ObjectSelector(default="x", objects=["x", "y"])
"""
        result = analyzer.analyze_file(code)

        # Check that two deprecation warnings were generated
        warnings = [error for error in result["type_errors"] if error["severity"] == "warning"]
        assert len(warnings) == 2

        for warning in warnings:
            assert warning["code"] == "deprecated-parameter"
            assert "ObjectSelector is deprecated, use Selector instead" in warning["message"]
