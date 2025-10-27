"""Base class for LSP server with interface for mixins."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from pygls.lsp.server import LanguageServer

from param_lsp.analyzer import ParamAnalyzer
from param_lsp.constants import PARAM_TYPE_MAP


class LSPServerBase(LanguageServer):
    """Base class defining the interface needed by mixins.

    This class provides the minimal interface that mixins expect,
    reducing the need for verbose type annotations in mixin methods.
    """

    def __init__(
        self, *args, python_env: Any = None, extra_libraries: set[str] | None = None, **kwargs
    ):
        """
        Initialize the LSP server.

        Args:
            python_env: PythonEnvironment instance for analyzing external libraries.
                       If None, uses the current Python environment.
            extra_libraries: Set of additional external library names to analyze.
        """
        super().__init__(*args, **kwargs)
        self.workspace_root: str | None = None
        self.python_env = python_env
        self.extra_libraries = extra_libraries if extra_libraries is not None else set()
        self.analyzer = ParamAnalyzer(python_env=python_env, extra_libraries=self.extra_libraries)
        self.document_cache: dict[str, dict[str, Any]] = {}
        self.classes = self._get_classes()

    def _uri_to_path(self, uri: str) -> str:
        """Convert URI to file path."""
        return urlsplit(uri).path

    def _get_classes(self) -> list[str]:
        """Get available Param parameter types from static analysis.

        Extracts parameter type names from all cached libraries (param, panel, holoviews).
        Returns simple class names (e.g., "String", "Integer") for completion and hover.
        """
        # Get all parameter types from cached libraries
        parameter_types = self.analyzer.external_inspector.get_all_parameter_types()

        # Extract simple class names from full paths
        # e.g., "param.String" -> "String", "panel.viewable.Children" -> "Children"
        classes = []
        seen = set()
        for full_path in parameter_types:
            class_name = full_path.split(".")[-1]
            if class_name not in seen:
                classes.append(class_name)
                seen.add(class_name)

        return sorted(classes)

    def _get_python_type_name(self, cls: str, allow_None: bool = False) -> str:
        """Map param type to Python type name for display using existing param_type_map."""
        if cls in PARAM_TYPE_MAP:
            python_types = PARAM_TYPE_MAP[cls]
            if isinstance(python_types, tuple):
                # Multiple types like ("builtins.int", "builtins.float") -> "int or float"
                type_names = [t.split(".")[-1] for t in python_types]
            else:
                # Single type like "builtins.int" -> "int"
                type_names = [python_types.split(".")[-1]]

            # Add None if allow_None is True
            if allow_None:
                type_names.append("None")

            return " | ".join(type_names)

        # For unknown param types, just return the param type name
        base_type = cls.lower()
        return f"{base_type} | None" if allow_None else base_type
