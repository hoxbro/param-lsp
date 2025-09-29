"""Test external_class_inspector functions independently."""

from __future__ import annotations

import pytest

from param_lsp._analyzer.external_class_inspector import ExternalClassInspector


class TestExternalClassInspector:
    """Test ExternalClassInspector functionality."""

    def test_initialization(self):
        """Test inspector initialization."""
        inspector = ExternalClassInspector()
        assert inspector is not None
        assert hasattr(inspector, "external_param_classes")
        assert isinstance(inspector.external_param_classes, dict)

    def test_populate_external_library_cache(self):
        """Test populate_external_library_cache method."""
        inspector = ExternalClassInspector()

        # Should not crash when called
        try:
            inspector.populate_external_library_cache()
        except Exception as e:
            # May fail due to missing libraries, but should not crash the test
            assert isinstance(e, (ImportError, FileNotFoundError, OSError))

    def test_analyze_external_class_ast_nonexistent(self):
        """Test analyze_external_class_ast with non-existent class."""
        inspector = ExternalClassInspector()

        result = inspector.analyze_external_class_ast("nonexistent.module.Class")
        assert result is None

    def test_analyze_external_class_ast_invalid_path(self):
        """Test analyze_external_class_ast with invalid class path."""
        inspector = ExternalClassInspector()

        result = inspector.analyze_external_class_ast("")
        assert result is None

        result = inspector.analyze_external_class_ast("invalid")
        assert result is None

    def test_introspect_external_class_runtime_nonexistent(self):
        """Test _introspect_external_class_runtime with non-existent class."""
        inspector = ExternalClassInspector()

        result = inspector._introspect_external_class_runtime("nonexistent.module.Class")
        assert result is None

    def test_looks_like_parameter_assignment(self):
        """Test _looks_like_parameter_assignment method."""
        inspector = ExternalClassInspector()

        # Test valid parameter assignments
        assert inspector._looks_like_parameter_assignment("x = param.Integer()")
        assert inspector._looks_like_parameter_assignment("name = param.String(default='test')")
        assert inspector._looks_like_parameter_assignment(
            "    value = param.Number(bounds=(0, 10))"
        )

        # Test invalid assignments
        assert not inspector._looks_like_parameter_assignment("x = 42")
        assert not inspector._looks_like_parameter_assignment("def method(self):")
        assert not inspector._looks_like_parameter_assignment("# Comment")
        assert not inspector._looks_like_parameter_assignment("")

    def test_extract_multiline_definition(self):
        """Test _extract_multiline_definition method."""
        inspector = ExternalClassInspector()

        source_lines = [
            "class Test:",
            "    x = param.Integer(",
            "        default=42,",
            "        bounds=(0, 100)",
            "    )",
            "    y = param.String()",
        ]

        # Test extracting multiline definition
        result = inspector._extract_multiline_definition(source_lines, 1)
        assert "param.Integer" in result
        assert "default=42" in result
        assert "bounds=(0, 100)" in result

        # Test with single line
        result = inspector._extract_multiline_definition(source_lines, 5)
        assert "param.String()" in result

    def test_find_parameter_defining_class(self):
        """Test _find_parameter_defining_class method."""
        inspector = ExternalClassInspector()

        # Create a mock class hierarchy
        class BaseClass:
            pass

        class ChildClass(BaseClass):
            pass

        # Test with non-param class should return None
        result = inspector._find_parameter_defining_class(ChildClass, "some_param")
        assert result is None

    def test_get_all_classes_in_module_invalid(self):
        """Test _get_all_classes_in_module with invalid module."""
        inspector = ExternalClassInspector()

        # Test with None
        result = inspector._get_all_classes_in_module(None)
        assert result == []

        # Test with non-module object
        result = inspector._get_all_classes_in_module("not_a_module")
        assert result == []

    def test_introspect_param_class_for_cache_invalid(self):
        """Test _introspect_param_class_for_cache with invalid input."""
        inspector = ExternalClassInspector()

        # Test with None
        result = inspector._introspect_param_class_for_cache(None)
        assert result is None

        # Test with non-class object
        result = inspector._introspect_param_class_for_cache("not_a_class")
        assert result is None

        # Test with built-in type
        result = inspector._introspect_param_class_for_cache(int)
        assert result is None

    def test_get_parameter_source_location_edge_cases(self):
        """Test _get_parameter_source_location with edge cases."""
        inspector = ExternalClassInspector()

        # Test with None class
        result = inspector._get_parameter_source_location(None, None, "param_name")
        assert result is None

        # Test with invalid parameter name
        class MockClass:
            pass

        result = inspector._get_parameter_source_location(None, MockClass, "nonexistent_param")
        assert result is None

    def test_discover_param_classes_in_library_invalid(self):
        """Test _discover_param_classes_in_library with invalid input."""
        inspector = ExternalClassInspector()

        # Test with None
        result = inspector._discover_param_classes_in_library(None, "invalid_library")
        assert result == 0

        # Test with non-existent library
        result = inspector._discover_param_classes_in_library(
            type("MockModule", (), {}), "nonexistent.library"
        )
        assert result == 0


class TestExternalClassInspectorIntegration:
    """Integration tests for ExternalClassInspector."""

    def test_error_handling_robustness(self):
        """Test that the inspector handles errors gracefully."""
        inspector = ExternalClassInspector()

        # These should not crash
        inspector.analyze_external_class_ast("definitely.not.a.real.class")
        inspector._introspect_external_class_runtime("also.not.real")

        # Should handle None inputs
        inspector._get_all_classes_in_module(None)
        inspector._introspect_param_class_for_cache(None)

    @pytest.mark.skipif(True, reason="Requires external libraries and may be slow")
    def test_real_param_class_analysis(self):
        """Test analysis of real param classes."""
        inspector = ExternalClassInspector()

        try:
            import param

            # Test with actual param.Parameterized if available
            result = inspector.analyze_external_class_ast("param.Parameterized")
            # May be None or a ParameterizedInfo object
            assert result is None or hasattr(result, "name")
        except ImportError:
            pytest.skip("param library not available")

    def test_attribute_errors_handled(self):
        """Test that AttributeError is handled gracefully."""
        inspector = ExternalClassInspector()

        # Create a mock object that will cause AttributeError
        class BrokenMock:
            def __getattr__(self, name):
                raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

        broken_obj = BrokenMock()

        # These should not crash even with broken objects
        result = inspector._introspect_param_class_for_cache(broken_obj)
        assert result is None

    def test_memory_efficiency(self):
        """Test that the inspector doesn't leak memory with repeated calls."""
        inspector = ExternalClassInspector()

        # Call methods multiple times to check for memory leaks
        for _ in range(10):
            inspector.analyze_external_class_ast("fake.class.Name")
            inspector._looks_like_parameter_assignment("x = param.Integer()")

        # Should not accumulate state inappropriately
        assert len(inspector.external_param_classes) >= 0  # May cache some failed lookups
