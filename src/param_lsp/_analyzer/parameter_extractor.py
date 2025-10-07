"""
Parameter extraction and parsing utilities.
Handles extracting parameter information from parso AST nodes.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from param_lsp.constants import PARAM_TYPES

logger = logging.getLogger(__name__)

from .ast_navigator import SourceAnalyzer
from .parso_utils import (
    find_arguments_in_trailer,
    find_function_call_trailers,
    get_children,
    get_value,
)

if TYPE_CHECKING:
    from parso.tree import NodeOrLeaf

    from param_lsp.models import ParameterInfo
else:
    from param_lsp.models import ParameterInfo

# Type aliases for better type safety
NumericValue = int | float | None  # Numeric values from nodes
BoolValue = bool | None  # Boolean values from nodes


def is_parameter_assignment(node: NodeOrLeaf) -> bool:
    """Check if a parso assignment statement represents a parameter definition.

    Args:
        node: A parso node representing an assignment statement

    Returns:
        True if the assignment looks like a parameter definition (e.g., x = param.String()),
        False otherwise

    Example:
        >>> import parso
        >>> tree = parso.parse("name = param.String(default='test')")
        >>> stmt = tree.children[0]
        >>> is_parameter_assignment(stmt)
        True
        >>> tree2 = parso.parse("x = 42")
        >>> stmt2 = tree2.children[0]
        >>> is_parameter_assignment(stmt2)
        False
    """
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
    """Check if a parso power/atom_expr node represents a parameter type call.

    Args:
        node: A parso node of type 'power' or 'atom_expr'

    Returns:
        True if the node represents a call to a known parameter type (e.g., param.String()),
        False otherwise

    Note:
        This function checks that the call is specifically to param.ParameterType or just
        ParameterType (direct import). It rejects calls like pd.DataFrame() even though
        DataFrame is in PARAM_TYPES, because it's not from the param module.

    Example:
        >>> import parso
        >>> tree = parso.parse("param.String()")
        >>> call_node = tree.children[0].children[0]
        >>> is_parameter_call(call_node)
        True
        >>> tree2 = parso.parse("pd.DataFrame()")
        >>> call_node2 = tree2.children[0].children[0]
        >>> is_parameter_call(call_node2)
        False
    """
    # Extract the full call chain to check if it's param.ParameterType
    parts = []

    # Walk through the node to extract all name parts
    for child in get_children(node):
        if child.type == "name":
            parts.append(get_value(child))
        elif child.type == "trailer":
            parts.extend(
                get_value(trailer_child)
                for trailer_child in get_children(child)
                if trailer_child.type == "name"
            )

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
        node: A parso node representing a class definition
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


def extract_objects_from_call(call_node: NodeOrLeaf) -> list[Any] | None:
    """Extract objects list from Selector parameter call."""
    kwargs = get_keyword_arguments(call_node)
    if "objects" in kwargs:
        # Extract list values from the objects argument
        return _extract_list_values(kwargs["objects"])
    return None


def extract_item_type_from_call(call_node: NodeOrLeaf) -> type | None:
    """Extract item_type from List parameter call."""
    kwargs = get_keyword_arguments(call_node)
    if "item_type" in kwargs:
        # Extract the type from the item_type argument
        return _extract_type_value(kwargs["item_type"])
    return None


def extract_length_from_call(call_node: NodeOrLeaf) -> int | None:
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


def _extract_type_value(type_node: NodeOrLeaf) -> type | None:
    """Extract a type from a parso node (e.g., str, int, float)."""
    if not type_node or not hasattr(type_node, "type"):
        return None

    if type_node.type == "name":
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


def _extract_list_values(list_node: NodeOrLeaf) -> list[Any] | None:
    """Extract values from a list node, preserving their original types."""
    if not list_node or not hasattr(list_node, "type"):
        return None

    if list_node.type == "atom":
        # Check if it's a list [item1, item2, ...]
        children = get_children(list_node)
        if len(children) >= 3 and get_value(children[0]) == "[" and get_value(children[-1]) == "]":
            # Extract items between brackets - could be in testlist_comp or directly
            items = []
            for child in children[1:-1]:  # Skip brackets
                if hasattr(child, "type"):
                    if child.type == "string":
                        # Direct string child
                        value = get_value(child)
                        if value and len(value) >= 2:
                            # Remove surrounding quotes and return as string
                            if (value.startswith('"') and value.endswith('"')) or (
                                value.startswith("'") and value.endswith("'")
                            ):
                                items.append(value[1:-1])
                            else:
                                items.append(value)
                    elif child.type == "number":
                        # Direct number child - extract as actual number
                        numeric_value = extract_numeric_value(child)
                        if numeric_value is not None:
                            items.append(numeric_value)
                    elif child.type in ("testlist_comp", "testlist"):
                        # testlist_comp contains the actual nodes
                        for grandchild in get_children(child):
                            if hasattr(grandchild, "type"):
                                if grandchild.type == "string":
                                    value = get_value(grandchild)
                                    if value and len(value) >= 2:
                                        # Remove surrounding quotes and return as string
                                        if (value.startswith('"') and value.endswith('"')) or (
                                            value.startswith("'") and value.endswith("'")
                                        ):
                                            items.append(value[1:-1])
                                        else:
                                            items.append(value)
                                elif grandchild.type == "number":
                                    # Extract as actual number
                                    numeric_value = extract_numeric_value(grandchild)
                                    if numeric_value is not None:
                                        items.append(numeric_value)
            return items if items else None

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


def resolve_parameter_class(
    param_call: NodeOrLeaf, imports: dict[str, str]
) -> dict[str, str] | None:
    """Resolve parameter class from a parso power node like param.Integer()."""
    # Extract the function name from the call
    func_name = None
    module_name = None

    for child in get_children(param_call):
        if child.type == "name":
            # Simple case: Integer() or param (first part of param.Integer)
            if func_name is None:
                func_name = get_value(child)
            else:
                module_name = func_name
                func_name = get_value(child)
        elif child.type == "trailer":
            # Handle dotted calls like param.Integer
            for trailer_child in get_children(child):
                if trailer_child.type == "name":
                    if module_name is None:
                        module_name = func_name  # Previous name becomes module
                    func_name = get_value(trailer_child)

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
    assignment_node: NodeOrLeaf,
    param_name: str,
    imports: dict[str, str],
    current_file_content: str | None = None,
) -> ParameterInfo | None:
    """Extract parameter info from a parso assignment statement."""
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
    found_equals = False
    for child in get_children(assignment_node):
        if hasattr(child, "type") and child.type == "operator" and get_value(child) == "=":
            found_equals = True
        elif found_equals and hasattr(child, "type") and child.type in ("power", "atom_expr"):
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
            # Get line number from the parso node
            line_number = assignment_node.start_pos[0]
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
