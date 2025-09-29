"""
Import and module resolution utilities.
Handles parsing imports and resolving module paths.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

from param_lsp._types import AnalysisResult, ImportDict, ParsoNode

from .parso_utils import get_children, get_value

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

    def handle_import(self, node: ParsoNode) -> None:
        """Handle 'import' statements (parso node)."""
        # For parso import_name nodes, parse the import statement
        for child in get_children(node):
            if child.type == "dotted_as_name":
                # Handle "import module as alias"
                module_name = None
                alias_name = None
                for part in get_children(child):
                    if part.type == "name":
                        if module_name is None:
                            module_name = get_value(part)
                        else:
                            alias_name = get_value(part)
                if module_name:
                    self.imports[alias_name or module_name] = module_name
            elif child.type == "dotted_name":
                # Handle "import module"
                module_name = get_value(child)
                if module_name:
                    self.imports[module_name] = module_name
            elif child.type == "name" and get_value(child) not in ("import", "as"):
                # Simple case: "import module"
                module_name = get_value(child)
                if module_name:
                    self.imports[module_name] = module_name

    def handle_import_from(self, node: ParsoNode) -> None:
        """Handle 'from ... import ...' statements (parso node)."""
        # For parso import_from nodes, parse the from...import statement
        module_name = None
        import_names = []

        # First pass: find module name and collect import names
        for child in get_children(node):
            if (
                child.type == "name"
                and module_name is None
                and get_value(child) not in ("from", "import")
            ) or (child.type == "dotted_name" and module_name is None):
                module_name = get_value(child)
            elif child.type == "import_as_names":
                for name_child in get_children(child):
                    if name_child.type == "import_as_name":
                        # Handle "from module import name as alias"
                        import_name = None
                        alias_name = None
                        for part in get_children(name_child):
                            if part.type == "name":
                                if import_name is None:
                                    import_name = get_value(part)
                                else:
                                    alias_name = get_value(part)
                        if import_name:
                            import_names.append((import_name, alias_name))
                    elif name_child.type == "name":
                        # Handle "from module import name"
                        name_value = get_value(name_child)
                        if name_value:
                            import_names.append((name_value, None))
            elif (
                child.type == "name"
                and get_value(child) not in ("from", "import")
                and module_name is not None
            ):
                # Handle simple "from module import name" where name is a direct child
                child_value = get_value(child)
                if child_value:
                    import_names.append((child_value, None))

        # Second pass: register all imports
        if module_name:
            for import_name, alias_name in import_names:
                full_name = f"{module_name}.{import_name}"
                self.imports[alias_name or import_name] = full_name

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
        """Resolve the full class path from a parso power/atom_expr node like pn.widgets.IntSlider."""
        parts = []
        for child in get_children(base):
            if child.type == "name":
                parts.append(get_value(child))
            elif child.type == "trailer":
                parts.extend(
                    [
                        get_value(trailer_child)
                        for trailer_child in get_children(child)
                        if trailer_child.type == "name"
                    ]
                )

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
