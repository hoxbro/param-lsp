"""
Utilities for working with tree-sitter AST nodes.
Provides helper functions for common tree-sitter operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

    from tree_sitter import Node


def get_value(node: Node | None) -> str | None:
    """Safely extract the string value from a tree-sitter node.

    Args:
        node: The tree-sitter node to extract value from

    Returns:
        The string value of the node's text if it exists, None otherwise
    """
    if node is None:
        return None
    if hasattr(node, "text") and node.text is not None:
        return node.text.decode("utf-8")
    return None


def get_children(node: Node | None) -> list[Node]:
    """Safely extract child nodes from a tree-sitter node.

    Args:
        node: The tree-sitter node to extract children from

    Returns:
        List of child nodes if they exist, empty list otherwise
    """
    if node is None:
        return []
    if hasattr(node, "children"):
        return list(node.children)
    return []


def walk_tree(node: Node | None) -> Generator[Node, None, None]:
    """Recursively walk a tree-sitter AST tree, yielding all nodes in depth-first order.

    Args:
        node: The root node to start walking from

    Yields:
        Each node in the tree, starting with the root node, then all descendants
    """
    if node is None:
        return
    yield node
    for child in get_children(node):
        if child is not None:
            yield from walk_tree(child)


def get_class_name(class_node: Node) -> str | None:
    """Extract the class name from a tree-sitter class_definition node.

    Args:
        class_node: A tree-sitter node of type 'class_definition'

    Returns:
        The class name as a string if found, None otherwise
    """
    if class_node is None:
        return None

    # Try to get name via field accessor first (more reliable for tree-sitter)
    if hasattr(class_node, "child_by_field_name"):
        name_node = class_node.child_by_field_name("name")
        if name_node:
            return get_value(name_node)

    # Fallback: search children for identifier after "class" keyword
    found_class_keyword = False
    for child in get_children(class_node):
        if hasattr(child, "type"):
            if child.type == "class" or (
                child.type == "identifier" and get_value(child) == "class"
            ):
                found_class_keyword = True
            elif found_class_keyword and child.type == "identifier":
                return get_value(child)

    return None


def get_class_bases(class_node: Node) -> list[Node]:
    """Extract base class nodes from a tree-sitter class_definition node.

    Args:
        class_node: A tree-sitter node of type 'class_definition'

    Returns:
        List of tree-sitter nodes representing the base classes
    """
    bases = []

    # Try to get superclasses via field accessor
    if hasattr(class_node, "child_by_field_name"):
        superclasses_node = class_node.child_by_field_name("superclasses")
        if superclasses_node:
            # Superclasses node is an argument_list containing the base classes
            bases.extend(
                child
                for child in get_children(superclasses_node)
                if child.type in ("identifier", "attribute", "call")
            )
            return bases

    # Fallback: look for bases between parentheses in class definition
    in_parentheses = False
    for child in get_children(class_node):
        if hasattr(child, "type"):
            if child.type == "operator" and get_value(child) == "(":
                in_parentheses = True
            elif child.type == "operator" and get_value(child) == ")":
                in_parentheses = False
            elif in_parentheses:
                if child.type in ("identifier", "attribute", "call"):
                    bases.append(child)
                elif child.type == "argument_list":
                    # Multiple bases in argument list
                    bases.extend(
                        [
                            arg_child
                            for arg_child in get_children(child)
                            if arg_child.type in ("identifier", "attribute", "call")
                        ]
                    )

    return bases


def is_assignment_stmt(node: Node) -> bool:
    """Check if a tree-sitter node represents an assignment statement.

    Args:
        node: The tree-sitter node to check

    Returns:
        True if the node is an assignment or contains an assignment operator '=', False otherwise
    """
    if node is None:
        return False

    # In tree-sitter, assignment nodes have type "assignment"
    if hasattr(node, "type") and node.type == "assignment":
        return True

    # Also check for expression_statement containing assignment
    if hasattr(node, "type") and node.type == "expression_statement":
        for child in get_children(node):
            if child.type == "assignment":
                return True

    # Fallback: Look for assignment operator '=' in the children
    return any(get_value(child) == "=" for child in get_children(node) if hasattr(child, "type"))


def get_assignment_target_name(node: Node) -> str | None:
    """Extract the target variable name from an assignment statement.

    Args:
        node: A tree-sitter node representing an assignment statement

    Returns:
        The name of the variable being assigned to, or None if not found
    """
    # Try to get left side via field accessor
    if hasattr(node, "child_by_field_name") and node.type == "assignment":
        left_node = node.child_by_field_name("left")
        if left_node and left_node.type == "identifier":
            return get_value(left_node)

    # Fallback: The target is typically the first child before the '=' operator
    for child in get_children(node):
        if hasattr(child, "type"):
            if child.type == "identifier":
                return get_value(child)
            elif get_value(child) == "=":
                break

    return None


def is_function_call(node: Node) -> bool:
    """Check if a tree-sitter node represents a function call.

    Args:
        node: The tree-sitter node to check

    Returns:
        True if the node represents a function call, False otherwise
    """
    if not hasattr(node, "type"):
        return False

    # In tree-sitter, function calls have type "call"
    return node.type == "call"


def find_class_suites(class_node: Node) -> Generator[Node, None, None]:
    """Generator that yields class suite/body nodes from a class definition.

    In tree-sitter, the class body is typically accessed via the 'body' field.
    Also checks ERROR nodes to handle syntax errors gracefully.
    """
    yielded = False

    if hasattr(class_node, "child_by_field_name"):
        body_node = class_node.child_by_field_name("body")
        if body_node:
            yield body_node
            yielded = True

    # Check for ERROR nodes and block/suite nodes in children
    # This handles cases where syntax errors cause parameters to be in ERROR nodes
    # Only yield these if we haven't yielded a body node yet
    for child in get_children(class_node):
        if hasattr(child, "type"):
            if child.type in ("block", "suite") and not yielded:
                yield child
                yielded = True
            elif child.type == "ERROR":
                # Always yield ERROR nodes as they might contain parameters
                # even if there's also a body node
                yield child


def find_parameter_assignments(
    suite_node: Node,
    is_parameter_assignment_func,
) -> Generator[tuple[Node, str], None, None]:
    """Generator that yields parameter assignment nodes from a class suite/body."""
    for item in get_children(suite_node):
        if not hasattr(item, "type"):
            continue

        if item.type == "assignment" and is_assignment_stmt(item):
            target_name = get_assignment_target_name(item)
            if target_name and is_parameter_assignment_func(item):
                yield item, target_name
        elif item.type == "expression_statement":
            # Check if expression statement contains assignment
            for child in get_children(item):
                if child.type == "assignment" and is_assignment_stmt(child):
                    target_name = get_assignment_target_name(child)
                    if target_name and is_parameter_assignment_func(child):
                        yield child, target_name


def find_function_call_trailers(call_node: Node) -> Generator[Node, None, None]:
    """Generator that yields function call argument list nodes.

    In tree-sitter, a call node has an 'arguments' field containing the argument list.
    """
    if hasattr(call_node, "child_by_field_name") and call_node.type == "call":
        args_node = call_node.child_by_field_name("arguments")
        if args_node:
            yield args_node
            return

    # Fallback: search for argument_list nodes
    for child in get_children(call_node):
        if hasattr(child, "type") and child.type == "argument_list":
            yield child


def find_arguments_in_trailer(trailer_node: Node) -> Generator[Node, None, None]:
    """Generator that yields argument nodes from a function call argument list."""
    for child in get_children(trailer_node):
        if not hasattr(child, "type"):
            continue

        # Tree-sitter has keyword_argument and regular arguments
        if child.type == "keyword_argument":
            yield child
        elif child.type not in ("(", ")", ","):  # Skip punctuation
            # Regular positional arguments
            yield child


def find_all_parameter_assignments(
    class_node: Node,
    is_parameter_assignment_func,
) -> Generator[tuple[Node, str], None, None]:
    """Generator that yields all parameter assignments in a class."""
    for suite_node in find_class_suites(class_node):
        yield from find_parameter_assignments(suite_node, is_parameter_assignment_func)
