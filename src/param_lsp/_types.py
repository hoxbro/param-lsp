"""Centralized type definitions for param-lsp.

This module contains all common type hints and TypedDict definitions
to avoid duplication across the codebase.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeAlias, TypedDict

if TYPE_CHECKING:
    from tree_sitter import Node

    from param_lsp.models import ParameterInfo, ParameterizedInfo


# =============================================================================
# TREE-SITTER TYPE ALIASES
# =============================================================================

# Re-export tree-sitter types for convenience
TSNode: TypeAlias = "Node"


# =============================================================================
# COMMON TYPE ALIASES
# =============================================================================

# Import mappings (alias -> full module name)
ImportDict: TypeAlias = dict[str, str]

# Parameter class mappings (class name -> class info)
ParamClassDict: TypeAlias = dict[str, "ParameterizedInfo"]

# External parameter class mappings (class name -> class info, may be None if analysis failed)
ExternalParamClassDict: TypeAlias = dict[str, "ParameterizedInfo | None"]

# Parameter mappings (parameter name -> parameter info)
ParameterDict: TypeAlias = dict[str, "ParameterInfo"]

# String to string mappings
StringDict: TypeAlias = dict[str, str]

# String to Any mappings (for cache data, document cache, etc.)
AnyDict: TypeAlias = dict[str, Any]

# Keyword arguments from tree-sitter nodes
KwargsDict: TypeAlias = dict[str, "Node"]


# =============================================================================
# TYPED DICT DEFINITIONS
# =============================================================================


class TypeErrorDict(TypedDict):
    """Type definition for type error dictionaries."""

    line: int
    col: int
    end_line: int
    end_col: int
    message: str
    severity: str
    code: str


class AnalysisResult(TypedDict):
    """Type definition for analysis result dictionaries."""

    param_classes: ParamClassDict
    imports: ImportDict
    type_errors: list[TypeErrorDict]
