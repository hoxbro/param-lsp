"""Tests for the ImportResolver modular component."""

from __future__ import annotations

import os

import pytest

from src.param_lsp._analyzer.import_resolver import ImportResolver
from src.param_lsp._treesitter import parser, walk_tree


class TestImportResolver:
    """Test the ImportResolver modular component."""

    @pytest.fixture
    def sample_imports(self):
        """Create sample imports mapping."""
        return {
            "param": "param",
            "pn": "panel",
            "Button": "panel.widgets.Button",
            "Parameterized": "param.Parameterized",
        }

    @pytest.fixture
    def mock_analyze_file_func(self):
        """Mock function for analyzing files."""

        def mock_func(content, file_path=None):
            return {
                "param_classes": {
                    "TestClass": type(
                        "MockParameterizedInfo",
                        (),
                        {
                            "parameters": {
                                "test_param": type("MockParameterInfo", (), {"cls": "String"})()
                            }
                        },
                    )()
                },
                "imports": {},
                "type_errors": [],
            }

        return mock_func

    @pytest.fixture
    def resolver(self, sample_imports, mock_analyze_file_func):
        """Create an ImportResolver instance for testing."""
        return ImportResolver(
            workspace_root="/test/workspace",
            imports=sample_imports,
            module_cache={},
            file_cache={},
            analyze_file_func=mock_analyze_file_func,
        )

    def test_initialization(self):
        """Test ImportResolver initialization."""
        resolver = ImportResolver()
        assert resolver.workspace_root is None
        assert resolver.imports == {}
        assert resolver.module_cache == {}
        assert resolver.file_cache == {}
        assert resolver.analyze_file_func is None

    def test_initialization_with_params(self, sample_imports, mock_analyze_file_func):
        """Test ImportResolver initialization with parameters."""
        resolver = ImportResolver(
            workspace_root="/test/workspace",
            imports=sample_imports,
            analyze_file_func=mock_analyze_file_func,
        )
        assert str(resolver.workspace_root).replace(os.sep, "/") == "/test/workspace"
        assert resolver.imports == sample_imports
        assert resolver.analyze_file_func == mock_analyze_file_func

    def test_handle_import_simple(self, resolver):
        """Test handle_import with simple import statement."""
        code = "import os"
        tree = parser.parse(code)
        import_nodes = [
            node for node in walk_tree(tree.root_node) if node.type == "import_statement"
        ]
        assert len(import_nodes) == 1

        resolver.handle_import(import_nodes[0])

        # Should add the import
        assert "os" in resolver.imports
        assert resolver.imports["os"] == "os"

    def test_handle_import_as_alias(self, resolver):
        """Test handle_import with import as alias."""
        code = "import numpy as np"
        tree = parser.parse(code)
        import_nodes = [
            node for node in walk_tree(tree.root_node) if node.type == "import_statement"
        ]
        assert len(import_nodes) == 1

        resolver.handle_import(import_nodes[0])

        # Should add the aliased import
        assert "np" in resolver.imports
        assert resolver.imports["np"] == "numpy"

    def test_handle_import_from_simple(self, resolver):
        """Test handle_import_from with simple from import."""
        code = "from os import path"
        tree = parser.parse(code)
        import_nodes = [
            node for node in walk_tree(tree.root_node) if node.type == "import_from_statement"
        ]
        assert len(import_nodes) == 1

        resolver.handle_import_from(import_nodes[0])

        # Should add the from import
        assert "path" in resolver.imports
        assert resolver.imports["path"] == "os.path"

    def test_handle_import_from_multiple(self, resolver):
        """Test handle_import_from with multiple imports."""
        code = "from os import path, environ"
        tree = parser.parse(code)
        import_nodes = [
            node for node in walk_tree(tree.root_node) if node.type == "import_from_statement"
        ]
        assert len(import_nodes) == 1

        resolver.handle_import_from(import_nodes[0])

        # Should add both imports
        assert "path" in resolver.imports
        assert "environ" in resolver.imports
        assert resolver.imports["path"] == "os.path"
        assert resolver.imports["environ"] == "os.environ"

    def test_handle_import_from_alias(self, resolver):
        """Test handle_import_from with alias."""
        code = "from param import Parameterized as P"
        tree = parser.parse(code)
        import_nodes = [
            node for node in walk_tree(tree.root_node) if node.type == "import_from_statement"
        ]
        assert len(import_nodes) == 1

        resolver.handle_import_from(import_nodes[0])

        # Should add the aliased import
        assert "P" in resolver.imports
        assert resolver.imports["P"] == "param.Parameterized"

    def test_resolve_module_path_absolute(self, resolver):
        """Test resolve_module_path with absolute module."""
        # This would require actual file system, so test the logic path
        result = resolver.resolve_module_path("nonexistent.module")
        # Should return None for non-existent modules
        assert result is None

    def test_resolve_module_path_no_workspace(self):
        """Test resolve_module_path without workspace root."""
        resolver = ImportResolver(workspace_root=None)
        result = resolver.resolve_module_path("some.module")
        assert result is None

    def test_resolve_full_class_path_simple(self, resolver):
        """Test resolve_full_class_path with simple class path."""
        code = "pn.widgets.Button"
        tree = parser.parse(code)
        # Find the attribute node (dotted name like pn.widgets.Button)
        attr_nodes = [node for node in walk_tree(tree.root_node) if node.type == "attribute"]
        assert len(attr_nodes) > 0
        # Get the first (top-level) attribute node which contains the full path
        result = resolver.resolve_full_class_path(attr_nodes[0])
        assert result == "panel.widgets.Button"  # pn resolves to panel

    def test_resolve_full_class_path_unknown_alias(self, resolver):
        """Test resolve_full_class_path with unknown alias."""
        code = "unknown.widgets.Button"
        tree = parser.parse(code)
        # Find the attribute node
        attr_nodes = [node for node in walk_tree(tree.root_node) if node.type == "attribute"]
        assert len(attr_nodes) > 0
        # Get the first (top-level) attribute node which contains the full path
        result = resolver.resolve_full_class_path(attr_nodes[0])
        assert result == "unknown.widgets.Button"  # Should use as-is

    def test_resolve_full_class_path_no_parts(self, resolver):
        """Test resolve_full_class_path with empty node."""
        code = "x"  # Simple name, not a complex path
        tree = parser.parse(code)
        # Find a simple identifier node
        id_nodes = [node for node in walk_tree(tree.root_node) if node.type == "identifier"]
        assert len(id_nodes) == 1

        # Simple identifier should return just the name
        result = resolver.resolve_full_class_path(id_nodes[0])
        assert result == "x"

    def test_analyze_imported_module_no_func(self):
        """Test analyze_imported_module without analyze_file_func."""
        resolver = ImportResolver(analyze_file_func=None)
        result = resolver.analyze_imported_module("test.module")

        expected = {"param_classes": {}, "imports": {}, "type_errors": []}
        assert result == expected

    def test_analyze_imported_module_cached(self, resolver):
        """Test analyze_imported_module with cached result."""
        # Pre-populate cache
        cached_result = {"param_classes": {"Cached": "class"}, "imports": {}, "type_errors": []}
        resolver.module_cache["test.module"] = cached_result

        result = resolver.analyze_imported_module("test.module")
        assert result == cached_result

    def test_get_imported_param_class_info_no_import(self, resolver):
        """Test get_imported_param_class_info with unknown import."""
        result = resolver.get_imported_param_class_info("TestClass", "unknown_import")
        assert result is None

    def test_get_imported_param_class_info_dotted_import(self, resolver):
        """Test get_imported_param_class_info with dotted import."""
        # Mock a file that would be analyzed
        with pytest.MonkeyPatch().context() as m:
            # Mock file system operations to avoid actual file I/O
            def mock_open(*args, **kwargs):
                class MockFile:
                    def read(self):
                        return "# mock file content"

                    def __enter__(self):
                        return self

                    def __exit__(self, *args):
                        pass

                return MockFile()

            m.setattr("builtins.open", mock_open)

            # Test with Button which maps to "panel.widgets.Button"
            result = resolver.get_imported_param_class_info("Button", "Button", "/test/file.py")
            # Since we have a mock analyze function, this should work
            # but will fail on file operations, so we expect None
            assert result is None

    def test_get_imported_param_class_info_simple_import(self, resolver):
        """Test get_imported_param_class_info with simple import."""
        # Mock a file system operation that will fail
        with pytest.MonkeyPatch().context() as m:

            def mock_open(*args, **kwargs):
                msg = "File not found"
                raise OSError(msg)

            m.setattr("builtins.open", mock_open)

            result = resolver.get_imported_param_class_info("TestClass", "param", "/test/file.py")
            assert result is None  # Should handle file errors gracefully

    def test_resolver_state_isolation(self):
        """Test that resolver instances maintain their own state."""
        # Create two resolvers with different imports
        resolver1 = ImportResolver(imports={"mod1": "module1"})
        resolver2 = ImportResolver(imports={"mod2": "module2"})

        # Each resolver should only know about its own imports
        assert "mod1" in resolver1.imports
        assert "mod1" not in resolver2.imports
        assert "mod2" in resolver2.imports
        assert "mod2" not in resolver1.imports

        # Test independent caches
        resolver1.module_cache["test1"] = {"param_classes": {}, "imports": {}, "type_errors": []}
        resolver2.module_cache["test2"] = {"param_classes": {}, "imports": {}, "type_errors": []}

        assert "test1" in resolver1.module_cache
        assert "test1" not in resolver2.module_cache
        assert "test2" in resolver2.module_cache
        assert "test2" not in resolver1.module_cache

    def test_imports_update_independently(self):
        """Test that import handling updates resolver state independently."""
        resolver = ImportResolver()

        # Initially empty
        assert resolver.imports == {}

        # Add an import
        code = "import test_module"
        tree = parser.parse(code)
        import_nodes = [
            node for node in walk_tree(tree.root_node) if node.type == "import_statement"
        ]
        resolver.handle_import(import_nodes[0])

        # Should have the import
        assert "test_module" in resolver.imports
        assert resolver.imports["test_module"] == "test_module"

    def test_handle_import_from_edge_cases(self, resolver):
        """Test handle_import_from with edge cases."""
        # Test with relative import (from . import something)
        code = "from . import local_module"
        tree = parser.parse(code)
        import_nodes = [
            node for node in walk_tree(tree.root_node) if node.type == "import_from_statement"
        ]

        if import_nodes:  # Only test if tree-sitter can parse this
            resolver.handle_import_from(import_nodes[0])
            # Relative imports may or may not be handled depending on implementation

    def test_module_cache_file_cache_interaction(self, resolver):
        """Test interaction between module_cache and file_cache."""
        # This tests the caching logic paths in analyze_imported_module

        # Mock file cache entry
        file_result = {"param_classes": {"FileClass": "data"}, "imports": {}, "type_errors": []}
        resolver.file_cache["/test/path.py"] = file_result

        # Mock the path resolution to return our cached file path
        original_resolve = resolver.resolve_module_path
        resolver.resolve_module_path = lambda module, path=None: "/test/path.py"

        try:
            result = resolver.analyze_imported_module("test.module")

            # Should return the file cache result and update module cache
            assert result == file_result
            assert resolver.module_cache["test.module"] == file_result
        finally:
            # Restore original method
            resolver.resolve_module_path = original_resolve
