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

    # Completion methods
    def _is_in_param_definition_context(self, line: str, character: int) -> bool:
        """Check if we're in a parameter definition context."""
        ...

    def _get_completions_for_param_class(self, line: str, character: int) -> list[Any]:
        """Get completions for param class attributes and methods."""
        ...

    def _is_in_constructor_context(self, uri: str, line: str, character: int) -> bool:
        """Check if the cursor is in a param class constructor context."""
        ...

    def _get_constructor_parameter_completions(
        self, uri: str, line: str, character: int
    ) -> list[Any]:
        """Get parameter completions for param class constructors."""
        ...

    def _get_param_depends_completions(
        self, uri: str, lines: list[str], position: Any
    ) -> list[Any]:
        """Get parameter completions for param.depends decorator."""
        ...

    def _is_in_param_depends_decorator(self, lines: list[str], position: Any) -> bool:
        """Check if the current position is inside a param.depends decorator."""
        ...

    def _extract_partial_parameter_text(self, lines: list[str], position: Any) -> str:
        """Extract the partial parameter text being typed."""
        ...

    def _extract_used_depends_parameters_multiline(
        self, lines: list[str], position: Any
    ) -> set[str]:
        """Extract parameter names already used in the param.depends decorator."""
        ...

    def _extract_used_depends_parameters(self, line: str, character: int) -> set[str]:
        """Extract parameter names already used in the param.depends decorator."""
        ...

    def _find_containing_class(self, lines: list[str], current_line: int) -> str | None:
        """Find the containing class for a given line."""
        ...

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
        ...

    def _format_default_for_display(
        self, default_value: Any, param_type: str | None = None
    ) -> str:
        """Format default value for display."""
        ...

    def _resolve_external_class_path(self, class_name: str, analyzer: Any) -> str | None:
        """Resolve external class path using import aliases."""
        ...

    def _get_param_attribute_completions(self, uri: str, line: str, character: int) -> list[Any]:
        """Get parameter completions for param attribute access."""
        ...

    def _get_param_object_attribute_completions(
        self, uri: str, line: str, character: int
    ) -> list[Any]:
        """Get attribute completions for Parameter objects."""
        ...

    def _get_reactive_expression_completions(
        self, uri: str, line: str, character: int
    ) -> list[Any]:
        """Get method completions for reactive expressions."""
        ...

    def _get_param_update_completions(self, uri: str, line: str, character: int) -> list[Any]:
        """Get parameter completions for obj.param.update() keyword arguments."""
        ...

    def _resolve_class_name_from_context(
        self, uri: str, class_name: str, param_classes: set[str]
    ) -> str | None:
        """Resolve a class name from context, handling both direct class names and variable names."""
        ...

    def _should_include_parentheses_in_insert_text(
        self, line: str, character: int, method_name: str
    ) -> bool:
        """Determine if parentheses should be included in insert_text for method completions."""
        ...
