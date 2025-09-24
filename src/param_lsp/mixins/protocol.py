"""Protocol for LSP server mixins."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from param_lsp.analyzer import ParamAnalyzer


class LSPServerProtocol(Protocol):
    """Protocol defining the interface that LSP server must implement for mixins."""

    workspace_root: str | None
    analyzer: ParamAnalyzer
    document_cache: dict[str, dict[str, Any]]

    def publish_diagnostics(self, uri: str, diagnostics: list[Any]) -> None:
        """Publish diagnostics to the client."""
        ...

    # Additional server attributes needed by mixins
    param_types: list[str]

    # Mixin methods that will be provided by mixins
    def _get_python_type_name(self, param_type: str, allow_none: bool = False) -> str:
        """Map param type to Python type name for display."""
        ...

    def _publish_diagnostics(self, uri: str, type_errors: list[dict[str, Any]]) -> None:
        """Publish diagnostics for type errors."""
        ...

    def _clean_and_format_documentation(self, doc: str) -> str:
        """Clean and format documentation text."""
        ...

    def _get_hover_info(self, uri: str, line: str, word: str) -> str | None:
        """Get hover information for a word."""
        ...

    def _is_rx_method_context(self, line: str) -> bool:
        """Check if the rx word is in a parameter context."""
        ...

    def _build_rx_method_hover_info(self) -> str:
        """Build hover information for the rx property."""
        ...

    def _get_param_namespace_method_hover_info(self, line: str, word: str) -> str | None:
        """Get hover information for param namespace methods."""
        ...

    def _get_reactive_expression_method_hover_info(self, line: str, word: str) -> str | None:
        """Get hover information for reactive expression methods."""
        ...

    def _build_parameter_hover_info(
        self,
        param_name: str,
        class_name: str,
        param_parameter_types: dict[str, dict[str, str]],
        param_parameter_docs: dict[str, dict[str, str]],
        param_parameter_bounds: dict[str, dict[str, tuple]],
        param_parameter_allow_none: dict[str, dict[str, bool]] | None = None,
        param_parameter_locations: dict[str, dict[str, dict[str, Any]]] | None = None,
    ) -> str | None:
        """Build hover information for a local parameter."""
        ...

    def _build_external_parameter_hover_info(
        self, param_name: str, class_name: str, class_info: dict[str, Any]
    ) -> str | None:
        """Build hover information for an external parameter."""
        ...
