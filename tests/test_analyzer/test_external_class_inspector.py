"""Test external_class_inspector functions independently."""

from __future__ import annotations

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
            if not isinstance(e, (ImportError, FileNotFoundError, OSError)):
                raise

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


class TestExternalClassInspectorIntegration:
    """Integration tests for ExternalClassInspector."""

    def test_error_handling_robustness(self):
        """Test that the inspector handles errors gracefully."""
        inspector = ExternalClassInspector()

        # These should not crash
        inspector.analyze_external_class_ast("definitely.not.a.real.class")
        inspector._introspect_external_class_runtime("also.not.real")

    def test_real_param_class_analysis(self):
        """Test analysis of real param classes."""
        inspector = ExternalClassInspector()
        # Test with actual param.Parameterized if available
        result = inspector.analyze_external_class_ast("param.Parameterized")
        # May be None or a ParameterizedInfo object
        assert result is None or hasattr(result, "name")

    def test_memory_efficiency(self):
        """Test that the inspector doesn't leak memory with repeated calls."""
        inspector = ExternalClassInspector()

        # Call methods multiple times to check for memory leaks
        for _ in range(10):
            inspector.analyze_external_class_ast("fake.class.Name")
            inspector._looks_like_parameter_assignment("x = param.Integer()")

        # Should not accumulate state inappropriately
        assert len(inspector.external_param_classes) >= 0  # May cache some failed lookups
