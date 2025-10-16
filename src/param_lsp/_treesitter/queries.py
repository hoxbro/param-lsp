"""Tree-sitter query-based AST utilities for better performance.

This module uses tree-sitter's query API to efficiently find AST patterns
without manually walking the entire tree. Queries are compiled once and cached
for reuse, providing significant performance improvements over manual traversal.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tree_sitter import Language, Query, QueryCursor, Tree
from tree_sitter_python import language

if TYPE_CHECKING:
    from tree_sitter import Node

# Compiled query cache
_QUERY_CACHE: dict[str, Query] = {}

# Language singleton
_LANGUAGE: Language | None = None


def _get_language() -> Language:
    """Get or create the Language object."""
    global _LANGUAGE  # noqa: PLW0603
    if _LANGUAGE is None:
        _LANGUAGE = Language(language())
    return _LANGUAGE


def _get_query(query_string: str) -> Query:
    """Get or compile a tree-sitter query.

    Args:
        query_string: S-expression query pattern

    Returns:
        Compiled Query object
    """
    if query_string not in _QUERY_CACHE:
        lang = _get_language()
        _QUERY_CACHE[query_string] = Query(lang, query_string)
    return _QUERY_CACHE[query_string]


def _execute_query(query: Query, node: Node) -> list[tuple[int, dict[str, list[Node]]]]:
    """Execute a query on a node using QueryCursor.

    Args:
        query: Compiled Query object
        node: Node to search

    Returns:
        List of (pattern_index, captures_dict) tuples
    """
    cursor = QueryCursor(query)
    return cursor.matches(node)


# Pre-defined queries for common patterns
_QUERIES = {
    # Find all class definitions
    "classes": """
        (class_definition
            name: (identifier) @class_name
            body: (block) @class_body) @class
    """,
    # Find all import statements
    "imports": """
        [(import_statement) @import
         (import_from_statement) @import_from]
    """,
    # Find all function definitions
    "functions": """
        [(function_definition
            name: (identifier) @func_name
            body: (block) @func_body) @function
         (async_function_definition
            name: (identifier) @func_name
            body: (block) @func_body) @function]
    """,
    # Find all assignments
    "assignments": """
        (assignment
            left: (_) @target
            right: (_) @value) @assignment
    """,
    # Find all function calls
    "calls": """
        (call
            function: (_) @function
            arguments: (argument_list) @arguments) @call
    """,
    # Find parameter assignments (class-level assignments)
    "parameter_assignments": """
        (class_definition
            body: (block
                (expression_statement
                    (assignment
                        left: (identifier) @param_name
                        right: (call
                            function: (_) @param_type)) @param_assignment)))
    """,
    # Find decorator usage
    "decorators": """
        (decorated_definition
            (decorator) @decorator
            definition: (_) @definition)
    """,
    # Find attribute access
    "attributes": """
        (attribute
            object: (_) @object
            attribute: (identifier) @attribute) @attr_access
    """,
}


def find_classes(tree: Tree | Node) -> list[tuple[Node, dict[str, Node]]]:
    """Find all class definitions using query.

    Args:
        tree: Tree or Node to search

    Returns:
        List of (class_node, captures_dict) tuples where captures_dict contains:
            - "class": the full class definition node
            - "class_name": the identifier node with the class name
            - "class_body": the block node with the class body
    """
    root_node: Node = tree.root_node if isinstance(tree, Tree) else tree
    query = _get_query(_QUERIES["classes"])
    matches = _execute_query(query, root_node)

    results = []
    for _, captures_dict in matches:
        # captures_dict maps capture names to lists of nodes
        if captures_dict.get("class"):
            class_node = captures_dict["class"][0]
            # Build captures dict with single nodes (not lists)
            result_captures = {
                "class": class_node,
                "class_name": captures_dict.get("class_name", [None])[0],
                "class_body": captures_dict.get("class_body", [None])[0],
            }
            results.append((class_node, result_captures))

    return results


def find_imports(tree: Tree | Node) -> list[tuple[Node, dict[str, Node]]]:
    """Find all import statements using query.

    Args:
        tree: Tree or Node to search

    Returns:
        List of (import_node, captures_dict) tuples where captures_dict contains:
            - "import" or "import_from": the import statement node
    """
    root_node: Node = tree.root_node if isinstance(tree, Tree) else tree
    query = _get_query(_QUERIES["imports"])
    matches = _execute_query(query, root_node)

    results = []
    for _, captures_dict in matches:
        # Get the first available import node
        import_node = None
        result_captures = {}
        if captures_dict.get("import"):
            import_node = captures_dict["import"][0]
            result_captures["import"] = import_node
        elif captures_dict.get("import_from"):
            import_node = captures_dict["import_from"][0]
            result_captures["import_from"] = import_node

        if import_node:
            results.append((import_node, result_captures))

    return results


def find_assignments(tree: Tree | Node) -> list[tuple[Node, dict[str, Node]]]:
    """Find all assignment statements using query.

    Args:
        tree: Tree or Node to search

    Returns:
        List of (assignment_node, captures_dict) tuples where captures_dict contains:
            - "assignment": the full assignment node
            - "target": the left side of the assignment
            - "value": the right side of the assignment
    """
    root_node: Node = tree.root_node if isinstance(tree, Tree) else tree
    query = _get_query(_QUERIES["assignments"])
    matches = _execute_query(query, root_node)

    results = []
    for _, captures_dict in matches:
        if captures_dict.get("assignment"):
            assignment_node = captures_dict["assignment"][0]
            result_captures = {
                "assignment": assignment_node,
                "target": captures_dict.get("target", [None])[0],
                "value": captures_dict.get("value", [None])[0],
            }
            results.append((assignment_node, result_captures))

    return results


def find_calls(tree: Tree | Node) -> list[tuple[Node, dict[str, Node]]]:
    """Find all function/method calls using query.

    Args:
        tree: Tree or Node to search

    Returns:
        List of (call_node, captures_dict) tuples where captures_dict contains:
            - "call": the full call node
            - "function": the function being called
            - "arguments": the argument list
    """
    root_node: Node = tree.root_node if isinstance(tree, Tree) else tree
    query = _get_query(_QUERIES["calls"])
    matches = _execute_query(query, root_node)

    results = []
    for _, captures_dict in matches:
        if captures_dict.get("call"):
            call_node = captures_dict["call"][0]
            result_captures = {
                "call": call_node,
                "function": captures_dict.get("function", [None])[0],
                "arguments": captures_dict.get("arguments", [None])[0],
            }
            results.append((call_node, result_captures))

    return results


def find_decorators(tree: Tree | Node) -> list[tuple[Node, dict[str, Node]]]:
    """Find all decorator usage using query.

    Args:
        tree: Tree or Node to search

    Returns:
        List of (decorator_node, captures_dict) tuples where captures_dict contains:
            - "decorator": the decorator node
            - "definition": the decorated definition
    """
    root_node: Node = tree.root_node if isinstance(tree, Tree) else tree
    query = _get_query(_QUERIES["decorators"])
    matches = _execute_query(query, root_node)

    results = []
    for _, captures_dict in matches:
        if "decorator" in captures_dict:
            for decorator_node in captures_dict["decorator"]:
                result_captures = {
                    "decorator": decorator_node,
                    "definition": captures_dict.get("definition", [None])[0],
                }
                results.append((decorator_node, result_captures))

    return results


def find_attributes(tree: Tree | Node) -> list[tuple[Node, dict[str, Node]]]:
    """Find all attribute accesses using query.

    Args:
        tree: Tree or Node to search

    Returns:
        List of (attr_node, captures_dict) tuples where captures_dict contains:
            - "attr_access": the full attribute access node
            - "object": the object being accessed
            - "attribute": the attribute name identifier
    """
    root_node: Node = tree.root_node if isinstance(tree, Tree) else tree
    query = _get_query(_QUERIES["attributes"])
    matches = _execute_query(query, root_node)

    results = []
    for _, captures_dict in matches:
        if captures_dict.get("attr_access"):
            attr_node = captures_dict["attr_access"][0]
            result_captures = {
                "attr_access": attr_node,
                "object": captures_dict.get("object", [None])[0],
                "attribute": captures_dict.get("attribute", [None])[0],
            }
            results.append((attr_node, result_captures))

    return results


def query_custom(tree: Tree | Node, query_string: str) -> list[tuple[Node, dict[str, list[Node]]]]:
    """Execute a custom tree-sitter query.

    Args:
        tree: Tree or Node to search
        query_string: S-expression query pattern

    Returns:
        List of (first_capture_node, all_captures_dict) tuples
        Note: captures_dict values are lists of nodes (unlike the predefined queries)
    """
    root_node: Node = tree.root_node if isinstance(tree, Tree) else tree
    query = _get_query(query_string)
    matches = _execute_query(query, root_node)

    results = []
    for _, captures_dict in matches:
        # For custom queries, return the raw captures_dict (with lists)
        if captures_dict:
            # Use the first node from the first capture as the primary node
            first_nodes = next(iter(captures_dict.values()))
            if first_nodes:
                results.append((first_nodes[0], captures_dict))

    return results


def clear_query_cache() -> None:
    """Clear the compiled query cache.

    Useful for testing or memory management.
    """
    _QUERY_CACHE.clear()
