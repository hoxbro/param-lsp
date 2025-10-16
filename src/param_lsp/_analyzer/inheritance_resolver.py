"""
Inheritance resolution for parameter classes.
Handles parameter inheritance from parent classes both local and external.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from param_lsp._treesitter import get_class_bases, get_value

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from tree_sitter import Node

    from param_lsp.models import ParameterInfo, ParameterizedInfo


class InheritanceResolver:
    """Resolves parameter inheritance hierarchies for Parameterized classes.

    This class handles the complex task of resolving parameter inheritance
    from parent classes, supporting both local classes (defined in the same
    codebase) and external classes (from libraries like Panel, HoloViews).

    Key capabilities:
    - Identifies Parameterized base classes from AST nodes
    - Collects inherited parameters from parent classes
    - Handles multi-level inheritance chains
    - Resolves external class inheritance via runtime introspection
    - Manages parameter overriding (child parameters override parent ones)

    The resolver works with both static analysis (for local classes) and
    runtime introspection (for external library classes) to provide
    complete inheritance resolution.

    Attributes:
        param_classes: Local parameterized classes in the codebase
        external_param_classes: External parameterized classes from libraries
        imports: Import mappings for resolving class references
    """

    def __init__(
        self,
        param_classes: dict[str, ParameterizedInfo],
        external_param_classes: dict[str, ParameterizedInfo],
        imports: dict[str, str],
        get_imported_param_class_info_func,
        analyze_external_class_ast_func,
        resolve_full_class_path_func,
    ):
        self.param_classes = param_classes
        self.external_param_classes = external_param_classes
        self.imports = imports
        self.get_imported_param_class_info = get_imported_param_class_info_func
        self.analyze_external_class_ast = analyze_external_class_ast_func
        self.resolve_full_class_path = resolve_full_class_path_func

    def is_param_base(self, base: Node, current_file_path: str | None = None) -> bool:
        """Check if a base class is param.Parameterized or similar (tree-sitter node).

        Args:
            base: The base class AST node to check
            current_file_path: Path to the current file being analyzed (for cross-file resolution)
        """
        if base.type == "identifier":
            base_name = get_value(base)
            if not base_name:
                return False
            # Check if it's a direct param.Parameterized import
            if (
                base_name in ["Parameterized"]
                and base_name in self.imports
                and "param.Parameterized" in self.imports[base_name]
            ):
                return True
            # Check if it's a known param class (from inheritance)
            if base_name in self.param_classes:
                return True
            # Check if it's an imported param class
            imported_class_info = self.get_imported_param_class_info(
                base_name,
                base_name,
                current_file_path,
            )
            if imported_class_info:
                return True
        elif base.type == "attribute":
            # Handle dotted names like param.Parameterized or pn.widgets.IntSlider
            # In tree-sitter, attribute has 'object' and 'attribute' fields
            parts = []

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

            if len(parts) >= 2:
                # Handle simple case: param.Parameterized
                if len(parts) == 2:
                    module, class_name = parts
                    if (module == "param" and class_name == "Parameterized") or (
                        module in self.imports
                        and self.imports[module].endswith("param")
                        and class_name == "Parameterized"
                    ):
                        return True

                # Handle complex attribute access like pn.widgets.IntSlider
                full_class_path = self.resolve_full_class_path(base)
                # Check if this external class is a Parameterized class
                class_info = self.analyze_external_class_ast(full_class_path)
                if class_info:
                    return True
        return False

    def collect_inherited_parameters(
        self, node: Node, current_file_path: str | None = None
    ) -> dict[str, ParameterInfo]:
        """Collect parameters from parent classes in inheritance hierarchy (tree-sitter node)."""
        inherited_parameters = {}  # Last wins

        bases = get_class_bases(node)
        for base in bases:
            if base.type == "identifier":
                parent_class_name = get_value(base)
                if not parent_class_name:
                    continue

                # First check if it's a local class in the same file
                if parent_class_name in self.param_classes:
                    # Get parameters from the parent class
                    parent_class_info = self.param_classes[parent_class_name]
                    for param_name, param_info in parent_class_info.parameters.items():
                        inherited_parameters[param_name] = param_info  # noqa: PERF403

                # If not found locally, check if it's an imported class
                else:
                    # Check if this class was imported
                    imported_class_info = self.get_imported_param_class_info(
                        parent_class_name, parent_class_name, current_file_path
                    )

                    if imported_class_info:
                        for param_name, param_info in imported_class_info.parameters.items():
                            inherited_parameters[param_name] = param_info  # noqa: PERF403

            elif base.type in ("attribute", "call"):
                # Handle complex attribute access like pn.widgets.IntSlider
                full_class_path = self.resolve_full_class_path(base)
                # Skip analysis of param.Parameterized itself (base class has no parameters)
                if full_class_path == "param.Parameterized":
                    continue  # param.Parameterized itself has no custom parameters to inherit

                # Check if this external class is a Parameterized class
                class_info = self.analyze_external_class_ast(full_class_path)
                if class_info:
                    for param_name, param_info in class_info.parameters.items():
                        inherited_parameters[param_name] = param_info  # noqa: PERF403

        return inherited_parameters
