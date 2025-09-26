"""Base class for LSP server with interface for mixins."""

from __future__ import annotations

import inspect
from typing import Any
from urllib.parse import urlsplit

import param
from pygls.server import LanguageServer

from param_lsp.analyzer import ParamAnalyzer


class LSPServerBase(LanguageServer):
    """Base class defining the interface needed by mixins.

    This class provides the minimal interface that mixins expect,
    reducing the need for verbose type annotations in mixin methods.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.workspace_root: str | None = None
        self.analyzer = ParamAnalyzer()
        self.document_cache: dict[str, dict[str, Any]] = {}
        self.param_types = self._get_param_types()

    def _uri_to_path(self, uri: str) -> str:
        """Convert URI to file path."""
        return urlsplit(uri).path

    def _get_param_types(self) -> list[str]:
        """Get available Param parameter types."""

        # Get actual param types from the module
        param_types = []
        for name in dir(param):
            obj = getattr(param, name)
            if inspect.isclass(obj) and issubclass(obj, param.Parameter):
                param_types.append(name)
        return param_types

    def _get_python_type_name(self, param_type: str, allow_None: bool = False) -> str:
        """Map param type to Python type name for display using existing param_type_map."""
        if hasattr(self, "analyzer") and param_type in self.analyzer.param_type_map:
            python_types = self.analyzer.param_type_map[param_type]
            if isinstance(python_types, tuple):
                # Multiple types like (int, float) -> "int or float"
                type_names = [t.__name__ for t in python_types]
            else:
                # Single type like int -> "int"
                type_names = [python_types.__name__]

            # Add None if allow_None is True
            if allow_None:
                type_names.append("None")

            return " | ".join(type_names)

        # For unknown param types, just return the param type name
        base_type = param_type.lower()
        return f"{base_type} | None" if allow_None else base_type
