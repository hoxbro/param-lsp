"""Base class for LSP server with interface for mixins."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pygls.server import LanguageServer

if TYPE_CHECKING:
    from param_lsp.analyzer import ParamAnalyzer


class LSPServerBase(LanguageServer):
    """Base class defining the interface needed by mixins.

    This class provides the minimal interface that mixins expect,
    reducing the need for verbose type annotations in mixin methods.
    """

    # Core attributes required by mixins
    workspace_root: str | None
    analyzer: ParamAnalyzer
    document_cache: dict[str, dict[str, Any]]
    param_types: list[str]

    # Method stubs for methods implemented by mixins or LanguageServer
    # Note: publish_diagnostics is implemented by LanguageServer with different signature

    def _analyze_document(self, uri: str, content: str) -> None:
        """Analyze document content and cache results."""

    def _uri_to_path(self, uri: str) -> str:
        """Convert URI to file path."""
        return ""

    def _get_python_type_name(self, param_type: str, allow_none: bool = False) -> str:
        """Map param type to Python type name for display."""
        return ""

    def _clean_and_format_documentation(self, doc: str) -> str:
        """Clean and format documentation text."""
        return ""

    def _format_default_for_display(
        self, default_value: Any, param_type: str | None = None
    ) -> str:
        """Format default value for display."""
        return ""

    def _build_parameter_documentation(
        self,
        param_name: str,
        class_name: str,
        parameter_types: dict[str, str],
        parameter_docs: dict[str, str],
        parameter_bounds: dict[str, tuple],
        parameter_allow_none: dict[str, bool] | None = None,
        parameter_defaults: dict[str, str] | None = None,
    ) -> str:
        """Build documentation for a parameter."""
        return ""

    def _find_containing_class(self, lines: list[str], current_line: int) -> str | None:
        """Find the containing class for a given line."""
        return None

    def _resolve_class_name_from_context(
        self, uri: str, class_name: str, param_classes: set[str]
    ) -> str | None:
        """Resolve a class name from context."""
        return None

    def _should_include_parentheses_in_insert_text(
        self, line: str, character: int, method_name: str
    ) -> bool:
        """Determine if parentheses should be included in insert_text."""
        return False
