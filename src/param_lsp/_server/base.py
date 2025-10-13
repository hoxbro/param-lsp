"""Base class for LSP server with interface for mixins."""

from __future__ import annotations

import inspect
from typing import Any
from urllib.parse import urlsplit

import param
from pygls.server import LanguageServer

from param_lsp.analyzer import ParamAnalyzer
from param_lsp.constants import PARAM_TYPE_MAP


class LSPServerBase(LanguageServer):
    """Base class defining the interface needed by mixins.

    This class provides the minimal interface that mixins expect,
    reducing the need for verbose type annotations in mixin methods.
    """

    def __init__(self, *args, python_env: Any = None, **kwargs):
        """
        Initialize the LSP server.

        Args:
            python_env: PythonEnvironment instance for analyzing external libraries.
                       If None, uses the current Python environment.
        """
        super().__init__(*args, **kwargs)
        self.workspace_root: str | None = None
        self.python_env = python_env
        self.analyzer = ParamAnalyzer(python_env=python_env)
        self.document_cache: dict[str, dict[str, Any]] = {}
        self.classes = self._get_classes()

    def _uri_to_path(self, uri: str) -> str:
        """Convert URI to file path."""
        return urlsplit(uri).path

    def _get_classes(self) -> list[str]:
        """Get available Param parameter types."""

        # Get actual param types from the module
        classes = []
        for name in dir(param):
            obj = getattr(param, name)
            if inspect.isclass(obj) and issubclass(obj, param.Parameter):
                classes.append(name)
        return classes

    def _get_python_type_name(self, cls: str, allow_None: bool = False) -> str:
        """Map param type to Python type name for display using existing param_type_map."""
        if cls in PARAM_TYPE_MAP:
            python_types = PARAM_TYPE_MAP[cls]
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
        base_type = cls.lower()
        return f"{base_type} | None" if allow_None else base_type
