"""
Type checking and validation for parameter assignments.
Handles both class parameter defaults and runtime assignments.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict, cast

from .parso_utils import (
    find_all_parameter_assignments,
    get_children,
    get_value,
    has_attribute_target,
    is_assignment_stmt,
    is_function_call,
    walk_tree,
)
from .parameter_extractor import (
    extract_boolean_value,
    extract_numeric_value,
    get_keyword_arguments,
    is_none_value,
    resolve_parameter_class,
)

if TYPE_CHECKING:
    from parso.tree import BaseNode, NodeOrLeaf


class TypeErrorDict(TypedDict):
    """Type definition for type error dictionaries."""

    line: int
    col: int
    end_line: int
    end_col: int
    message: str
    severity: str
    code: str


class TypeChecker:
    """Handles type checking and validation for parameter assignments."""

    def __init__(
        self,
        param_type_map: dict,
        param_classes: dict,
        imports: dict[str, str],
        is_parameter_assignment_func,
    ):
        self.param_type_map = param_type_map
        self.param_classes = param_classes
        self.imports = imports
        self.is_parameter_assignment = is_parameter_assignment_func
        self.type_errors: list[TypeErrorDict] = []

    def check_parameter_types(self, tree: NodeOrLeaf, lines: list[str]) -> list[TypeErrorDict]:
        """Check for type errors in parameter assignments."""
        self.type_errors.clear()

        for node in walk_tree(tree):
            if node.type == "classdef":
                self._check_class_parameter_defaults(cast("BaseNode", node), lines)

            # Check runtime parameter assignments like obj.param = value
            elif node.type == "expr_stmt" and is_assignment_stmt(node):
                if has_attribute_target(node):
                    self._check_runtime_parameter_assignment_parso(node, lines)

            # Check constructor calls like MyClass(x="A")
            elif node.type in ("power", "atom_expr") and is_function_call(node):
                self._check_constructor_parameter_types(node, lines)

        return self.type_errors.copy()


    def _check_class_parameter_defaults(self, class_node: BaseNode, lines: list[str]) -> None:
        """Check parameter default types within a class definition."""
        # This would need access to analyzer's param_classes and other methods
        # For now, this is a placeholder that shows the structure

    def _check_runtime_parameter_assignment_parso(
        self, node: NodeOrLeaf, lines: list[str]
    ) -> None:
        """Check runtime parameter assignments like obj.param = value (parso version)."""
        # This is a complex method that needs access to analyzer's context
        # For now, this is a placeholder that shows the structure

    def _infer_value_type(self, node: NodeOrLeaf) -> type | None:
        """Infer Python type from parso node."""
        if hasattr(node, "type"):
            if node.type == "number":
                # Check if it's a float or int
                value = get_value(node)
                if value is None:
                    return None
                if "." in value:
                    return float
                else:
                    return int
            elif node.type == "string":
                return str
            elif node.type == "name":
                if get_value(node) in {"True", "False"}:
                    return bool
                elif get_value(node) == "None":
                    return type(None)
                # Could be a variable - would need more sophisticated analysis
                return None
            elif node.type == "keyword":
                if get_value(node) in {"True", "False"}:
                    return bool
                elif get_value(node) == "None":
                    return type(None)
                return None
            elif node.type == "atom":
                # Check for list, dict, tuple
                if get_children(node) and get_value(get_children(node)[0]) == "[":
                    return list
                elif get_children(node) and get_value(get_children(node)[0]) == "{":
                    return dict
                elif get_children(node) and get_value(get_children(node)[0]) == "(":
                    return tuple
        return None

    def _is_boolean_literal(self, node: NodeOrLeaf) -> bool:
        """Check if a parso node represents a boolean literal (True/False)."""
        return (node.type == "name" and get_value(node) in ("True", "False")) or (
            node.type == "keyword" and get_value(node) in ("True", "False")
        )

    def _format_expected_types(self, expected_types: tuple) -> str:
        """Format expected types for error messages."""
        if len(expected_types) == 1:
            return expected_types[0].__name__
        else:
            type_names = [t.__name__ for t in expected_types]
            return " or ".join(type_names)

    def _create_type_error(
        self, node: NodeOrLeaf, message: str, code: str, severity: str = "error"
    ) -> None:
        """Helper function to create and append a type error (parso version)."""
        # Get position information from parso node
        if hasattr(node, "start_pos"):
            line = node.start_pos[0] - 1  # Convert to 0-based
            col = node.start_pos[1]
            end_line = node.end_pos[0] - 1 if hasattr(node, "end_pos") else line
            end_col = node.end_pos[1] if hasattr(node, "end_pos") else col
        else:
            # Fallback if position info is not available
            line = 0
            col = 0
            end_line = 0
            end_col = 0

        self.type_errors.append(
            {
                "line": line,
                "col": col,
                "end_line": end_line,
                "end_col": end_col,
                "message": message,
                "severity": severity,
                "code": code,
            }
        )

    def _parse_bounds_format(
        self, bounds: tuple
    ) -> tuple[float | None, float | None, bool, bool] | None:
        """Parse bounds tuple into (min_val, max_val, left_inclusive, right_inclusive)."""
        if len(bounds) == 2:
            min_val, max_val = bounds
            left_inclusive, right_inclusive = True, True  # Default to inclusive
            return min_val, max_val, left_inclusive, right_inclusive
        elif len(bounds) == 4:
            min_val, max_val, left_inclusive, right_inclusive = bounds
            return min_val, max_val, left_inclusive, right_inclusive
        else:
            return None

    def _format_bounds_description(
        self,
        min_val: float | None,
        max_val: float | None,
        left_inclusive: bool,
        right_inclusive: bool,
    ) -> str:
        """Format bounds into a human-readable string with proper bracket notation."""
        min_str = str(min_val) if min_val is not None else "-∞"
        max_str = str(max_val) if max_val is not None else "∞"
        left_bracket = "[" if left_inclusive else "("
        right_bracket = "]" if right_inclusive else ")"
        return f"{left_bracket}{min_str}, {max_str}{right_bracket}"
