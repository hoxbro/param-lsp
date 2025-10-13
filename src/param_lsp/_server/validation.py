"""Validation mixin for diagnostics and error reporting."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from lsprotocol.types import Diagnostic, DiagnosticSeverity, Position, Range

from param_lsp.analyzer import ParamAnalyzer

from .base import LSPServerBase

if TYPE_CHECKING:
    from param_lsp._types import TypeErrorDict

logger = logging.getLogger(__name__)


class ValidationMixin(LSPServerBase):
    """Provides validation and diagnostic functionality for the LSP server."""

    def _analyze_document(self, uri: str, content: str):
        """Analyze a document and cache the results."""
        file_path = self._uri_to_path(uri)

        # Update analyzer with workspace root if available
        if (
            hasattr(self, "workspace_root")
            and self.workspace_root
            and hasattr(self, "analyzer")
            and not self.analyzer.workspace_root
        ):
            # Recreate analyzer with workspace root, preserving python_env
            self.analyzer = ParamAnalyzer(
                python_env=self.python_env, workspace_root=self.workspace_root
            )

        analysis = self.analyzer.analyze_file(content, file_path)
        self.document_cache[uri] = {
            "content": content,
            "analysis": analysis,
            "analyzer": self.analyzer,
        }

        # Debug logging
        logger.info(f"Analysis results for {uri}:")
        param_classes = analysis.get("param_classes", {})
        logger.info(f"  Param classes: {set(param_classes.keys())}")
        logger.info(
            f"  Parameters: {[{name: info.get_parameter_names() for name, info in param_classes.items()}]}"
        )
        logger.info(
            f"  Parameter types: {[{name: {p.name: p.cls for p in info.parameters.values()} for name, info in param_classes.items()}]}"
        )
        logger.info(f"  Type errors: {analysis.get('type_errors', [])}")

        # Publish diagnostics for type errors
        self._publish_diagnostics(uri, analysis.get("type_errors", []))

    def _publish_diagnostics(self, uri: str, type_errors: list[TypeErrorDict]):
        """Publish diagnostics for type errors."""
        diagnostics = []

        for error in type_errors:
            severity = (
                DiagnosticSeverity.Error
                if error.get("severity") == "error"
                else DiagnosticSeverity.Warning
            )

            diagnostic = Diagnostic(
                range=Range(
                    start=Position(line=error["line"], character=error["col"]),
                    end=Position(line=error["end_line"], character=error["end_col"]),
                ),
                message=error["message"],
                severity=severity,
                code=error.get("code"),
                source="param-lsp",
            )
            diagnostics.append(diagnostic)

        # Publish diagnostics
        self.publish_diagnostics(uri, diagnostics)
