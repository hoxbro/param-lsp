"""
Parameter validation for parameter assignments.
Handles type checking, bounds validation, constraint checking for both
class parameter defaults and runtime assignments.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

from param_lsp.constants import DEPRECATED_PARAMETER_TYPES, PARAM_TYPE_MAP

from .parameter_extractor import (
    extract_boolean_value,
    extract_numeric_value,
    get_keyword_arguments,
    is_none_value,
    resolve_parameter_class,
)
from .parso_utils import (
    find_all_parameter_assignments,
    get_children,
    get_class_name,
    get_value,
    is_assignment_stmt,
    is_function_call,
    walk_tree,
)

if TYPE_CHECKING:
    from param_lsp._analyzer.static_external_analyzer import ExternalClassInspector
    from param_lsp._types import (
        ExternalParamClassDict,
        ImportDict,
        ParamClassDict,
        ParsoNode,
        TypeErrorDict,
    )


class ParameterValidator:
    """Validates parameter assignments in Parameterized classes.

    This class provides comprehensive validation for parameter assignments including:
    - Type checking (ensuring assigned values match parameter types)
    - Bounds validation (checking numeric values are within specified ranges)
    - Constraint checking (validating parameter-specific constraints)
    - Runtime assignment validation (checking obj.param = value statements)
    - Constructor parameter validation (checking MyClass(param=value) calls)

    The validator works with both local parameter classes and external library classes
    (like Panel widgets, HoloViews elements) to provide complete validation coverage.

    Attributes:
        param_classes: Local parameterized classes discovered in the code
        external_param_classes: External parameterized classes from libraries
        imports: Import mappings for resolving parameter types
        type_errors: List of validation errors found during analysis
    """

    def __init__(
        self,
        param_classes: ParamClassDict,
        external_param_classes: ExternalParamClassDict,
        imports: ImportDict,
        is_parameter_assignment_func,
        external_inspector: ExternalClassInspector,
        workspace_root: str | None = None,
    ):
        self.param_classes = param_classes
        self.external_param_classes = external_param_classes
        self.imports = imports
        self.is_parameter_assignment = is_parameter_assignment_func
        self.workspace_root = workspace_root
        self.external_inspector = external_inspector
        self.type_errors: list[TypeErrorDict] = []

    def check_parameter_types(
        self, tree: ParsoNode, lines: list[str], cached_nodes: list[ParsoNode] | None = None
    ) -> list[TypeErrorDict]:
        """Perform comprehensive parameter type validation on a parsed AST.

        Args:
            tree: The root parso AST node to validate
            lines: Source code lines for error reporting
            cached_nodes: Optional pre-computed list of all nodes for performance optimization

        Returns:
            List of type error dictionaries containing validation errors found

        This method performs three types of validation:
        1. Class parameter defaults (e.g., name = param.String(default=123))
        2. Runtime parameter assignments (e.g., obj.name = 123)
        3. Constructor parameter calls (e.g., MyClass(name=123))

        Each validation checks for type mismatches, bounds violations,
        and parameter-specific constraints.
        """
        self.type_errors.clear()

        # Use cached nodes if provided for performance optimization
        nodes_to_check = cached_nodes if cached_nodes is not None else walk_tree(tree)

        for node in nodes_to_check:
            if node.type == "classdef":
                self._check_class_parameter_defaults(node, lines)

            # Check runtime parameter assignments like obj.param = value
            elif node.type == "expr_stmt" and is_assignment_stmt(node):
                if self._has_attribute_target(node):
                    self._check_runtime_parameter_assignment_parso(node, lines)

            # Check constructor calls like MyClass(x="A")
            elif node.type in ("power", "atom_expr") and is_function_call(node):
                self._check_constructor_parameter_types(node, lines)

        return self.type_errors.copy()

    def _check_class_parameter_defaults(self, class_node: ParsoNode, lines: list[str]) -> None:
        """Check parameter default types within a class definition."""
        class_name = get_class_name(class_node)
        if not class_name or class_name not in self.param_classes:
            return

        for assignment_node, target_name in find_all_parameter_assignments(
            class_node, self.is_parameter_assignment
        ):
            self._check_parameter_default_type(assignment_node, target_name, lines)

    def _check_constructor_parameter_types(self, node: ParsoNode, lines: list[str]) -> None:
        """Check for type errors in constructor parameter calls like MyClass(x="A") (parso version)."""
        # Get the class name from the call
        class_name = self._get_instance_class(node)
        if not class_name:
            return

        # Check if this is a valid param class (local or external)
        is_valid_param_class = class_name in self.param_classes or (
            class_name in self.external_param_classes and self.external_param_classes[class_name]
        )

        if not is_valid_param_class:
            return

        # Get keyword arguments from the parso node
        kwargs = get_keyword_arguments(node)

        # Check each keyword argument passed to the constructor
        for param_name, param_value in kwargs.items():
            # Get the expected parameter type
            cls = self._get_parameter_type_from_class(class_name, param_name)
            if not cls:
                continue  # Skip if parameter not found (could be inherited or not a param)

            # Check if None is allowed for this parameter
            inferred_type = self._infer_value_type(param_value)
            if inferred_type is type(None):  # None value
                allow_None = self._get_parameter_allow_None(class_name, param_name)
                if allow_None:
                    continue  # None is allowed, skip further validation
                # If allow_None is False or not specified, continue with normal type checking

            # Check if assigned value matches expected type
            if cls in PARAM_TYPE_MAP:
                expected_types = PARAM_TYPE_MAP[cls]
                if not isinstance(expected_types, tuple):
                    expected_types = (expected_types,)

                # Special handling for Boolean parameters - they should only accept actual bool values
                if cls == "Boolean" and inferred_type and inferred_type is not bool:
                    # For parso nodes, check if it's a keyword node with True/False
                    is_bool_value = (
                        hasattr(param_value, "type")
                        and param_value.type == "keyword"
                        and get_value(param_value) in ("True", "False")
                    )
                    if not is_bool_value:
                        message = f"Cannot assign {inferred_type.__name__} to Boolean parameter '{param_name}' in {class_name}() constructor (expects True/False)"
                        self._create_type_error(node, message, "constructor-boolean-type-mismatch")
                elif inferred_type and not any(
                    (isinstance(inferred_type, type) and issubclass(inferred_type, t))
                    or inferred_type == t
                    for t in expected_types
                ):
                    message = f"Cannot assign {inferred_type.__name__} to parameter '{param_name}' of type {cls} in {class_name}() constructor (expects {self._format_expected_types(expected_types)})"
                    self._create_type_error(node, message, "constructor-type-mismatch")

            # Check bounds for numeric parameters in constructor calls
            self._check_constructor_bounds(node, class_name, param_name, cls, param_value)

            # Check container constraints (List item_type, Tuple length)
            self._check_constructor_container_constraints(
                node, class_name, param_name, cls, param_value
            )

    def _infer_value_type(self, node: ParsoNode) -> type | None:
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

    def _is_boolean_literal(self, node: ParsoNode) -> bool:
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
        self, node: ParsoNode | None, message: str, code: str, severity: str = "error"
    ) -> None:
        """Helper function to create and append a type error (parso version)."""
        # Get position information from parso node
        if node is not None and hasattr(node, "start_pos"):
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

    def _has_attribute_target(self, node: ParsoNode) -> bool:
        """Check if assignment has an attribute target (like obj.attr = value)."""
        for child in get_children(node):
            if child.type in ("power", "atom_expr"):
                # Check if this node has attribute access (trailer with '.')
                for sub_child in get_children(child):
                    if (
                        sub_child.type == "trailer"
                        and get_children(sub_child)
                        and get_value(get_children(sub_child)[0]) == "."
                    ):
                        return True
            elif child.type == "operator" and get_value(child) == "=":
                break
        return False

    def _check_constructor_bounds(
        self,
        node: ParsoNode,
        class_name: str,
        param_name: str,
        cls: str,
        param_value: ParsoNode,
    ) -> None:
        """Check if constructor parameter value is within parameter bounds."""
        # Only check bounds for numeric types
        if cls not in ["Number", "Integer"]:
            return

        # Get bounds for this parameter
        bounds = self._get_parameter_bounds(class_name, param_name)
        if not bounds:
            return

        # Extract numeric value from parameter value
        assigned_numeric = extract_numeric_value(param_value)
        if assigned_numeric is None:
            return

        # Parse bounds format
        parsed_bounds = self._parse_bounds_format(bounds)
        if not parsed_bounds:
            return
        min_val, max_val, left_inclusive, right_inclusive = parsed_bounds

        # Check if value is within bounds based on inclusivity
        violates_lower = False
        violates_upper = False

        if min_val is not None:
            if left_inclusive:
                violates_lower = assigned_numeric < min_val
            else:
                violates_lower = assigned_numeric <= min_val

        if max_val is not None:
            if right_inclusive:
                violates_upper = assigned_numeric > max_val
            else:
                violates_upper = assigned_numeric >= max_val

        if violates_lower or violates_upper:
            bound_description = self._format_bounds_description(
                min_val, max_val, left_inclusive, right_inclusive
            )
            message = f"Value {assigned_numeric} for parameter '{param_name}' in {class_name}() constructor is outside bounds {bound_description}"
            self._create_type_error(node, message, "constructor-bounds-violation")

    def _check_constructor_container_constraints(
        self,
        node: ParsoNode,
        class_name: str,
        param_name: str,
        cls: str,
        param_value: ParsoNode,
    ) -> None:
        """Check container constraints for List item_type and Tuple length."""
        if cls == "List":
            self._check_list_item_type_constructor(node, class_name, param_name, param_value)
        elif cls == "Tuple":
            self._check_tuple_length_constructor(node, class_name, param_name, param_value)

    def _check_list_item_type_constructor(
        self,
        node: ParsoNode,
        class_name: str,
        param_name: str,
        param_value: ParsoNode,
    ) -> None:
        """Check that all items in a List match the specified item_type."""
        # Get item_type constraint for this parameter
        item_type = self._get_parameter_item_type(class_name, param_name)
        if not item_type:
            return

        # Extract list items from the parameter value
        list_items = self._extract_list_items(param_value)
        if not list_items:
            return

        # Check each item against the expected type
        for i, item in enumerate(list_items):
            item_type_inferred = self._infer_value_type(item)
            if item_type_inferred and not self._is_type_compatible(item_type_inferred, item_type):
                message = f"Item {i} in List parameter '{param_name}' has type {item_type_inferred.__name__}, expected {item_type.__name__}"
                self._create_type_error(node, message, "list-item-type-mismatch")

    def _check_tuple_length_constructor(
        self,
        node: ParsoNode,
        class_name: str,
        param_name: str,
        param_value: ParsoNode,
    ) -> None:
        """Check that Tuple has the expected length."""
        # Get length constraint for this parameter
        expected_length = self._get_parameter_length(class_name, param_name)
        if expected_length is None:
            return

        # Extract tuple items from the parameter value
        tuple_items = self._extract_tuple_items(param_value)
        if tuple_items is None:
            return

        actual_length = len(tuple_items)
        if actual_length != expected_length:
            message = f"Tuple parameter '{param_name}' has {actual_length} elements, expected {expected_length}"
            self._create_type_error(node, message, "tuple-length-mismatch")

    def _check_parameter_default_type(
        self, node: ParsoNode, param_name: str, lines: list[str]
    ) -> None:
        """Check if parameter default value matches declared type (parso version)."""
        # Find the parameter call on the right side of the assignment
        param_call = None
        for child in get_children(node):
            if child.type in ("power", "atom_expr"):
                param_call = child
                break

        if not param_call:
            return

        # Resolve the actual parameter class type
        param_class_info = resolve_parameter_class(param_call, self.imports)
        if not param_class_info:
            return

        cls = param_class_info["type"]

        # Get default value and allow_None from keyword arguments
        kwargs = get_keyword_arguments(param_call)
        default_value = kwargs.get("default")
        allow_None_node = kwargs.get("allow_None")
        allow_None = (
            extract_boolean_value(allow_None_node)
            if "allow_None" in kwargs and allow_None_node is not None
            else None
        )

        # Param automatically sets allow_None=True when default=None
        if default_value is not None and is_none_value(default_value):
            allow_None = True

        if cls and default_value and cls in PARAM_TYPE_MAP:
            expected_types = PARAM_TYPE_MAP[cls]
            if not isinstance(expected_types, tuple):
                expected_types = (expected_types,)

            inferred_type = self._infer_value_type(default_value)

            # Check if None is allowed for this parameter
            if allow_None and inferred_type is type(None):
                return  # None is allowed, skip further validation

            # Special handling for Boolean parameters - they should only accept actual bool values
            if cls == "Boolean" and inferred_type and inferred_type is not bool:
                # For Boolean parameters, only accept actual boolean values
                if not (
                    default_value.type == "name" and get_value(default_value) in ("True", "False")
                ):
                    message = f"Parameter '{param_name}' of type Boolean expects bool but got {inferred_type.__name__}"
                    self._create_type_error(node, message, "boolean-type-mismatch")
            elif inferred_type and not any(
                (isinstance(inferred_type, type) and issubclass(inferred_type, t))
                or inferred_type == t
                for t in expected_types
            ):
                message = f"Parameter '{param_name}' of type {cls} expects {self._format_expected_types(expected_types)} but got {inferred_type.__name__}"
                self._create_type_error(node, message, "type-mismatch")

        # Check for deprecated parameter types
        self._check_deprecated_parameter_type(node, cls)

        # Check for additional parameter constraints
        self._check_parameter_constraints(node, param_name, lines)

    def _check_runtime_parameter_assignment_parso(self, node: ParsoNode, lines: list[str]) -> None:
        """Check runtime parameter assignments like obj.param = value (parso version)."""
        # Extract target and assigned value from parso expr_stmt node
        target = None
        assigned_value = None

        # Look for attribute target and assigned value
        for child in get_children(node):
            if child.type in ("power", "atom_expr"):
                # Check if this is an attribute access (obj.attr)
                has_attribute = False
                for sub_child in get_children(child):
                    if (
                        sub_child.type == "trailer"
                        and get_children(sub_child)
                        and get_value(get_children(sub_child)[0]) == "."
                    ):
                        has_attribute = True
                        break
                if has_attribute:
                    target = child
            elif child.type == "operator" and get_value(child) == "=":
                # Next non-operator child should be the assigned value
                continue
            elif target is not None and child.type != "operator":
                assigned_value = child
                break

        if not target or not assigned_value:
            return

        # Extract parameter name from the attribute access
        param_name = None
        for child in get_children(target):
            if (
                child.type == "trailer"
                and len(get_children(child)) >= 2
                and get_value(get_children(child)[0]) == "."
                and get_children(child)[1].type == "name"
            ):
                param_name = get_value(get_children(child)[1])
                break

        if not param_name:
            return

        # Determine the instance class
        instance_class = None

        # Check if this is a direct instantiation (has parentheses before the dot)
        has_call = False
        for child in get_children(target):
            if (
                child.type == "trailer"
                and len(get_children(child)) >= 2
                and get_value(get_children(child)[0]) == "("
                and get_value(get_children(child)[-1]) == ")"
            ):
                has_call = True
                break

        if has_call:
            # Case: MyClass().param = value (direct instantiation)
            instance_class = self._get_instance_class(target)
        else:
            # Case: instance_var.param = value
            # Try to find which param class has this parameter
            for class_name, class_info in self.param_classes.items():
                if param_name in class_info.parameters:
                    instance_class = class_name
                    break

            # If not found in local classes, check external param classes
            if not instance_class:
                for class_name, class_info in self.external_param_classes.items():
                    if class_info and param_name in class_info.parameters:
                        instance_class = class_name
                        break

        if not instance_class:
            return

        # Check if this is a valid param class
        is_valid_param_class = instance_class in self.param_classes or (
            instance_class in self.external_param_classes
            and self.external_param_classes[instance_class]
        )

        if not is_valid_param_class:
            return

        # Get the parameter type from the class definition
        cls = self._get_parameter_type_from_class(instance_class, param_name)
        if not cls:
            return

        # Check if assigned value matches expected type
        if cls in PARAM_TYPE_MAP:
            expected_types = PARAM_TYPE_MAP[cls]
            if not isinstance(expected_types, tuple):
                expected_types = (expected_types,)

            inferred_type = self._infer_value_type(assigned_value)

            # Check if None is allowed for this parameter
            if inferred_type is type(None):  # None value
                allow_None = self._get_parameter_allow_None(instance_class, param_name)
                if allow_None:
                    return  # None is allowed, skip further validation

            # Special handling for Boolean parameters
            if cls == "Boolean" and inferred_type and inferred_type is not bool:
                # For Boolean parameters, only accept actual boolean values
                if not self._is_boolean_literal(assigned_value):
                    message = f"Cannot assign {inferred_type.__name__} to Boolean parameter '{param_name}' (expects True/False)"
                    self._create_type_error(node, message, "runtime-boolean-type-mismatch")
            elif inferred_type and not any(
                (isinstance(inferred_type, type) and issubclass(inferred_type, t))
                or inferred_type == t
                for t in expected_types
            ):
                message = f"Cannot assign {inferred_type.__name__} to parameter '{param_name}' of type {cls} (expects {self._format_expected_types(expected_types)})"
                self._create_type_error(node, message, "runtime-type-mismatch")

        # Check bounds for numeric parameters
        self._check_runtime_bounds_parso(node, instance_class, param_name, cls, assigned_value)

    def _check_runtime_bounds_parso(
        self,
        node: ParsoNode,
        instance_class: str,
        param_name: str,
        cls: str,
        assigned_value: ParsoNode,
    ) -> None:
        """Check if assigned value is within parameter bounds (parso version)."""
        # Only check bounds for numeric types
        if cls not in ["Number", "Integer"]:
            return

        # Get bounds for this parameter
        bounds = self._get_parameter_bounds(instance_class, param_name)
        if not bounds:
            return

        # Extract numeric value from assigned value
        assigned_numeric = extract_numeric_value(assigned_value)
        if assigned_numeric is None:
            return

        # Parse bounds format
        parsed_bounds = self._parse_bounds_format(bounds)
        if not parsed_bounds:
            return
        min_val, max_val, left_inclusive, right_inclusive = parsed_bounds

        # Check if value is within bounds based on inclusivity
        violates_lower = False
        violates_upper = False

        if min_val is not None:
            if left_inclusive:
                violates_lower = assigned_numeric < min_val
            else:
                violates_lower = assigned_numeric <= min_val

        if max_val is not None:
            if right_inclusive:
                violates_upper = assigned_numeric > max_val
            else:
                violates_upper = assigned_numeric >= max_val

        if violates_lower or violates_upper:
            bound_description = self._format_bounds_description(
                min_val, max_val, left_inclusive, right_inclusive
            )
            message = f"Value {assigned_numeric} for parameter '{param_name}' is outside bounds {bound_description}"
            self._create_type_error(node, message, "bounds-violation")

    def _get_parameter_bounds(self, class_name: str, param_name: str) -> tuple | None:
        """Get parameter bounds from a class definition."""
        # Check local classes first
        if class_name in self.param_classes:
            param_info = self.param_classes[class_name].get_parameter(param_name)
            return param_info.bounds if param_info else None

        # Check external classes
        class_info = self.external_param_classes.get(class_name)
        if class_info:
            param_info = class_info.get_parameter(param_name)
            return param_info.bounds if param_info else None

        return None

    def _get_instance_class(self, call_node) -> str | None:
        """Get the class name from an instance creation call (parso version)."""
        # For parso nodes, we need to find the function name from the power/atom_expr structure
        if call_node.type in ("power", "atom_expr"):
            # First try to resolve the full class path for external classes
            full_class_path = self._resolve_full_class_path(call_node)
            # Check if this is an external Parameterized class
            class_info = self._analyze_external_class_ast(full_class_path)
            if class_info:
                # Return the full path as the class identifier for external classes
                return full_class_path

            # If not an external class, look for local class names
            # We need to find the class name that's actually being called
            # For Outer.Inner(), we want "Inner", not "Outer"

            # Find the last name before a function call (parentheses trailer)
            last_name = None
            for child in get_children(call_node):
                if child.type == "name":
                    last_name = get_value(child)
                elif child.type == "trailer":
                    if len(get_children(child)) >= 2 and get_children(child)[1].type == "name":
                        # This is a dot access like .Inner
                        last_name = get_value(get_children(child)[1])
                    elif (
                        len(get_children(child)) >= 1
                        and get_children(child)[0].type == "operator"
                        and get_value(get_children(child)[0]) == "("
                    ):
                        # This is the function call parentheses - return the last name we found
                        return last_name

            # If we found a name but no explicit function call, return the last name
            return last_name
        return None

    def _resolve_full_class_path(self, base) -> str | None:
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

    def _get_parameter_type_from_class(self, class_name: str, param_name: str) -> str | None:
        """Get the parameter type from a class definition."""
        # Check local classes first
        if class_name in self.param_classes:
            param_info = self.param_classes[class_name].get_parameter(param_name)
            return param_info.cls if param_info else None

        # Check external classes
        class_info = self.external_param_classes.get(class_name)
        if class_info:
            param_info = class_info.get_parameter(param_name)
            return param_info.cls if param_info else None

        return None

    def _get_parameter_allow_None(self, class_name: str, param_name: str) -> bool:
        """Get the allow_None setting for a parameter from a class definition."""
        # Check local classes first
        if class_name in self.param_classes:
            param_info = self.param_classes[class_name].get_parameter(param_name)
            return param_info.allow_None if param_info else False

        # Check external classes
        class_info = self.external_param_classes.get(class_name)
        if class_info:
            param_info = class_info.get_parameter(param_name)
            return param_info.allow_None if param_info else False

        return False

    def _check_parameter_constraints(
        self, node: ParsoNode, param_name: str, lines: list[str]
    ) -> None:
        """Check for parameter-specific constraints (parso version)."""
        # Find the parameter call on the right side of the assignment
        param_call = None
        for child in get_children(node):
            if child.type in ("power", "atom_expr"):
                param_call = child
                break

        if not param_call:
            return

        # Resolve the actual parameter class type for constraint checking
        param_class_info = resolve_parameter_class(param_call, self.imports)
        if not param_class_info:
            return

        resolved_cls = param_class_info["type"]

        # Get keyword arguments
        kwargs = get_keyword_arguments(param_call)

        # Check bounds for Number/Integer parameters
        if resolved_cls in ["Number", "Integer"]:
            bounds_node = kwargs.get("bounds")
            inclusive_bounds_node = kwargs.get("inclusive_bounds")
            default_value = kwargs.get("default")

            inclusive_bounds = (True, True)  # Default to inclusive

            # Parse inclusive_bounds if present
            if inclusive_bounds_node and inclusive_bounds_node.type == "atom":
                # Parse (True, False) pattern
                for child in get_children(inclusive_bounds_node):
                    if child.type == "testlist_comp":
                        elements = [
                            c for c in get_children(child) if c.type in ("name", "keyword")
                        ]
                        if len(elements) >= 2:
                            left_inclusive = extract_boolean_value(elements[0])
                            right_inclusive = extract_boolean_value(elements[1])
                            if left_inclusive is not None and right_inclusive is not None:
                                inclusive_bounds = (left_inclusive, right_inclusive)

            # Parse bounds if present
            if bounds_node and bounds_node.type == "atom":
                # Parse (min, max) pattern
                for child in get_children(bounds_node):
                    if child.type == "testlist_comp":
                        elements = [
                            c
                            for c in get_children(child)
                            if c.type in ("number", "name", "factor")
                        ]
                        if len(elements) >= 2:
                            try:
                                min_val = extract_numeric_value(elements[0])
                                max_val = extract_numeric_value(elements[1])

                                if (
                                    min_val is not None
                                    and max_val is not None
                                    and min_val >= max_val
                                ):
                                    message = f"Parameter '{param_name}' has invalid bounds: min ({min_val}) >= max ({max_val})"
                                    self._create_type_error(node, message, "invalid-bounds")

                                # Check if default value violates bounds
                                if (
                                    default_value is not None
                                    and min_val is not None
                                    and max_val is not None
                                ):
                                    default_numeric = extract_numeric_value(default_value)
                                    if default_numeric is not None:
                                        left_inclusive, right_inclusive = inclusive_bounds

                                        # Check bounds violation
                                        violates_lower = (
                                            (default_numeric < min_val)
                                            if left_inclusive
                                            else (default_numeric <= min_val)
                                        )
                                        violates_upper = (
                                            (default_numeric > max_val)
                                            if right_inclusive
                                            else (default_numeric >= max_val)
                                        )

                                        if violates_lower or violates_upper:
                                            bound_description = self._format_bounds_description(
                                                min_val, max_val, left_inclusive, right_inclusive
                                            )
                                            message = f"Default value {default_numeric} for parameter '{param_name}' is outside bounds {bound_description}"
                                            self._create_type_error(
                                                node, message, "default-bounds-violation"
                                            )

                            except (ValueError, TypeError):
                                pass

        # Check for empty lists/tuples with List/Tuple parameters
        elif resolved_cls in ["List", "Tuple"]:
            default_value = kwargs.get("default")
            if default_value and default_value.type == "atom":
                # Check if it's an empty list or tuple
                # Get all child values to check for empty containers
                child_values = [
                    get_value(child)
                    for child in get_children(default_value)
                    if hasattr(child, "value")
                ]
                is_empty_list = child_values == ["[", "]"]
                is_empty_tuple = child_values == ["(", ")"]

                if (is_empty_list or is_empty_tuple) and "bounds" in kwargs:
                    message = f"Parameter '{param_name}' has empty default but bounds specified"
                    self._create_type_error(node, message, "empty-default-with-bounds", "warning")

    def _check_deprecated_parameter_type(self, node: ParsoNode, param_type: str) -> None:
        """Check if a parameter type is deprecated and emit a warning."""
        if param_type in DEPRECATED_PARAMETER_TYPES:
            deprecation_info = DEPRECATED_PARAMETER_TYPES[param_type]
            message = f"{deprecation_info['message']} (since {deprecation_info['version']})"
            self._create_type_error(node, message, "deprecated-parameter", "warning")

    def _analyze_external_class_ast(self, full_class_path: str | None):
        """Analyze external class using AST through external class inspector."""
        if full_class_path is None:
            return None
        return self.external_inspector.analyze_external_class(full_class_path)

    def _get_parameter_item_type(self, class_name: str, param_name: str) -> type | None:
        """Get the item_type constraint for a List parameter."""
        # Check local classes first
        if class_name in self.param_classes:
            param_info = self.param_classes[class_name].get_parameter(param_name)
            return param_info.item_type if param_info else None

        # Check external classes
        class_info = self.external_param_classes.get(class_name)
        if class_info:
            param_info = class_info.get_parameter(param_name)
            return param_info.item_type if param_info else None

        return None

    def _get_parameter_length(self, class_name: str, param_name: str) -> int | None:
        """Get the length constraint for a Tuple parameter."""
        # Check local classes first
        if class_name in self.param_classes:
            param_info = self.param_classes[class_name].get_parameter(param_name)
            return param_info.length if param_info else None

        # Check external classes
        class_info = self.external_param_classes.get(class_name)
        if class_info:
            param_info = class_info.get_parameter(param_name)
            return param_info.length if param_info else None

        return None

    def _extract_list_items(self, node: ParsoNode) -> list[ParsoNode] | None:
        """Extract items from a list literal like [1, 2, 3]."""
        if not hasattr(node, "type") or node.type != "atom":
            return None

        children = get_children(node)
        if not children or get_value(children[0]) != "[":
            return None

        # Find testlist_comp inside the list
        items = []
        for child in children:
            if child.type == "testlist_comp":
                # Extract individual elements from testlist_comp
                items.extend(
                    item_child
                    for item_child in get_children(child)
                    if item_child.type not in ("operator",)
                )
                break

        return items

    def _extract_tuple_items(self, node: ParsoNode) -> list[ParsoNode] | None:
        """Extract items from a tuple literal like (1, 2, 3)."""
        if not hasattr(node, "type") or node.type != "atom":
            return None

        children = get_children(node)
        if not children or get_value(children[0]) != "(":
            return None

        # Find testlist_comp inside the tuple
        items = []
        for child in children:
            if child.type == "testlist_comp":
                # Extract individual elements from testlist_comp
                items.extend(
                    item_child
                    for item_child in get_children(child)
                    if item_child.type not in ("operator",)
                )
                break

        return items

    def _is_type_compatible(self, inferred_type: type, expected_type: type) -> bool:
        """Check if inferred type is compatible with expected type."""
        if inferred_type == expected_type:
            return True

        # Handle subclass relationships
        if isinstance(inferred_type, type) and isinstance(expected_type, type):
            try:
                return issubclass(inferred_type, expected_type)
            except TypeError:
                return False

        return False
