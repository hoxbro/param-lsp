"""Tree-sitter Python parser singleton with caching and incremental parsing.

Provides a singleton instance of the tree-sitter Python parser for use across the codebase,
with support for parse tree caching and incremental re-parsing for improved performance.
"""

from __future__ import annotations

import hashlib
import os
from collections import OrderedDict
from typing import TYPE_CHECKING

from tree_sitter import Language, Parser
from tree_sitter_python import language

if TYPE_CHECKING:
    from tree_sitter import Tree

# Create the parser singleton
_parser: Parser | None = None

# Parse tree cache: hash(source_code) -> (Tree, source_bytes)
# Using OrderedDict for LRU-like behavior
_parse_cache: OrderedDict[str, tuple[Tree, bytes]] = OrderedDict()

# Cache configuration
_CACHE_ENABLED = os.environ.get("PARAM_LSP_DISABLE_CACHE") != "1"
_MAX_CACHE_SIZE = int(os.environ.get("PARAM_LSP_CACHE_SIZE", "100"))


def _get_parser() -> Parser:
    """Get or create the tree-sitter Python parser singleton."""
    global _parser  # noqa: PLW0603
    if _parser is None:
        _parser = Parser(Language(language()))
    return _parser


def _compute_hash(source_bytes: bytes) -> str:
    """Compute SHA-256 hash of source code for cache key.

    Args:
        source_bytes: Source code as bytes

    Returns:
        Hex digest of SHA-256 hash
    """
    return hashlib.sha256(source_bytes).hexdigest()


def _cache_get(cache_key: str) -> tuple[Tree, bytes] | None:
    """Get cached parse tree if available.

    Args:
        cache_key: Cache key (hash of source code)

    Returns:
        Tuple of (Tree, source_bytes) if cached, None otherwise
    """
    if not _CACHE_ENABLED:
        return None

    if cache_key in _parse_cache:
        # Move to end (most recently used)
        _parse_cache.move_to_end(cache_key)
        return _parse_cache[cache_key]

    return None


def _cache_put(cache_key: str, tree: Tree, source_bytes: bytes) -> None:
    """Store parse tree in cache with LRU eviction.

    Args:
        cache_key: Cache key (hash of source code)
        tree: Parsed tree
        source_bytes: Source code as bytes
    """
    if not _CACHE_ENABLED:
        return

    # Add to cache
    _parse_cache[cache_key] = (tree, source_bytes)

    # Enforce size limit (LRU eviction)
    while len(_parse_cache) > _MAX_CACHE_SIZE:
        # Remove oldest entry (first item)
        _parse_cache.popitem(last=False)


def clear_cache() -> None:
    """Clear the parse tree cache.

    Useful for testing or when memory needs to be freed.
    """
    _parse_cache.clear()


def get_cache_stats() -> dict[str, int]:
    """Get cache statistics.

    Returns:
        Dictionary with cache size and capacity
    """
    return {
        "size": len(_parse_cache),
        "capacity": _MAX_CACHE_SIZE,
        "enabled": _CACHE_ENABLED,
    }


def parse(source_code: str, error_recovery: bool = True) -> Tree:
    """Parse Python source code using tree-sitter with caching.

    The parse tree is cached based on the source code hash. If the same
    source code is parsed again, the cached tree is returned for better performance.

    Args:
        source_code: Python source code to parse
        error_recovery: Whether to enable error recovery (always True for tree-sitter)

    Returns:
        Tree-sitter Tree object
    """
    parser = _get_parser()
    source_bytes = source_code.encode("utf-8") if isinstance(source_code, str) else source_code

    # Check cache first
    cache_key = _compute_hash(source_bytes)
    cached = _cache_get(cache_key)
    if cached is not None:
        cached_tree, cached_bytes = cached
        # Verify cached bytes match (hash collision protection)
        if cached_bytes == source_bytes:
            return cached_tree

    # Parse and cache
    tree = parser.parse(source_bytes)
    _cache_put(cache_key, tree, source_bytes)

    return tree


def parse_incremental(
    source_code: str,
    old_tree: Tree | None = None,
    old_source: str | None = None,
    error_recovery: bool = True,
) -> Tree:
    """Parse Python source code with incremental parsing support.

    When an old_tree is provided, tree-sitter will use incremental parsing
    to only re-parse the changed portions, improving performance for edits.

    Args:
        source_code: New Python source code to parse
        old_tree: Previous parse tree (from before the edit)
        old_source: Previous source code (used for cache invalidation)
        error_recovery: Whether to enable error recovery (always True for tree-sitter)

    Returns:
        Tree-sitter Tree object

    Note:
        For best performance with LSP text document changes, the caller should
        track edits and call tree.edit() on old_tree before passing it here.
    """
    parser = _get_parser()
    source_bytes = source_code.encode("utf-8") if isinstance(source_code, str) else source_code

    # Check cache first (even for incremental parsing)
    cache_key = _compute_hash(source_bytes)
    cached = _cache_get(cache_key)
    if cached is not None:
        cached_tree, cached_bytes = cached
        if cached_bytes == source_bytes:
            return cached_tree

    # Parse incrementally if old_tree is provided
    tree = parser.parse(source_bytes, old_tree=old_tree)

    # Cache the new tree
    _cache_put(cache_key, tree, source_bytes)

    return tree


def regenerate_cache() -> None:
    """Regenerate the cache by clearing it.

    This is useful for testing or debugging cache-related issues.
    Note: Since we use hash-based caching, there's no actual
    "regeneration" needed - just clear the cache.
    """
    clear_cache()
