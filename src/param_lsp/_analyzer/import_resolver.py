"""
Import and module resolution utilities.
Handles parsing imports and resolving module paths.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

from .parso_utils import get_children, get_value

if TYPE_CHECKING:
    from parso.tree import NodeOrLeaf


class AnalysisResult(TypedDict):
    """Type definition for analysis result dictionaries."""

    param_classes: dict[str, object]  # Using object for now, would be ParameterizedInfo
    imports: dict[str, str]
    type_errors: list[dict]


class ImportResolver:
    """Handles import parsing and module resolution."""

    def __init__(self, workspace_root: str | None = None):
        self.workspace_root = Path(workspace_root) if workspace_root else None
        self.imports: dict[str, str] = {}
        self.module_cache: dict[str, AnalysisResult] = {}
        self.file_cache: dict[str, AnalysisResult] = {}

    def handle_import(self, node: "NodeOrLeaf") -> None:
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

    def handle_import_from(self, node: "NodeOrLeaf") -> None:
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
        self, module_name: str, current_file_path: str | None = None
    ) -> str | None:
        """Resolve a module name to a file path."""
        if not self.workspace_root:
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