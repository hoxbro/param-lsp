"""Tree-sitter utilities for param-lsp.

This module provides tree-sitter parsing and navigation utilities.
"""

from __future__ import annotations

from . import parser, queries
from .queries import find_decorators
from .utils import (
    find_all_parameter_assignments,
    find_arguments_in_trailer,
    find_class_suites,
    find_function_call_trailers,
    find_parameter_assignments,
    get_assignment_target_name,
    get_children,
    get_class_bases,
    get_class_name,
    get_value,
    is_assignment_stmt,
    is_function_call,
    walk_tree,
)

__all__ = [
    "find_all_parameter_assignments",
    "find_arguments_in_trailer",
    "find_class_suites",
    "find_decorators",
    "find_function_call_trailers",
    "find_parameter_assignments",
    "get_assignment_target_name",
    "get_children",
    "get_class_bases",
    "get_class_name",
    "get_value",
    "is_assignment_stmt",
    "is_function_call",
    "parser",
    "queries",
    "walk_tree",
]
