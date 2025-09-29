"""
Utilities for working with parso AST nodes.
Provides helper functions for common parso operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

    from parso.tree import NodeOrLeaf


def has_value(node: NodeOrLeaf | None) -> bool:
    """Check if a parso node has a value attribute.

    Args:
        node: The parso node to check

    Returns:
        True if the node has a 'value' attribute, False otherwise

    Example:
        >>> import parso
        >>> tree = parso.parse("x = 1")
        >>> name_node = tree.children[0].children[0]  # 'x' node
        >>> has_value(name_node)
        True
    """
    if node is None:
        return False
    return hasattr(node, "value")


def get_value(node: NodeOrLeaf | None) -> str | None:
    """Safely extract the string value from a parso node.

    Args:
        node: The parso node to extract value from

    Returns:
        The string value of the node if it exists, None otherwise

    Example:
        >>> import parso
        >>> tree = parso.parse("x = 'hello'")
        >>> string_node = tree.children[0].children[2]  # 'hello' node
        >>> get_value(string_node)
        "'hello'"
    """
    if node is None:
        return None
    return getattr(node, "value", None)


def has_children(node: NodeOrLeaf | None) -> bool:
    """Check if a parso node has child nodes.

    Args:
        node: The parso node to check

    Returns:
        True if the node has a 'children' attribute, False otherwise

    Note:
        Leaf nodes (like literals, names) typically don't have children,
        while internal nodes (like expressions, statements) do.

    Example:
        >>> import parso
        >>> tree = parso.parse("x = 1")
        >>> has_children(tree)  # Module node has children
        True
        >>> leaf = tree.children[0].children[0]  # 'x' name node
        >>> has_children(leaf)  # Name nodes don't have children
        False
    """
    if node is None:
        return False
    return hasattr(node, "children")


def get_children(node: NodeOrLeaf | None) -> list[NodeOrLeaf]:
    """Safely extract child nodes from a parso node.

    Args:
        node: The parso node to extract children from

    Returns:
        List of child nodes if they exist, empty list otherwise

    Example:
        >>> import parso
        >>> tree = parso.parse("x = 1")
        >>> children = get_children(tree)
        >>> len(children) > 0  # Module has children
        True
        >>> leaf_children = get_children(tree.children[0].children[0])
        >>> len(leaf_children)  # Name nodes have no children
        0
    """
    if node is None:
        return []
    children = getattr(node, "children", [])
    return children if children is not None else []


def walk_tree(node: NodeOrLeaf | None) -> Generator[NodeOrLeaf, None, None]:
    """Recursively walk a parso AST tree, yielding all nodes in depth-first order.

    Args:
        node: The root node to start walking from

    Yields:
        Each node in the tree, starting with the root node, then all descendants

    Example:
        >>> import parso
        >>> tree = parso.parse("x = 1")
        >>> nodes = list(walk_tree(tree))
        >>> len(nodes) >= 3  # At least module, expr_stmt, and child nodes
        True
        >>> nodes[0] == tree  # First node is the root
        True
    """
    if node is None:
        return
    yield node
    if has_children(node):
        for child in get_children(node):
            if child is not None:
                yield from walk_tree(child)


def get_class_name(class_node: NodeOrLeaf) -> str | None:
    """Extract the class name from a parso classdef node.

    Args:
        class_node: A parso node of type 'classdef'

    Returns:
        The class name as a string if found, None otherwise

    Example:
        >>> import parso
        >>> tree = parso.parse("class MyClass: pass")
        >>> class_def = tree.children[0]  # The classdef node
        >>> get_class_name(class_def)
        'MyClass'
    """
    if class_node is None:
        return None
    for child in get_children(class_node):
        if hasattr(child, "type") and child.type == "name":
            return get_value(child)
    return None


def get_class_bases(class_node: NodeOrLeaf) -> list[NodeOrLeaf]:
    """Extract base class nodes from a parso classdef node.

    Args:
        class_node: A parso node of type 'classdef'

    Returns:
        List of parso nodes representing the base classes

    Example:
        >>> import parso
        >>> tree = parso.parse("class Child(Parent, Mixin): pass")
        >>> class_def = tree.children[0]
        >>> bases = get_class_bases(class_def)
        >>> len(bases)
        2
        >>> get_value(bases[0])  # First base class
        'Parent'
    """
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
    """Check if a parso node represents an assignment statement.

    Args:
        node: The parso node to check

    Returns:
        True if the node contains an assignment operator '=', False otherwise

    Example:
        >>> import parso
        >>> tree = parso.parse("x = 1")
        >>> stmt = tree.children[0]  # The expr_stmt node
        >>> is_assignment_stmt(stmt)
        True
        >>> tree2 = parso.parse("print('hello')")
        >>> stmt2 = tree2.children[0]
        >>> is_assignment_stmt(stmt2)
        False
    """
    # Look for assignment operator '=' in the children
    return any(
        child.type == "operator" and get_value(child) == "=" for child in get_children(node)
    )


def get_assignment_target_name(node: NodeOrLeaf) -> str | None:
    """Extract the target variable name from an assignment statement.

    Args:
        node: A parso node representing an assignment statement

    Returns:
        The name of the variable being assigned to, or None if not found

    Example:
        >>> import parso
        >>> tree = parso.parse("my_var = 42")
        >>> stmt = tree.children[0]
        >>> get_assignment_target_name(stmt)
        'my_var'
    """
    # The target is typically the first child before the '=' operator
    for child in get_children(node):
        if child.type == "name":
            return get_value(child)
        elif child.type == "operator" and get_value(child) == "=":
            break
    return None


def has_attribute_target(node: NodeOrLeaf) -> bool:
    """Check if an assignment statement targets an attribute (like obj.attr = value).

    Args:
        node: A parso node representing an assignment statement

    Returns:
        True if the assignment targets an attribute, False otherwise

    Example:
        >>> import parso
        >>> tree1 = parso.parse("obj.attr = 1")
        >>> stmt1 = tree1.children[0]
        >>> has_attribute_target(stmt1)
        True
        >>> tree2 = parso.parse("x = 1")
        >>> stmt2 = tree2.children[0]
        >>> has_attribute_target(stmt2)
        False
    """
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
    """Check if a parso node represents a function call (has trailing parentheses).

    Args:
        node: The parso node to check

    Returns:
        True if the node represents a function call, False otherwise

    Example:
        >>> import parso
        >>> tree = parso.parse("func(arg)")
        >>> call_node = tree.children[0].children[0]  # The function call
        >>> is_function_call(call_node)
        True
        >>> tree2 = parso.parse("variable")
        >>> var_node = tree2.children[0].children[0]
        >>> is_function_call(var_node)
        False
    """
    if not hasattr(node, "children"):
        return False
    return any(
        child.type == "trailer"
        and get_children(child)
        and get_value(get_children(child)[0]) == "("
        for child in get_children(node)
    )


def find_class_suites(class_node: NodeOrLeaf) -> Generator[NodeOrLeaf, None, None]:
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
    class_node: NodeOrLeaf,
    is_parameter_assignment_func,
) -> Generator[tuple[NodeOrLeaf, str], None, None]:
    """Generator that yields all parameter assignments in a class."""
    for suite_node in find_class_suites(class_node):
        yield from find_parameter_assignments(suite_node, is_parameter_assignment_func)
