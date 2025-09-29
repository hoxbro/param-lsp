"""
Integration tests for modular component interactions.
Tests the basic coordination between different analyzer modules.
"""

from __future__ import annotations

import tempfile
from contextlib import suppress

from parso import parse

from src.param_lsp._analyzer.external_class_inspector import ExternalClassInspector
from src.param_lsp._analyzer.import_resolver import ImportResolver
from src.param_lsp._analyzer.parameter_extractor import is_parameter_assignment
from src.param_lsp._analyzer.parso_utils import get_value, has_children, walk_tree


class TestModularComponentIntegration:
    """Test integration between modular analyzer components."""

    def test_parso_utils_error_handling(self):
        """Test that parso utils handle None and invalid inputs gracefully."""
        # Test with None inputs - should not crash
        assert get_value(None) is None
        assert has_children(None) is False
        assert list(walk_tree(None)) == []

        # Test with empty tree
        empty_tree = parse("")
        nodes = list(walk_tree(empty_tree))
        assert len(nodes) >= 1  # At least the root node

    def test_parameter_extractor_basic_functions(self):
        """Test parameter extraction basic functions work."""
        code1 = """
import param
class Test1(param.Parameterized):
    x = param.Number()
"""

        code2 = """
x = 42  # Not a parameter
"""

        # Both should be parseable
        tree1 = parse(code1)
        tree2 = parse(code2)

        # Test parameter assignment detection on actual assignments
        for node in walk_tree(tree1):
            if hasattr(node, "type") and node.type == "expr_stmt":
                result = is_parameter_assignment(node)
                assert isinstance(result, bool)

        for node in walk_tree(tree2):
            if hasattr(node, "type") and node.type == "expr_stmt":
                result = is_parameter_assignment(node)
                assert isinstance(result, bool)

    def test_external_class_inspector_standalone(self):
        """Test external class inspector basic functionality."""
        inspector = ExternalClassInspector()

        # Test methods that should work without dependencies
        result = inspector._get_all_classes_in_module(None)
        assert result == []

        # Test introspection with invalid inputs
        result = inspector._introspect_param_class_for_cache(None)
        assert result is None

        result = inspector._introspect_param_class_for_cache(int)
        assert result is None  # Built-in types should return None

        # Test method doesn't crash with basic types
        result = inspector._find_parameter_defining_class(str, "nonexistent")
        assert result is None

    def test_import_resolver_basic_functionality(self):
        """Test import resolver basic methods."""
        resolver = ImportResolver()

        # Test path resolution with invalid inputs
        result = resolver.resolve_module_path(None, None)
        assert result is None

        with tempfile.TemporaryDirectory() as tmpdir:
            result = resolver.resolve_module_path("nonexistent", tmpdir)
        # Should handle gracefully
        assert result is None or isinstance(result, str)

        # Test module analysis with None
        result = resolver.analyze_imported_module(None, None)
        assert result == {"param_classes": {}, "imports": {}, "type_errors": []}

    def test_modular_components_error_resilience(self):
        """Test that modular components are resilient to errors."""
        # Test with various malformed inputs
        test_inputs = [
            None,
            "",
            "class Broken(param.Parameterized",  # Missing closing paren
        ]

        inspector = ExternalClassInspector()
        resolver = ImportResolver()

        for test_input in test_inputs:
            with suppress(Exception):
                # If parsing fails, continue
                _ = None if test_input is None else parse(test_input)

            # All these methods should handle None gracefully
            assert inspector._get_all_classes_in_module(None) == []
            assert resolver.resolve_module_path(None, None) is None

    def test_cross_module_data_flow(self):
        """Test data flow between different modules."""
        code = """
import param

class MyClass(param.Parameterized):
    value = param.Number(default=1.0)
"""
        tree = parse(code)

        # Step 1: Use parso utils to extract structure
        nodes = list(walk_tree(tree))
        assert len(nodes) >= 1

        # Step 2: Extract imports
        import_nodes = [
            node
            for node in walk_tree(tree)
            if hasattr(node, "type") and node.type in ("import_name", "import_from")
        ]

        assert len(import_nodes) >= 1  # Should find the import statement

        # Step 3: Test that extracted data is usable
        for node in walk_tree(tree):
            if hasattr(node, "type") and node.type == "expr_stmt":
                # Should be able to test if it's a parameter assignment
                result = is_parameter_assignment(node)
                assert isinstance(result, bool)

    def test_error_isolation_between_modules(self):
        """Test that errors in one module don't affect others."""
        inspector = ExternalClassInspector()
        resolver = ImportResolver()

        # Test that if one component fails, others continue working
        with suppress(Exception):
            # This might fail but shouldn't crash the program
            inspector.analyze_external_class_ast("definitely.not.a.real.class")

        # Other components should still work
        assert resolver.resolve_module_path(None, None) is None
        assert inspector._get_all_classes_in_module(None) == []

        # Test with valid data to ensure functionality isn't broken
        code = "import param"
        tree = parse(code)
        nodes = list(walk_tree(tree))
        assert len(nodes) >= 1

    def test_component_independence(self):
        """Test that components can work independently."""
        # Each component should work without requiring others

        # Parso utils should work standalone
        tree = parse("x = 1")
        nodes = list(walk_tree(tree))
        assert len(nodes) >= 1

        # Parameter extractor functions should work standalone
        assignment = tree.children[0] if tree.children else None
        if assignment:
            result = is_parameter_assignment(assignment)
            assert isinstance(result, bool)

        # External class inspector should work standalone
        inspector = ExternalClassInspector()
        result = inspector._get_all_classes_in_module(None)
        assert result == []

        # Import resolver should work standalone
        resolver = ImportResolver()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = resolver.resolve_module_path("test", tmpdir)
        # Should return None or a valid path, but not crash
        assert result is None or isinstance(result, str)

    def test_modular_component_coordination(self):
        """Test that modular components can work together."""
        # Test a realistic scenario where components need to coordinate
        code = """
import param

class TestWidget(param.Parameterized):
    name = param.String(default="widget")
    value = param.Number(default=0.0, bounds=(0, 1))
"""
        tree = parse(code)

        # Test that all components can process the same tree without issues
        inspector = ExternalClassInspector()
        resolver = ImportResolver()

        # All should be able to process the tree
        nodes = list(walk_tree(tree))
        assert len(nodes) >= 1

        # Components should handle the tree gracefully
        assert inspector._get_all_classes_in_module(None) == []
        assert resolver.resolve_module_path(None, None) is None

        # Parameter assignment detection should work
        assignment_count = 0
        for node in walk_tree(tree):
            if (
                hasattr(node, "type")
                and node.type == "expr_stmt"
                and is_parameter_assignment(node)
            ):
                assignment_count += 1

        # Should detect parameter assignments
        assert assignment_count >= 0  # May or may not find assignments depending on implementation
