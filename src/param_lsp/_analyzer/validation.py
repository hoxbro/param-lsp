"""
Parameter validation for parameter assignments.
Handles type checking, bounds validation, constraint checking for both
class parameter defaults and runtime assignments.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

from param_lsp._treesitter import (
    find_all_parameter_assignments,
    get_children,
    get_class_name,
    get_value,
    is_function_call,
)
from param_lsp._treesitter.queries import (
    find_attribute_assignments,
    find_calls,
    find_classes,
    find_param_depends_decorators,
)
from param_lsp.constants import DEPRECATED_PARAMETER_TYPES, PARAM_TYPE_MAP

from .parameter_extractor import (
    extract_boolean_value,
    extract_numeric_value,
    get_keyword_arguments,
    is_none_value,
    resolve_parameter_class,
)

if TYPE_CHECKING:
    from tree_sitter import Node

    from param_lsp._analyzer.static_external_analyzer import ExternalClassInspector
    from param_lsp._types import (
        ExternalParamClassDict,
        ImportDict,
        ParamClassDict,
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

    def check_parameter_types(self, tree: Node, lines: list[str]) -> list[TypeErrorDict]:
        """Perform comprehensive parameter type validation on a parsed AST.

        Args:
            tree: The root tree-sitter AST node to validate
            lines: Source code lines for error reporting

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

        # Use optimized tree-sitter queries instead of walking entire tree
        # This is significantly faster, especially for large files

        # Check class parameter defaults
        for class_node, _captures in find_classes(tree):
            self._check_class_parameter_defaults(class_node, lines)

        # Check runtime parameter assignments like obj.param = value
        # Use optimized find_attribute_assignments query instead of finding all assignments
        for assignment_node, _captures in find_attribute_assignments(tree):
            self._check_runtime_parameter_assignment(assignment_node, lines)

        # Check constructor calls like MyClass(x="A")
        for call_node, _captures in find_calls(tree):
            if is_function_call(call_node):
                self._check_constructor_parameter_types(call_node, lines)

        # Check @param.depends decorators for invalid parameter references
        self._check_param_depends_decorators(tree)

        return self.type_errors.copy()

    def _check_class_parameter_defaults(self, class_node: Node, lines: list[str]) -> None:
        """Check parameter default types within a class definition."""
        class_name = get_class_name(class_node)
        if not class_name or class_name not in self.param_classes:
            return

        for assignment_node, target_name in find_all_parameter_assignments(
            class_node, self.is_parameter_assignment
        ):
            self._check_parameter_default_type(assignment_node, target_name, lines)

    def _check_constructor_parameter_types(self, node: Node, lines: list[str]) -> None:
        """Check for type errors in constructor parameter calls like MyClass(x="A") (tree-sitter version)."""
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

        # Get keyword arguments from the tree-sitter node
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
                    # For tree-sitter nodes, check if it's a keyword node with True/False
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

    def _infer_value_type(self, node: Node) -> type | None:
        """Infer Python type from tree-sitter node."""
        if node:
            if node.type in ("integer", "float"):
                # Check if it's a float or int
                if node.type == "float":
                    return float
                else:
                    return int
            elif node.type == "string":
                return str
            elif node.type == "identifier":
                value = get_value(node)
                if value in {"True", "False"}:
                    return bool
                elif value == "None":
                    return type(None)
                # Could be a variable - would need more sophisticated analysis
                return None
            elif node.type in ("true", "false"):
                return bool
            elif node.type == "none":
                return type(None)
            elif node.type == "list":
                return list
            elif node.type == "dictionary":
                return dict
            elif node.type == "tuple":
                return tuple
        return None

    def _is_boolean_literal(self, node: Node) -> bool:
        """Check if a tree-sitter node represents a boolean literal (True/False)."""
        return node.type in ("true", "false") or (
            node.type == "identifier" and get_value(node) in ("True", "False")
        )

    def _format_expected_types(self, expected_types: tuple) -> str:
        """Format expected types for error messages."""
        if len(expected_types) == 1:
            return expected_types[0].__name__
        else:
            type_names = [t.__name__ for t in expected_types]
            return " or ".join(type_names)

    def _create_type_error(
        self, node: Node | None, message: str, code: str, severity: str = "error"
    ) -> None:
        """Helper function to create and append a type error (tree-sitter version)."""
        # Get position information from tree-sitter node
        if node is not None:
            line = node.start_point[0]  # tree-sitter is 0-indexed
            col = node.start_point[1]
            end_line = node.end_point[0]
            end_col = node.end_point[1]
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

    def _check_constructor_bounds(
        self,
        node: Node,
        class_name: str,
        param_name: str,
        cls: str,
        param_value: Node,
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
        node: Node,
        class_name: str,
        param_name: str,
        cls: str,
        param_value: Node,
    ) -> None:
        """Check container constraints for List item_type and Tuple length."""
        if cls == "List":
            self._check_list_item_type_constructor(node, class_name, param_name, param_value)
        elif cls == "Tuple":
            self._check_tuple_length_constructor(node, class_name, param_name, param_value)

    def _check_list_item_type_constructor(
        self,
        node: Node,
        class_name: str,
        param_name: str,
        param_value: Node,
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
        node: Node,
        class_name: str,
        param_name: str,
        param_value: Node,
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

    def _check_parameter_default_type(self, node: Node, param_name: str, lines: list[str]) -> None:
        """Check if parameter default value matches declared type (tree-sitter version)."""
        # Find the parameter call on the right side of the assignment
        param_call = None
        if node.type == "assignment":
            right_node = node.child_by_field_name("right")
            if right_node and right_node.type == "call":
                param_call = right_node
        else:
            # Fallback: scan children for call node
            for child in get_children(node):
                if child.type == "call":
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

    def _check_runtime_parameter_assignment(self, node: Node, lines: list[str]) -> None:
        """Check runtime parameter assignments like obj.param = value."""
        # Extract target and assigned value from attribute assignment
        # Since we use find_attribute_assignments, we know node is an attribute assignment
        left_node = node.child_by_field_name("left")
        right_node = node.child_by_field_name("right")

        if not left_node or not right_node or left_node.type != "attribute":
            return

        target = left_node
        assigned_value = right_node

        # Extract parameter name from the attribute access
        # In tree-sitter, attribute has 'attribute' field
        param_name = None
        if target.type == "attribute":
            attr_node = target.child_by_field_name("attribute")
            if attr_node:
                param_name = get_value(attr_node)

        if not param_name:
            return

        # Determine the instance class
        instance_class = None

        # Check if this is a direct instantiation (has call before the dot)
        # In tree-sitter, attribute nodes have 'object' and 'attribute' fields
        # For S().value, object is the call node S()
        has_call = False
        call_node = None

        if target.type == "attribute":
            obj_node = target.child_by_field_name("object")
            if obj_node and obj_node.type == "call":
                has_call = True
                call_node = obj_node
        if has_call:
            # Case: MyClass().param = value (direct instantiation)
            if call_node:
                # Extract class name from the call node
                instance_class = self._get_instance_class(call_node)
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
        self._check_runtime_bounds(node, instance_class, param_name, cls, assigned_value)

    def _check_runtime_bounds(
        self,
        node: Node,
        instance_class: str,
        param_name: str,
        cls: str,
        assigned_value: Node,
    ) -> None:
        """Check if assigned value is within parameter bounds."""
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
        """Get the class name from an instance creation call."""
        # For tree-sitter call nodes like TestClass(...) or pn.widgets.IntSlider(...)
        if call_node.type == "call":
            # Get the function/class being called (first child, before argument_list)
            children = get_children(call_node)
            if not children:
                return None

            function_node = children[0]

            # Simple case: TestClass(...)
            if function_node.type == "identifier":
                return get_value(function_node)

            # Attribute case: module.Class(...) or pn.widgets.IntSlider(...)
            elif function_node.type == "attribute":
                # Try to resolve the full path for external classes
                full_class_path = self._resolve_full_class_path_from_attribute(function_node)
                # Check if this is an external Parameterized class
                class_info = self._analyze_external_class_ast(full_class_path)
                if class_info:
                    # Return the full path as the class identifier for external classes
                    return full_class_path

                # Otherwise return just the final attribute name
                attr_node = function_node.child_by_field_name("attribute")
                if attr_node:
                    return get_value(attr_node)
        return None

    def _resolve_full_class_path_from_attribute(self, attribute_node: Node) -> str | None:
        """Resolve the full class path from a tree-sitter attribute node like pn.widgets.IntSlider.

        For an attribute node representing pn.widgets.IntSlider:
        - object field: pn.widgets (could be nested attribute)
        - attribute field: IntSlider
        """
        parts = []

        # Recursively collect all parts from nested attributes
        def collect_parts(node: Node) -> None:
            if node.type == "identifier":
                parts.append(get_value(node))
            elif node.type == "attribute":
                # First get the object part (left side)
                obj_node = node.child_by_field_name("object")
                if obj_node:
                    collect_parts(obj_node)
                # Then get the attribute part (right side)
                attr_node = node.child_by_field_name("attribute")
                if attr_node:
                    parts.append(get_value(attr_node))

        collect_parts(attribute_node)

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

    def _resolve_full_class_path(self, base) -> str | None:
        """Resolve the full class path from a tree-sitter power/atom_expr node like pn.widgets.IntSlider."""
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

    def _check_parameter_constraints(self, node: Node, param_name: str, lines: list[str]) -> None:
        """Check for parameter-specific constraints."""
        # Find the parameter call on the right side of the assignment
        param_call = None
        # For tree-sitter, check if this is an assignment node
        if node.type == "assignment":
            right_node = node.child_by_field_name("right")
            if right_node and right_node.type == "call":
                param_call = right_node
        else:
            # Fallback: scan children for call node
            for child in get_children(node):
                if child.type == "call":
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
            if inclusive_bounds_node and inclusive_bounds_node.type == "tuple":
                # Parse (True, False) pattern
                # In tree-sitter, tuple children are directly the elements
                elements = [
                    c
                    for c in get_children(inclusive_bounds_node)
                    if c.type in ("identifier", "true", "false")
                ]
                if len(elements) >= 2:
                    left_inclusive = extract_boolean_value(elements[0])
                    right_inclusive = extract_boolean_value(elements[1])
                    if left_inclusive is not None and right_inclusive is not None:
                        inclusive_bounds = (left_inclusive, right_inclusive)

            # Parse bounds if present
            if bounds_node and bounds_node.type == "tuple":
                # Parse (min, max) pattern
                # In tree-sitter, tuple children are directly the numeric elements
                elements = [
                    c
                    for c in get_children(bounds_node)
                    if c.type in ("integer", "float", "unary_operator", "identifier")
                ]
                if len(elements) >= 2:
                    try:
                        min_val = extract_numeric_value(elements[0])
                        max_val = extract_numeric_value(elements[1])

                        if min_val is not None and max_val is not None and min_val >= max_val:
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
            if default_value and default_value.type in ("list", "tuple"):
                # Check if it's an empty list or tuple
                # In tree-sitter, empty containers have only parentheses/brackets as children
                child_values = [
                    get_value(child)
                    for child in get_children(default_value)
                    if get_value(child) not in (",",)  # Ignore commas
                ]
                is_empty_list = child_values == ["[", "]"]
                is_empty_tuple = child_values == ["(", ")"]

                if (is_empty_list or is_empty_tuple) and "bounds" in kwargs:
                    message = f"Parameter '{param_name}' has empty default but bounds specified"
                    self._create_type_error(node, message, "empty-default-with-bounds", "warning")

    def _check_deprecated_parameter_type(self, node: Node, param_type: str) -> None:
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

    def _extract_list_items(self, node: Node) -> list[Node] | None:
        """Extract items from a list literal like [1, 2, 3]."""
        if not hasattr(node, "type") or node.type != "list":
            return None

        # In tree-sitter, list children are directly the items plus brackets and commas
        # Filter out punctuation to get just the items
        items = [child for child in get_children(node) if child.type not in ("[", "]", ",")]

        return items if items else None

    def _extract_tuple_items(self, node: Node) -> list[Node] | None:
        """Extract items from a tuple literal like (1, 2, 3)."""
        if not hasattr(node, "type") or node.type != "tuple":
            return None

        # In tree-sitter, tuple children are directly the items plus parentheses and commas
        # Filter out punctuation to get just the items
        items = [child for child in get_children(node) if child.type not in ("(", ")", ",")]

        return items if items else None

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

    def _check_param_depends_decorators(self, tree: Node) -> None:
        """Check @param.depends decorators for invalid parameter references.

        This method validates that all parameter names referenced in @param.depends
        decorators actually exist as parameters in the containing class.

        Args:
            tree: The root tree-sitter AST node to validate
        """
        # Find all param.depends decorators in the tree
        decorators = find_param_depends_decorators(tree)

        for decorator_node, _captures in decorators:
            # Find the containing class for this decorator
            containing_class = self._find_containing_class_for_decorator(decorator_node)
            if not containing_class:
                continue

            # Get all valid parameter names for this class
            valid_params = self._get_class_parameters(containing_class)
            if not valid_params:
                continue

            # Extract parameter names from the decorator arguments
            depends_params = self._extract_depends_parameters(decorator_node)

            # Check each parameter name
            for param_name, param_node in depends_params:
                if param_name not in valid_params:
                    message = (
                        f"Parameter '{param_name}' does not exist in class '{containing_class}'"
                    )
                    self._create_type_error(
                        param_node, message, "invalid-depends-parameter", "error"
                    )

    def _find_containing_class_for_decorator(self, decorator_node: Node) -> str | None:
        """Find the class containing a decorator.

        Args:
            decorator_node: A tree-sitter decorator node

        Returns:
            The name of the containing class, or None if not found
        """
        # Walk up the tree to find the class definition
        current = decorator_node.parent
        while current:
            if current.type == "class_definition":
                class_name = get_class_name(current)
                # Only return if this is a Parameterized class we know about
                if class_name and (
                    class_name in self.param_classes or class_name in self.external_param_classes
                ):
                    return class_name
            current = current.parent
        return None

    def _get_class_parameters(self, class_name: str) -> set[str]:
        """Get all valid parameter names for a class (including inherited).

        Args:
            class_name: The name of the class

        Returns:
            Set of parameter names
        """
        params = set()

        # Check local classes
        if class_name in self.param_classes:
            class_info = self.param_classes[class_name]
            params.update(class_info.get_parameter_names())

        # Check external classes
        elif class_name in self.external_param_classes:
            class_info = self.external_param_classes[class_name]
            if class_info:
                params.update(class_info.get_parameter_names())

        return params

    def _extract_depends_parameters(self, decorator_node: Node) -> list[tuple[str, Node]]:
        """Extract parameter names from a @param.depends decorator.

        Args:
            decorator_node: A tree-sitter decorator node

        Returns:
            List of (parameter_name, node) tuples where node is the string node
        """
        params = []

        # Find the call node within the decorator
        call_node = None
        for child in get_children(decorator_node):
            if child.type == "call":
                call_node = child
                break

        if not call_node:
            return params

        # Get the argument list
        args_node = call_node.child_by_field_name("arguments")
        if not args_node:
            return params

        # Extract string arguments
        for arg in get_children(args_node):
            if arg.type == "string":
                # Extract the parameter name from the string (remove quotes)
                param_text = get_value(arg)
                if param_text:
                    # Remove surrounding quotes
                    param_name = param_text.strip('"').strip("'")
                    params.append((param_name, arg))

        return params
