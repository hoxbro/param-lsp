"""
Utilities for working with parso AST nodes.
Provides helper functions for common parso operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

    from parso.tree import BaseNode, NodeOrLeaf


def has_value(node: NodeOrLeaf) -> bool:
    """Check if node has a value attribute."""
    return hasattr(node, "value")


def get_value(node: NodeOrLeaf) -> str | None:
    """Safely get value from node."""
    return getattr(node, "value", None)


def has_children(node: NodeOrLeaf) -> bool:
    """Check if node has children attribute."""
    return hasattr(node, "children")


def get_children(node: NodeOrLeaf) -> list[NodeOrLeaf]:
    """Safely get children from node."""
    return getattr(node, "children", [])


def walk_tree(node: NodeOrLeaf) -> Generator[NodeOrLeaf, None, None]:
    """Walk a parso tree recursively, yielding all nodes."""
    yield node
    if has_children(node):
        for child in get_children(node):
            yield from walk_tree(child)


def get_class_name(class_node: BaseNode) -> str | None:
    """Extract class name from parso classdef node."""
    for child in get_children(class_node):
        if child.type == "name":
            return get_value(child)
    return None


def get_class_bases(class_node: BaseNode) -> list[NodeOrLeaf]:
    """Extract base classes from parso classdef node."""
    bases = []
    # Look for bases between parentheses in class definition
    in_parentheses = False
    for child in get_children(class_node):
        if child.type == "operator" and get_value(child) == "(":
            in_parentheses = True
        elif child.type == "operator" and get_value(child) == ")":
            in_parentheses = False
        elif in_parentheses:
            if child.type == "name":
                bases.append(child)
            elif child.type in ("atom_expr", "power"):
                # Handle dotted names like module.Class or param.Parameterized
                bases.append(child)
            elif child.type == "arglist":
                # Multiple bases in argument list
                bases.extend(
                    [
                        arg_child
                        for arg_child in get_children(child)
                        if arg_child.type == "name" or arg_child.type in ("atom_expr", "power")
                    ]
                )
    return bases


def is_assignment_stmt(node: NodeOrLeaf) -> bool:
    """Check if a parso node is an assignment statement."""
    # Look for assignment operator '=' in the children
    return any(
        child.type == "operator" and get_value(child) == "=" for child in get_children(node)
    )


def get_assignment_target_name(node: NodeOrLeaf) -> str | None:
    """Get the target name from an assignment statement."""
    # The target is typically the first child before the '=' operator
    for child in get_children(node):
        if child.type == "name":
            return get_value(child)
        elif child.type == "operator" and get_value(child) == "=":
            break
    return None


def has_attribute_target(node: NodeOrLeaf) -> bool:
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


def is_function_call(node: NodeOrLeaf) -> bool:
    """Check if a parso node represents a function call (has trailing parentheses)."""
    if not hasattr(node, "children"):
        return False
    return any(
        child.type == "trailer"
        and get_children(child)
        and get_value(get_children(child)[0]) == "("
        for child in get_children(node)
    )


def find_class_suites(class_node: BaseNode) -> Generator[NodeOrLeaf, None, None]:
    """Generator that yields class suite nodes from a class definition."""
    for child in get_children(class_node):
        if child.type == "suite":
            yield child


def find_parameter_assignments(
    suite_node: NodeOrLeaf,
    is_parameter_assignment_func,
) -> Generator[tuple[NodeOrLeaf, str], None, None]:
    """Generator that yields parameter assignment nodes from a class suite."""
    for item in get_children(suite_node):
        if item.type == "expr_stmt" and is_assignment_stmt(item):
            target_name = get_assignment_target_name(item)
            if target_name and is_parameter_assignment_func(item):
                yield item, target_name
        elif item.type == "simple_stmt":
            # Also check within simple statements for other formats
            yield from find_assignments_in_simple_stmt(item, is_parameter_assignment_func)


def find_assignments_in_simple_stmt(
    stmt_node: NodeOrLeaf,
    is_parameter_assignment_func,
) -> Generator[tuple[NodeOrLeaf, str], None, None]:
    """Generator that yields assignment nodes from a simple statement."""
    for stmt_child in get_children(stmt_node):
        if stmt_child.type == "expr_stmt" and is_assignment_stmt(stmt_child):
            target_name = get_assignment_target_name(stmt_child)
            if target_name and is_parameter_assignment_func(stmt_child):
                yield stmt_child, target_name


def find_function_call_trailers(call_node: NodeOrLeaf) -> Generator[NodeOrLeaf, None, None]:
    """Generator that yields function call trailers with arguments."""
    for child in get_children(call_node):
        if (
            child.type == "trailer"
            and get_children(child)
            and get_value(get_children(child)[0]) == "("
        ):
            yield child


def find_arguments_in_trailer(trailer_node: NodeOrLeaf) -> Generator[NodeOrLeaf, None, None]:
    """Generator that yields argument nodes from a function call trailer."""
    for trailer_child in get_children(trailer_node):
        if trailer_child.type == "arglist":
            # Multiple arguments in an arglist
            yield from find_arguments_in_arglist(trailer_child)
        elif trailer_child.type == "argument":
            # Single argument directly in trailer
            yield trailer_child


def find_arguments_in_arglist(arglist_node: NodeOrLeaf) -> Generator[NodeOrLeaf, None, None]:
    """Generator that yields argument nodes from an arglist."""
    for arg_child in get_children(arglist_node):
        if arg_child.type == "argument":
            yield arg_child


def find_all_parameter_assignments(
    class_node: BaseNode,
    is_parameter_assignment_func,
) -> Generator[tuple[NodeOrLeaf, str], None, None]:
    """Generator that yields all parameter assignments in a class."""
    for suite_node in find_class_suites(class_node):
        yield from find_parameter_assignments(suite_node, is_parameter_assignment_func)
