"""Validation mixin for diagnostics and error reporting."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from lsprotocol.types import Diagnostic, DiagnosticSeverity, Position, Range

from param_lsp.analyzer import ParamAnalyzer

from .base import LSPServerBase

if TYPE_CHECKING:
    from typing import Any

logger = logging.getLogger(__name__)


class ValidationMixin(LSPServerBase):
    """Provides validation and diagnostic functionality for the LSP server."""

    def _analyze_document(self, uri: str, content: str):
        """Analyze a document and cache the results."""
        file_path = urlparse(uri).path

        # Update analyzer with workspace root if available
        if (
            hasattr(self, "workspace_root")
            and self.workspace_root
            and hasattr(self, "analyzer")
            and not self.analyzer.workspace_root
        ):
            self.analyzer = ParamAnalyzer(self.workspace_root)

        analysis = self.analyzer.analyze_file(content, file_path)
        self.document_cache[uri] = {
            "content": content,
            "analysis": analysis,
            "analyzer": self.analyzer,
        }

        # Debug logging
        logger.info(f"Analysis results for {uri}:")
        logger.info(f"  Param classes: {analysis.get('param_classes', set())}")
        logger.info(f"  Parameters: {analysis.get('param_parameters', {})}")
        logger.info(f"  Parameter types: {analysis.get('param_parameter_types', {})}")
        logger.info(f"  Type errors: {analysis.get('type_errors', [])}")

        # Publish diagnostics for type errors
        self._publish_diagnostics(uri, analysis.get("type_errors", []))

    def _publish_diagnostics(self, uri: str, type_errors: list[dict[str, Any]]):
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
        if hasattr(self, "publish_diagnostics"):
            self.publish_diagnostics(uri, diagnostics)
