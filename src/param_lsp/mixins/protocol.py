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

    # Mixin methods that will be provided by mixins
    def _get_python_type_name(self, param_type: str, allow_none: bool = False) -> str:
        """Map param type to Python type name for display."""
        ...

    def _publish_diagnostics(self, uri: str, type_errors: list[dict[str, Any]]) -> None:
        """Publish diagnostics for type errors."""
        ...
