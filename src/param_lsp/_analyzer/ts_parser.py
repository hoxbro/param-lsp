"""Tree-sitter Python parser singleton.

Provides a singleton instance of the tree-sitter Python parser for use across the codebase.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tree_sitter import Language, Parser
from tree_sitter_python import language

if TYPE_CHECKING:
    from tree_sitter import Tree

# Create the parser singleton
_parser: Parser | None = None


def _get_parser() -> Parser:
    """Get or create the tree-sitter Python parser singleton."""
    global _parser  # noqa: PLW0603
    if _parser is None:
        _parser = Parser(Language(language()))
    return _parser


def parse(source_code: str, error_recovery: bool = True) -> Tree:
    """Parse Python source code using tree-sitter.

    Args:
        source_code: Python source code to parse
        error_recovery: Whether to enable error recovery (always True for tree-sitter)

    Returns:
        Tree-sitter Tree object
    """
    parser = _get_parser()
    source_bytes = source_code.encode("utf-8") if isinstance(source_code, str) else source_code
    return parser.parse(source_bytes)
