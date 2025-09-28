"""
Parameter extraction and parsing utilities.
Handles extracting parameter information from parso AST nodes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from param_lsp.constants import PARAM_TYPES

from .parso_utils import (
    find_arguments_in_trailer,
    find_function_call_trailers,
    get_children,
    get_value,
)

if TYPE_CHECKING:
    from parso.tree import NodeOrLeaf

    from param_lsp.models import ParameterInfo

# Type aliases for better type safety
NumericValue = int | float | None  # Numeric values from nodes
BoolValue = bool | None  # Boolean values from nodes


def is_parameter_assignment(node: NodeOrLeaf) -> bool:
    """Check if a parso assignment statement looks like a parameter definition."""
    # Find the right-hand side of the assignment (after '=')
    found_equals = False
    for child in get_children(node):
        if child.type == "operator" and get_value(child) == "=":
            found_equals = True
        elif found_equals and child.type in ("power", "atom_expr"):
            # Check if it's a parameter type call
            return is_parameter_call(child)
    return False


def is_parameter_call(node: NodeOrLeaf) -> bool:
    """Check if a parso power/atom_expr node represents a parameter type call."""
    # Extract the function name and check if it's a param type
    func_name = None

    # Look through children to find the actual function being called
    for child in get_children(node):
        if child.type == "name":
            # This could be a direct function call (e.g., "String") or module name
            func_name = get_value(child)
        elif child.type == "trailer":
            # Handle dotted calls like param.Integer
            for trailer_child in get_children(child):
                if trailer_child.type == "name":
                    func_name = get_value(trailer_child)
                    break
            # If we found a function name in a trailer, that's the final function name
            if func_name:
                break

    # Would need imports context to check imported param types
    # This will be handled by the main analyzer
    return func_name is not None and func_name in PARAM_TYPES


def extract_parameters(
    node, find_assignments_func, extract_info_func, is_parameter_assignment_func
) -> list[ParameterInfo]:
    """Extract parameter definitions from a Param class (parso node)."""
    parameters = []

    for assignment_node, target_name in find_assignments_func(node, is_parameter_assignment_func):
        param_info = extract_info_func(assignment_node, target_name)
        if param_info:
            parameters.append(param_info)

    return parameters


def get_keyword_arguments(call_node: NodeOrLeaf) -> dict[str, NodeOrLeaf]:
    """Extract keyword arguments from a parso function call node."""

    kwargs = {}

    for trailer_node in find_function_call_trailers(call_node):
        for arg_node in find_arguments_in_trailer(trailer_node):
            extract_single_argument(arg_node, kwargs)

    return kwargs


def extract_single_argument(arg_node: NodeOrLeaf, kwargs: dict[str, NodeOrLeaf]) -> None:
    """Extract a single keyword argument from a parso argument node."""
    if len(get_children(arg_node)) >= 3:
        name_node = get_children(arg_node)[0]
        equals_node = get_children(arg_node)[1]
        value_node = get_children(arg_node)[2]

        if (
            name_node.type == "name"
            and equals_node.type == "operator"
            and get_value(equals_node) == "="
        ):
            name_value = get_value(name_node)
            if name_value:
                kwargs[name_value] = value_node


def extract_bounds_from_call(call_node: NodeOrLeaf) -> tuple | None:
    """Extract bounds from a parameter call (parso version)."""
    bounds_info = None
    inclusive_bounds = (True, True)  # Default to inclusive

    kwargs = get_keyword_arguments(call_node)

    if "bounds" in kwargs:
        bounds_node = kwargs["bounds"]
        # Check if it's a tuple/parentheses with 2 elements
        if bounds_node.type == "atom" and get_children(bounds_node):
            # Look for (min, max) pattern
            for child in get_children(bounds_node):
                if child.type == "testlist_comp":
                    elements = [
                        c
                        for c in get_children(child)
                        if c.type in ("number", "name", "factor", "keyword")
                    ]
                    if len(elements) >= 2:
                        min_val = extract_numeric_value(elements[0])
                        max_val = extract_numeric_value(elements[1])
                        # Accept bounds even if one side is None (unbounded)
                        if min_val is not None or max_val is not None:
                            bounds_info = (min_val, max_val)

    if "inclusive_bounds" in kwargs:
        inclusive_bounds_node = kwargs["inclusive_bounds"]
        # Similar logic for inclusive bounds tuple
        if inclusive_bounds_node.type == "atom" and get_children(inclusive_bounds_node):
            for child in get_children(inclusive_bounds_node):
                if child.type == "testlist_comp":
                    elements = [c for c in get_children(child) if c.type in ("name", "keyword")]
                    if len(elements) >= 2:
                        left_inclusive = extract_boolean_value(elements[0])
                        right_inclusive = extract_boolean_value(elements[1])
                        if left_inclusive is not None and right_inclusive is not None:
                            inclusive_bounds = (left_inclusive, right_inclusive)

    if bounds_info:
        # Return (min, max, left_inclusive, right_inclusive)
        return (*bounds_info, *inclusive_bounds)
    return None


def extract_doc_from_call(call_node: NodeOrLeaf) -> str | None:
    """Extract doc string from a parameter call (parso version)."""
    kwargs = get_keyword_arguments(call_node)
    if "doc" in kwargs:
        return extract_string_value(kwargs["doc"])
    return None


def extract_allow_None_from_call(call_node: NodeOrLeaf) -> BoolValue:
    """Extract allow_None from a parameter call (parso version)."""
    kwargs = get_keyword_arguments(call_node)
    if "allow_None" in kwargs:
        return extract_boolean_value(kwargs["allow_None"])
    return None


def extract_default_from_call(call_node: NodeOrLeaf) -> NodeOrLeaf | None:
    """Extract default value from a parameter call (parso version)."""
    kwargs = get_keyword_arguments(call_node)
    if "default" in kwargs:
        return kwargs["default"]
    return None


def is_none_value(node: NodeOrLeaf) -> bool:
    """Check if a parso node represents None."""
    return (
        hasattr(node, "type")
        and node.type in ("name", "keyword")  # None can be either name or keyword type
        and hasattr(node, "value")
        and get_value(node) == "None"
    )


def extract_string_value(node: NodeOrLeaf) -> str | None:
    """Extract string value from parso node."""
    if hasattr(node, "type") and node.type == "string":
        # Remove quotes from string value
        value = get_value(node)
        if value is None:
            return None
        # Handle triple quotes first
        if (value.startswith('"""') and value.endswith('"""')) or (
            value.startswith("'''") and value.endswith("'''")
        ):
            return value[3:-3]
        # Handle single/double quotes
        elif (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            return value[1:-1]
        return value
    return None


def extract_boolean_value(node: NodeOrLeaf) -> BoolValue:
    """Extract boolean value from parso node."""
    if hasattr(node, "type") and node.type in ("name", "keyword"):
        if get_value(node) == "True":
            return True
        elif get_value(node) == "False":
            return False
    return None


def format_default_value(node: NodeOrLeaf) -> str:
    """Format a parso node as a string representation for display."""
    # For parso nodes, use the get_code() method to get the original source
    if hasattr(node, "get_code"):
        code = node.get_code()
        return code.strip() if code is not None else "<complex>"
    elif hasattr(node, "value"):
        value = get_value(node)
        return str(value) if value is not None else "<unknown>"
    else:
        return "<complex>"


def extract_numeric_value(node: NodeOrLeaf) -> NumericValue:
    """Extract numeric value from parso node."""
    if hasattr(node, "type") and node.type == "number":
        try:
            value = get_value(node)
            if value is None:
                return None
            # Try to parse as int first, then float
            # Scientific notation (e.g., 1e3) should be parsed as float
            if "." in value or "e" in value.lower():
                return float(value)
            else:
                return int(value)
        except ValueError:
            return None
    elif hasattr(node, "type") and node.type in ("name", "keyword") and get_value(node) == "None":
        return None  # Explicitly handle None
    elif (
        hasattr(node, "type")
        and node.type == "factor"
        and hasattr(node, "children")
        and len(get_children(node)) >= 2
    ):
        # Handle unary operators like negative numbers: factor -> operator(-) + number
        operator_node = get_children(node)[0]
        operand_node = get_children(node)[1]
        if (
            hasattr(operator_node, "value")
            and get_value(operator_node) == "-"
            and hasattr(operand_node, "type")
            and operand_node.type == "number"
        ):
            try:
                operand_value = get_value(operand_node)
                if operand_value is None:
                    return None
                if "." in operand_value:
                    return -float(operand_value)
                else:
                    return -int(operand_value)
            except ValueError:
                return None
    return None
