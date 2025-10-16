"""
Parameter extraction and parsing utilities.
Handles extracting parameter information from tree-sitter AST nodes.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from param_lsp.constants import PARAM_TYPES

logger = logging.getLogger(__name__)

from param_lsp._treesitter import (
    find_arguments_in_trailer,
    find_function_call_trailers,
    get_children,
    get_value,
)

from .ast_navigator import SourceAnalyzer

if TYPE_CHECKING:
    from tree_sitter import Node

    from param_lsp.models import ParameterInfo
else:
    from param_lsp.models import ParameterInfo

# Type aliases for better type safety
NumericValue = int | float | None  # Numeric values from nodes
BoolValue = bool | None  # Boolean values from nodes


def is_parameter_assignment(node: Node) -> bool:
    """Check if a tree-sitter assignment statement represents a parameter definition.

    Args:
        node: A tree-sitter node representing an assignment statement

    Returns:
        True if the assignment looks like a parameter definition (e.g., x = param.String()),
        False otherwise
    """
    # Find the right-hand side of the assignment (after '=')
    # In tree-sitter: assignment node has 'left', 'right' fields
    if node.type == "assignment":
        right_node = node.child_by_field_name("right")
        if right_node and right_node.type == "call":
            return is_parameter_call(right_node)

    # Fallback: scan children for '=' and check right side
    found_equals = False
    for child in get_children(node):
        if child.text == b"=" or get_value(child) == "=":
            found_equals = True
        elif found_equals and child.type == "call":
            # Check if it's a parameter type call
            return is_parameter_call(child)
    return False


def is_parameter_call(node: Node) -> bool:
    """Check if a tree-sitter call node represents a parameter type call.

    Args:
        node: A tree-sitter node of type 'call'

    Returns:
        True if the node represents a call to a known parameter type (e.g., param.String()),
        False otherwise

    Note:
        This function checks that the call is specifically to param.ParameterType or just
        ParameterType (direct import). It rejects calls like pd.DataFrame() even though
        DataFrame is in PARAM_TYPES, because it's not from the param module.
    """
    if node.type != "call":
        return False

    # Get the function being called (the 'function' field)
    func_node = node.child_by_field_name("function")
    if not func_node:
        return False

    parts = []

    # Extract call chain parts
    if func_node.type == "identifier":
        # Simple call: String()
        parts.append(get_value(func_node))
    elif func_node.type == "attribute":
        # Dotted call: param.String() or module.Class()
        # attribute has 'object' and 'attribute' fields
        obj_node = func_node.child_by_field_name("object")
        attr_node = func_node.child_by_field_name("attribute")
        if obj_node and attr_node and obj_node.type == "identifier":
            parts.append(get_value(obj_node))
            parts.append(get_value(attr_node))

    if not parts:
        return False

    # Check if this is a parameter type call
    # Accept: param.String, String (if just the type name)
    # Reject: pd.DataFrame, other.String

    if len(parts) == 1:
        # Direct call like "String()" - accept if it's a param type
        return parts[0] in PARAM_TYPES
    elif len(parts) == 2:
        # Dotted call like "param.String()" or "pd.DataFrame()"
        # Only accept if the module part is "param"
        module, func_name = parts
        return module == "param" and func_name in PARAM_TYPES
    else:
        # More complex chains - not a simple parameter type
        return False


def extract_parameters(
    node, find_assignments_func, extract_info_func, is_parameter_assignment_func
) -> list[ParameterInfo]:
    """Extract parameter definitions from a Parameterized class node.

    Args:
        node: A tree-sitter node representing a class definition
        find_assignments_func: Function to find parameter assignments in the class
        extract_info_func: Function to extract parameter info from assignments
        is_parameter_assignment_func: Function to check if an assignment is a parameter

    Returns:
        List of ParameterInfo objects representing the parameters in the class

    Example:
        This function is typically used as part of the main analyzer workflow
        to extract all parameter definitions from a Parameterized class.
    """
    parameters = []

    for assignment_node, target_name in find_assignments_func(node, is_parameter_assignment_func):
        param_info = extract_info_func(assignment_node, target_name)
        if param_info:
            parameters.append(param_info)

    return parameters


def get_keyword_arguments(call_node: Node) -> dict[str, Node]:
    """Extract keyword arguments from a tree-sitter function call node."""

    kwargs = {}

    for trailer_node in find_function_call_trailers(call_node):
        for arg_node in find_arguments_in_trailer(trailer_node):
            extract_single_argument(arg_node, kwargs)

    return kwargs


def extract_single_argument(arg_node: Node, kwargs: dict[str, Node]) -> None:
    """Extract a single keyword argument from a tree-sitter argument node."""
    # In tree-sitter: keyword_argument has 'name' and 'value' fields
    if arg_node.type == "keyword_argument":
        name_node = arg_node.child_by_field_name("name")
        value_node = arg_node.child_by_field_name("value")
        if name_node and value_node:
            name_value = get_value(name_node)
            if name_value:
                kwargs[name_value] = value_node
        return

    # Fallback: parse children manually
    if len(get_children(arg_node)) >= 3:
        name_node = get_children(arg_node)[0]
        equals_node = get_children(arg_node)[1]
        value_node = get_children(arg_node)[2]

        if name_node.type == "identifier" and (
            equals_node.text == b"=" or get_value(equals_node) == "="
        ):
            name_value = get_value(name_node)
            if name_value:
                kwargs[name_value] = value_node


def extract_bounds_from_call(call_node: Node) -> tuple | None:
    """Extract bounds from a parameter call (tree-sitter version)."""
    bounds_info = None
    inclusive_bounds = (True, True)  # Default to inclusive

    kwargs = get_keyword_arguments(call_node)

    if "bounds" in kwargs:
        bounds_node = kwargs["bounds"]
        # Check if it's a tuple with 2 elements
        if bounds_node.type in ("tuple", "list"):
            # Extract elements from tuple/list
            elements = [
                c
                for c in get_children(bounds_node)
                if c.type
                in ("integer", "float", "identifier", "unary_operator", "true", "false", "none")
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
        if inclusive_bounds_node.type in ("tuple", "list"):
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

    if bounds_info:
        # Return (min, max, left_inclusive, right_inclusive)
        return (*bounds_info, *inclusive_bounds)
    return None


def extract_doc_from_call(call_node: Node) -> str | None:
    """Extract doc string from a parameter call (tree-sitter version)."""
    kwargs = get_keyword_arguments(call_node)
    if "doc" in kwargs:
        return extract_string_value(kwargs["doc"])
    return None


def extract_allow_None_from_call(call_node: Node) -> BoolValue:
    """Extract allow_None from a parameter call (tree-sitter version)."""
    kwargs = get_keyword_arguments(call_node)
    if "allow_None" in kwargs:
        return extract_boolean_value(kwargs["allow_None"])
    return None


def extract_default_from_call(call_node: Node) -> Node | None:
    """Extract default value from a parameter call (tree-sitter version)."""
    kwargs = get_keyword_arguments(call_node)
    if "default" in kwargs:
        return kwargs["default"]
    return None


def extract_objects_from_call(call_node: Node) -> list[Any] | None:
    """Extract objects list from Selector parameter call."""
    kwargs = get_keyword_arguments(call_node)
    if "objects" in kwargs:
        # Extract list values from the objects argument
        return _extract_list_values(kwargs["objects"])
    return None


def extract_item_type_from_call(call_node: Node) -> type | None:
    """Extract item_type from List parameter call."""
    kwargs = get_keyword_arguments(call_node)
    if "item_type" in kwargs:
        # Extract the type from the item_type argument
        return _extract_type_value(kwargs["item_type"])
    return None


def extract_length_from_call(call_node: Node) -> int | None:
    """Extract length from Tuple parameter call."""
    kwargs = get_keyword_arguments(call_node)
    if "length" in kwargs:
        # Extract the numeric value from the length argument
        numeric_value = extract_numeric_value(kwargs["length"])
        # Convert to int if it's a float with no decimal part
        if isinstance(numeric_value, float) and numeric_value.is_integer():
            return int(numeric_value)
        elif isinstance(numeric_value, int):
            return numeric_value
    return None


def _extract_type_value(type_node: Node) -> type | None:
    """Extract a type from a tree-sitter node (e.g., str, int, float)."""
    if not type_node:
        return None

    if type_node.type == "identifier":
        type_name = get_value(type_node)
        if type_name is not None:
            # Map common type names to Python types
            type_mapping = {
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "list": list,
                "dict": dict,
                "tuple": tuple,
            }
            return type_mapping.get(type_name)

    return None


def _extract_list_values(list_node: Node) -> list[Any] | None:
    """Extract values from a list node, preserving their original types."""
    if not list_node:
        return None

    if list_node.type == "list":
        # tree-sitter list node contains items directly
        items = []
        for child in get_children(list_node):
            if child.type == "string":
                # Extract string value
                value = extract_string_value(child)
                if value is not None:
                    items.append(value)
            elif child.type in ("integer", "float"):
                # Extract numeric value
                numeric_value = extract_numeric_value(child)
                if numeric_value is not None:
                    items.append(numeric_value)
        return items if items else None

    return None


def is_none_value(node: Node) -> bool:
    """Check if a tree-sitter node represents None."""
    return node is not None and node.type == "none"


def extract_string_value(node: Node) -> str | None:
    """Extract string value from tree-sitter node."""
    if node and node.type == "string":
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


def extract_boolean_value(node: Node) -> BoolValue:
    """Extract boolean value from tree-sitter node."""
    if node:
        if node.type == "true":
            return True
        elif node.type == "false":
            return False
        # Fallback for identifier nodes with True/False values
        elif node.type == "identifier":
            value = get_value(node)
            if value == "True":
                return True
            elif value == "False":
                return False
    return None


def format_default_value(node: Node) -> str:
    """Format a tree-sitter node as a string representation for display."""
    # For tree-sitter nodes, use the text property to get the original source
    if node:
        value = get_value(node)
        return value.strip() if value is not None else "<complex>"
    else:
        return "<complex>"


def extract_numeric_value(node: Node) -> NumericValue:
    """Extract numeric value from tree-sitter node."""
    if not node:
        return None

    if node.type == "integer":
        try:
            value = get_value(node)
            return int(value) if value else None
        except ValueError:
            return None
    elif node.type == "float":
        try:
            value = get_value(node)
            return float(value) if value else None
        except ValueError:
            return None
    elif node.type == "none":
        return None  # Explicitly handle None
    elif node.type == "unary_operator":
        # Handle unary operators like negative numbers: unary_operator with operand
        children = get_children(node)
        if len(children) >= 2:
            operator_node = children[0]
            operand_node = children[1]
            if get_value(operator_node) == "-":
                operand_value = extract_numeric_value(operand_node)
                if operand_value is not None:
                    return -operand_value
    # Fallback for identifier "None"
    elif node.type == "identifier" and get_value(node) == "None":
        return None
    return None


def resolve_parameter_class(param_call: Node, imports: dict[str, str]) -> dict[str, str] | None:
    """Resolve parameter class from a tree-sitter call node like param.Integer()."""
    if param_call.type != "call":
        return None

    # Get the function being called
    func_node = param_call.child_by_field_name("function")
    if not func_node:
        return None

    func_name = None
    module_name = None

    if func_node.type == "identifier":
        # Simple call: Integer()
        func_name = get_value(func_node)
    elif func_node.type == "attribute":
        # Dotted call: param.Integer()
        obj_node = func_node.child_by_field_name("object")
        attr_node = func_node.child_by_field_name("attribute")
        if obj_node and attr_node and obj_node.type == "identifier":
            module_name = get_value(obj_node)
            func_name = get_value(attr_node)

    if func_name:
        # Check if it's a direct param type
        if func_name in PARAM_TYPES:
            return {"type": func_name, "module": module_name or "param"}

        # Check if it's an imported param type
        if func_name in imports:
            imported_full_name = imports[func_name]
            if imported_full_name.startswith("param."):
                param_type = imported_full_name.split(".")[-1]
                if param_type in PARAM_TYPES:
                    return {"type": param_type, "module": "param"}

    return None


def extract_parameter_info_from_assignment(
    assignment_node: Node,
    param_name: str,
    imports: dict[str, str],
    current_file_content: str | None = None,
) -> ParameterInfo | None:
    """Extract parameter info from a tree-sitter assignment statement."""
    if assignment_node is None or param_name is None:
        logger.debug("Invalid input: assignment_node or param_name is None")
        return None

    # Initialize parameter info
    cls = ""
    bounds = None
    doc = None
    allow_None = False
    default = None
    location = None
    objects = None

    # Get the parameter call (right-hand side of assignment)
    param_call = None
    if assignment_node.type == "assignment":
        right_node = assignment_node.child_by_field_name("right")
        if right_node and right_node.type == "call":
            param_call = right_node

    # Fallback: scan children manually
    if not param_call:
        found_equals = False
        for child in get_children(assignment_node):
            if child.text == b"=" or get_value(child) == "=":
                found_equals = True
            elif found_equals and child.type == "call":
                param_call = child
                break

    if param_call:
        # Get parameter type from the function call
        param_class_info = resolve_parameter_class(param_call, imports)
        if param_class_info:
            cls = param_class_info["type"]

        # Extract parameter arguments (bounds, doc, default, objects, etc.) from the whole param_call
        bounds = extract_bounds_from_call(param_call)
        doc = extract_doc_from_call(param_call)
        allow_None_value = extract_allow_None_from_call(param_call)
        default_value = extract_default_from_call(param_call)
        objects = extract_objects_from_call(param_call)

        # Store default value as a string representation
        if default_value is not None:
            default = format_default_value(default_value)

        # Param automatically sets allow_None=True when default=None
        if default_value is not None and is_none_value(default_value):
            allow_None = True
        elif allow_None_value is not None:
            allow_None = allow_None_value

    # Extract location information from the assignment node
    if assignment_node:
        try:
            # Get line number from the tree-sitter node (0-indexed in tree-sitter)
            line_number = assignment_node.start_point[0] + 1  # Convert to 1-indexed
            # Get the multiline source definition from the current file content
            if current_file_content:
                lines = current_file_content.split("\n")
                if 0 <= line_number - 1 < len(lines):
                    # Use multiline extraction to get complete parameter definition
                    source_definition = SourceAnalyzer.extract_multiline_definition(
                        lines, line_number - 1
                    )
                    # Preserve the original indentation of the first line
                    if source_definition and line_number - 1 < len(lines):
                        original_first_line = lines[line_number - 1]
                        # If original line has indentation that was stripped, restore it
                        if original_first_line.lstrip() == source_definition.split("\n")[0]:
                            # Replace first line with the original indented version
                            source_lines = source_definition.split("\n")
                            source_lines[0] = original_first_line
                            source_definition = "\n".join(source_lines)

                    location = {"line": line_number, "source": source_definition}
        except (AttributeError, IndexError):
            # If we can't get location info, continue without it
            pass

    # Extract container constraints
    item_type = None
    length = None
    if cls == "List" and param_call is not None:
        item_type = extract_item_type_from_call(param_call)
    elif cls == "Tuple" and param_call is not None:
        length = extract_length_from_call(param_call)

    # Create ParameterInfo object
    return ParameterInfo(
        name=param_name,
        cls=cls or "Unknown",
        bounds=bounds,
        doc=doc,
        allow_None=allow_None,
        default=default,
        location=location,
        objects=objects,
        item_type=item_type,
        length=length,
    )
