"""
Import and module resolution utilities.
Handles parsing imports and resolving module paths.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from param_lsp._treesitter import get_children, get_value
from param_lsp._types import AnalysisResult, ImportDict

if TYPE_CHECKING:
    from tree_sitter import Node

logger = logging.getLogger(__name__)


class ImportResolver:
    """Resolves imports and module paths for cross-file analysis.

    This class provides comprehensive import resolution capabilities for
    analyzing Parameterized classes across multiple files and modules.
    It handles both local imports (within the workspace) and external
    library imports.

    Key capabilities:
    - Parses and resolves import statements
    - Resolves module paths relative to workspace
    - Handles both absolute and relative imports
    - Caches analyzed modules for performance
    - Resolves full class paths for external libraries
    - Manages cross-file parameter inheritance

    The resolver maintains caches of analyzed modules and files to
    avoid redundant analysis and improve performance.

    Attributes:
        workspace_root: Root directory of the workspace
        imports: Import mappings for the current file
        module_cache: Cache of analyzed modules
        file_cache: Cache of analyzed files
    """

    def __init__(
        self,
        workspace_root: str | None = None,
        imports: ImportDict | None = None,
        module_cache: dict[str, AnalysisResult] | None = None,
        file_cache: dict[str, AnalysisResult] | None = None,
        analyze_file_func=None,
    ):
        self.workspace_root = Path(workspace_root) if workspace_root else None
        self.imports: ImportDict = imports if imports is not None else {}
        self.module_cache: dict[str, AnalysisResult] = (
            module_cache if module_cache is not None else {}
        )
        self.file_cache: dict[str, AnalysisResult] = file_cache if file_cache is not None else {}
        self.analyze_file_func = analyze_file_func

    def handle_import(self, node: Node) -> None:
        """Handle 'import' statements (tree-sitter node)."""
        # Tree-sitter import_statement structure
        for child in get_children(node):
            if child.type == "aliased_import":
                # Handle "import module as alias"
                name_node = child.child_by_field_name("name")
                alias_node = child.child_by_field_name("alias")
                if name_node:
                    module_name = self._reconstruct_dotted_name(name_node)
                    alias_name = get_value(alias_node) if alias_node else None
                    if module_name:
                        self.imports[alias_name or module_name] = module_name
            elif child.type in ("dotted_name", "identifier"):
                # Handle "import module"
                module_name = self._reconstruct_dotted_name(child)
                if module_name:
                    self.imports[module_name] = module_name

    def handle_import_from(self, node: Node) -> None:
        """Handle 'from ... import ...' statements (tree-sitter node)."""
        # Tree-sitter import_from_statement has 'module_name' field
        module_node = node.child_by_field_name("module_name")
        if not module_node:
            return

        module_name = self._reconstruct_dotted_name(module_node)
        if not module_name:
            return

        # Find imported names - look for aliased_import, dotted_name, or identifier children
        for child in get_children(node):
            if child.type == "aliased_import":
                # Handle "from module import name as alias"
                name_node = child.child_by_field_name("name")
                alias_node = child.child_by_field_name("alias")
                if name_node:
                    import_name = self._reconstruct_dotted_name(name_node)
                    alias_name = get_value(alias_node) if alias_node else None
                    if import_name:
                        full_name = f"{module_name}.{import_name}"
                        self.imports[alias_name or import_name] = full_name
            elif child.type in ("dotted_name", "identifier") and child != module_node:
                # Handle "from module import name" or "from module import dotted.name"
                import_name = self._reconstruct_dotted_name(child)
                if import_name and import_name not in ("from", "import"):
                    full_name = f"{module_name}.{import_name}"
                    # For dotted imports like "from pkg import sub.module", use the last part as the key
                    key = import_name.split(".")[-1] if "." in import_name else import_name
                    self.imports[key] = full_name

    def _reconstruct_dotted_name(self, node: Node) -> str | None:
        """Reconstruct a dotted name from a tree-sitter node."""
        if node.type == "identifier":
            return get_value(node)

        if node.type == "dotted_name":
            parts = [
                get_value(child) for child in get_children(node) if child.type == "identifier"
            ]
            valid_parts = [part for part in parts if part is not None]
            return ".".join(valid_parts) if valid_parts else None

        if node.type == "attribute":
            # Recursively build dotted name from attribute chain
            obj_node = node.child_by_field_name("object")
            attr_node = node.child_by_field_name("attribute")
            if obj_node and attr_node:
                obj_name = self._reconstruct_dotted_name(obj_node)
                attr_name = get_value(attr_node)
                if obj_name and attr_name:
                    return f"{obj_name}.{attr_name}"

        return get_value(node)

    def resolve_module_path(
        self, module_name: str | None, current_file_path: str | None = None
    ) -> str | None:
        """Resolve a module name to a file path."""
        if not self.workspace_root or module_name is None:
            return None

        # Handle relative imports
        if module_name.startswith("."):
            if not current_file_path:
                return None
            current_dir = Path(current_file_path).parent
            # Convert relative module name to absolute path
            parts = module_name.lstrip(".").split(".")
            target_path = current_dir
            for part in parts:
                if part:
                    target_path = target_path / part

            # Try .py file
            py_file = target_path.with_suffix(".py")
            if py_file.exists():
                return str(py_file)

            # Try package __init__.py
            init_file = target_path / "__init__.py"
            if init_file.exists():
                return str(init_file)

            return None

        # Handle absolute imports
        parts = module_name.split(".")

        # Try in workspace root
        target_path = self.workspace_root
        for part in parts:
            target_path = target_path / part

        # Try .py file
        py_file = target_path.with_suffix(".py")
        if py_file.exists():
            return str(py_file)

        # Try package __init__.py
        init_file = target_path / "__init__.py"
        if init_file.exists():
            return str(init_file)

        # Try searching in Python path (for installed packages)
        try:
            spec = importlib.util.find_spec(module_name)
            if spec and spec.origin and spec.origin.endswith(".py"):
                return spec.origin
        except (ImportError, ValueError, ModuleNotFoundError):
            pass

        return None

    def resolve_full_class_path(self, base) -> str | None:
        """Resolve the full class path from a tree-sitter node like pn.widgets.IntSlider."""
        parts = []

        # Extract parts based on node type
        if base.type == "identifier":
            parts.append(get_value(base))
        elif base.type == "attribute":
            # Recursively extract parts from attribute chain
            current = base
            while current:
                if current.type == "attribute":
                    attr_node = current.child_by_field_name("attribute")
                    if attr_node:
                        parts.insert(0, get_value(attr_node))
                    current = current.child_by_field_name("object")
                elif current.type == "identifier":
                    parts.insert(0, get_value(current))
                    current = None
                else:
                    break
        elif base.type == "call":
            # For call nodes, extract the function being called
            func_node = base.child_by_field_name("function")
            if func_node:
                return self.resolve_full_class_path(func_node)

        if parts:
            # Resolve the root module through imports
            root_alias = parts[0]
            if root_alias in self.imports:
                full_module_name = self.imports[root_alias]
                # Replace the alias with the full module name
                parts[0] = full_module_name
                return ".".join(parts)
            else:
                # Use the alias directly if no import mapping found
                return ".".join(parts)

        return None

    def analyze_imported_module(
        self, module_name: str | None, current_file_path: str | None = None
    ) -> AnalysisResult:
        """Analyze an imported module and cache the results."""
        if module_name is None:
            return AnalysisResult(param_classes={}, imports={}, type_errors=[])

        # Check cache first
        if module_name in self.module_cache:
            return self.module_cache[module_name]

        # Resolve module path
        module_path = self.resolve_module_path(module_name, current_file_path)
        if not module_path:
            return AnalysisResult(param_classes={}, imports={}, type_errors=[])

        # Check file cache
        if module_path in self.file_cache:
            result = self.file_cache[module_path]
            self.module_cache[module_name] = result
            return result

        # Read and analyze the module if analyze_file_func is provided
        if not self.analyze_file_func:
            return AnalysisResult(param_classes={}, imports={}, type_errors=[])

        try:
            with open(module_path, encoding="utf-8") as f:
                content = f.read()

            # Use the provided analyze_file function
            result = self.analyze_file_func(content, module_path)

            # Cache the result
            self.file_cache[module_path] = result
            self.module_cache[module_name] = result

            return result
        except (OSError, UnicodeDecodeError):
            return AnalysisResult(param_classes={}, imports={}, type_errors=[])

    def get_imported_param_class_info(
        self, class_name: str, import_name: str, current_file_path: str | None = None
    ):
        """Get parameter information for a class imported from another module."""
        # Get the full module name from imports
        full_import_name = self.imports.get(import_name)
        if not full_import_name:
            return None

        # Parse the import to get module name and class name
        if "." in full_import_name:
            # Handle "from module import Class" -> "module.Class"
            module_name, imported_class_name = full_import_name.rsplit(".", 1)
        else:
            # Handle "import module" -> "module"
            module_name = full_import_name
            imported_class_name = class_name

        # Analyze the imported module
        module_analysis = self.analyze_imported_module(module_name, current_file_path)
        if not module_analysis:
            return None

        # Check if the class exists in the imported module
        param_classes_dict = module_analysis.get("param_classes", {})
        if isinstance(param_classes_dict, dict) and imported_class_name in param_classes_dict:
            class_info = param_classes_dict[imported_class_name]
            # If it's a ParameterizedInfo object, return it
            if hasattr(class_info, "parameters"):
                return class_info

        return None
