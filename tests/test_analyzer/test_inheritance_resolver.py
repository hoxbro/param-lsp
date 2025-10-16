"""Tests for the InheritanceResolver modular component."""

from __future__ import annotations

import pytest

from src.param_lsp._analyzer.inheritance_resolver import InheritanceResolver
from src.param_lsp._treesitter import get_class_bases, parser, walk_tree
from src.param_lsp.models import ParameterInfo, ParameterizedInfo


class TestInheritanceResolver:
    """Test the InheritanceResolver modular component."""

    @pytest.fixture
    def sample_param_classes(self):
        """Create sample param classes for testing."""
        parent_class = ParameterizedInfo(name="Parent")
        parent_class.add_parameter(
            ParameterInfo(
                name="parent_param",
                cls="String",
                default="parent_value",
                doc="Parent parameter",
            )
        )

        local_class = ParameterizedInfo(name="LocalParam")
        local_class.add_parameter(
            ParameterInfo(
                name="local_param",
                cls="Integer",
                default="42",
            )
        )

        return {
            "Parent": parent_class,
            "LocalParam": local_class,
        }

    @pytest.fixture
    def sample_external_classes(self):
        """Create sample external param classes for testing."""
        external_class = ParameterizedInfo(name="ExternalWidget")
        external_class.add_parameter(
            ParameterInfo(
                name="external_param",
                cls="Boolean",
                default="True",
                doc="External parameter",
            )
        )

        return {
            "panel.widgets.Button": external_class,
        }

    @pytest.fixture
    def sample_imports(self):
        """Create sample imports mapping."""
        return {
            "param": "param",
            "Parameterized": "param.Parameterized",
            "pn": "panel",
            "Button": "panel.widgets.Button",
        }

    @pytest.fixture
    def mock_functions(self, sample_external_classes):
        """Create mock functions for the resolver."""

        def mock_get_imported_param_class_info(class_name, import_name, file_path):
            # Mock external class lookup
            if class_name == "Button":
                return sample_external_classes["panel.widgets.Button"]
            return None

        def mock_analyze_external_class_ast(full_class_path):
            # Mock external class analysis
            if full_class_path == "panel.widgets.Button":
                return sample_external_classes["panel.widgets.Button"]
            return None

        def mock_resolve_full_class_path(base_node):
            # Mock class path resolution
            # Simple mock that returns panel.widgets.Button for complex cases
            return "panel.widgets.Button"

        return (
            mock_get_imported_param_class_info,
            mock_analyze_external_class_ast,
            mock_resolve_full_class_path,
        )

    @pytest.fixture
    def resolver(
        self, sample_param_classes, sample_external_classes, sample_imports, mock_functions
    ):
        """Create an InheritanceResolver instance for testing."""
        mock_get, mock_analyze, mock_resolve = mock_functions

        return InheritanceResolver(
            param_classes=sample_param_classes,
            external_param_classes=sample_external_classes,
            imports=sample_imports,
            get_imported_param_class_info_func=mock_get,
            analyze_external_class_ast_func=mock_analyze,
            resolve_full_class_path_func=mock_resolve,
        )

    def test_is_param_base_direct_parameterized(self, resolver):
        """Test is_param_base with direct param.Parameterized."""
        code = "class Test(param.Parameterized): pass"
        tree = parser.parse(code)
        class_nodes = [
            node for node in walk_tree(tree.root_node) if node.type == "class_definition"
        ]
        assert len(class_nodes) == 1

        bases = get_class_bases(class_nodes[0])
        assert len(bases) == 1

        assert resolver.is_param_base(bases[0]) is True

    def test_is_param_base_imported_parameterized(self, resolver):
        """Test is_param_base with imported Parameterized."""
        code = "class Test(Parameterized): pass"
        tree = parser.parse(code)
        class_nodes = [
            node for node in walk_tree(tree.root_node) if node.type == "class_definition"
        ]
        assert len(class_nodes) == 1

        bases = get_class_bases(class_nodes[0])
        assert len(bases) == 1

        assert resolver.is_param_base(bases[0]) is True

    def test_is_param_base_local_param_class(self, resolver):
        """Test is_param_base with local param class."""
        code = "class Test(Parent): pass"
        tree = parser.parse(code)
        class_nodes = [
            node for node in walk_tree(tree.root_node) if node.type == "class_definition"
        ]
        assert len(class_nodes) == 1

        bases = get_class_bases(class_nodes[0])
        assert len(bases) == 1

        assert resolver.is_param_base(bases[0]) is True

    def test_is_param_base_non_param_class(self, resolver):
        """Test is_param_base with non-param class."""
        code = "class Test(object): pass"
        tree = parser.parse(code)
        class_nodes = [
            node for node in walk_tree(tree.root_node) if node.type == "class_definition"
        ]
        assert len(class_nodes) == 1

        bases = get_class_bases(class_nodes[0])
        assert len(bases) == 1

        assert resolver.is_param_base(bases[0]) is False

    def test_is_param_base_external_class(self, resolver):
        """Test is_param_base with external param class."""
        code = "class Test(pn.widgets.Button): pass"
        tree = parser.parse(code)
        class_nodes = [
            node for node in walk_tree(tree.root_node) if node.type == "class_definition"
        ]
        assert len(class_nodes) == 1

        bases = get_class_bases(class_nodes[0])
        assert len(bases) == 1

        assert resolver.is_param_base(bases[0]) is True

    def test_collect_inherited_parameters_local_parent(self, resolver):
        """Test collecting parameters from local parent class."""
        code = "class Child(Parent): pass"
        tree = parser.parse(code)
        class_nodes = [
            node for node in walk_tree(tree.root_node) if node.type == "class_definition"
        ]
        assert len(class_nodes) == 1

        inherited = resolver.collect_inherited_parameters(class_nodes[0])

        assert "parent_param" in inherited
        assert inherited["parent_param"].cls == "String"
        assert inherited["parent_param"].default == "parent_value"
        assert inherited["parent_param"].doc == "Parent parameter"

    def test_collect_inherited_parameters_external_parent(self, resolver):
        """Test collecting parameters from external parent class."""
        code = "class Child(Button): pass"
        tree = parser.parse(code)
        class_nodes = [
            node for node in walk_tree(tree.root_node) if node.type == "class_definition"
        ]
        assert len(class_nodes) == 1

        inherited = resolver.collect_inherited_parameters(class_nodes[0], "test_file.py")

        assert "external_param" in inherited
        assert inherited["external_param"].cls == "Boolean"
        assert inherited["external_param"].default == "True"

    def test_collect_inherited_parameters_multiple_parents(self, resolver):
        """Test collecting parameters from multiple parent classes."""
        code = "class Child(Parent, LocalParam): pass"
        tree = parser.parse(code)
        class_nodes = [
            node for node in walk_tree(tree.root_node) if node.type == "class_definition"
        ]
        assert len(class_nodes) == 1

        inherited = resolver.collect_inherited_parameters(class_nodes[0])

        # Should inherit from both parents (last wins for conflicts)
        assert "parent_param" in inherited
        assert "local_param" in inherited
        assert inherited["parent_param"].cls == "String"
        assert inherited["local_param"].cls == "Integer"

    def test_collect_inherited_parameters_no_parents(self, resolver):
        """Test collecting parameters when no param parents exist."""
        code = "class Child(object): pass"
        tree = parser.parse(code)
        class_nodes = [
            node for node in walk_tree(tree.root_node) if node.type == "class_definition"
        ]
        assert len(class_nodes) == 1

        inherited = resolver.collect_inherited_parameters(class_nodes[0])

        assert inherited == {}

    def test_collect_inherited_parameters_complex_inheritance(self, resolver):
        """Test collecting parameters with complex attribute access."""
        code = "class Child(pn.widgets.Button): pass"
        tree = parser.parse(code)
        class_nodes = [
            node for node in walk_tree(tree.root_node) if node.type == "class_definition"
        ]
        assert len(class_nodes) == 1

        inherited = resolver.collect_inherited_parameters(class_nodes[0], "test_file.py")

        assert "external_param" in inherited
        assert inherited["external_param"].cls == "Boolean"

    def test_collect_inherited_parameters_unknown_parent(self, resolver):
        """Test collecting parameters from unknown parent class."""
        code = "class Child(UnknownClass): pass"
        tree = parser.parse(code)
        class_nodes = [
            node for node in walk_tree(tree.root_node) if node.type == "class_definition"
        ]
        assert len(class_nodes) == 1

        inherited = resolver.collect_inherited_parameters(class_nodes[0])

        assert inherited == {}

    def test_inheritance_resolver_state_isolation(
        self, sample_param_classes, sample_external_classes, sample_imports, mock_functions
    ):
        """Test that resolver instances maintain their own state."""
        mock_get, mock_analyze, mock_resolve = mock_functions

        # Create two resolvers with different param_classes
        resolver1_classes = {"Class1": ParameterizedInfo(name="Class1")}
        resolver2_classes = {"Class2": ParameterizedInfo(name="Class2")}

        resolver1 = InheritanceResolver(
            param_classes=resolver1_classes,
            external_param_classes=sample_external_classes,
            imports=sample_imports,
            get_imported_param_class_info_func=mock_get,
            analyze_external_class_ast_func=mock_analyze,
            resolve_full_class_path_func=mock_resolve,
        )

        resolver2 = InheritanceResolver(
            param_classes=resolver2_classes,
            external_param_classes=sample_external_classes,
            imports=sample_imports,
            get_imported_param_class_info_func=mock_get,
            analyze_external_class_ast_func=mock_analyze,
            resolve_full_class_path_func=mock_resolve,
        )

        # Each resolver should only know about its own classes
        assert "Class1" in resolver1.param_classes
        assert "Class1" not in resolver2.param_classes
        assert "Class2" in resolver2.param_classes
        assert "Class2" not in resolver1.param_classes
