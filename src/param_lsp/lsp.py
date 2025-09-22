"""
HoloViz Param Language Server Protocol implementation.
Provides IDE support for Param-based Python code including autocompletion,
hover information, and diagnostics.
"""

from __future__ import annotations

import ast
import inspect
import logging
from typing import Any
from urllib.parse import urlparse

# from pygls.protocol import LanguageServerProtocol
import param
from lsprotocol.types import (
    CompletionItem,
    CompletionItemKind,
    CompletionList,
    CompletionOptions,
    CompletionParams,
    # Diagnostic,
    # DiagnosticSeverity,
    DidChangeTextDocumentParams,
    DidOpenTextDocumentParams,
    Hover,
    HoverParams,
    InitializeParams,
    InitializeResult,
    MarkupContent,
    MarkupKind,
    Position,
    Range,
    ServerCapabilities,
    # TextDocumentPositionParams,
    TextDocumentSyncKind,
)
from pygls.server import LanguageServer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ParamAnalyzer:
    """Analyzes Python code for Param usage patterns."""

    def __init__(self):
        self.param_classes: set[str] = set()
        self.param_parameters: dict[str, list[str]] = {}
        self.imports: dict[str, str] = {}

    def analyze_file(self, content: str) -> dict[str, Any]:
        """Analyze a Python file for Param usage."""
        try:
            tree = ast.parse(content)
            self._reset_analysis()

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self._handle_import(node)
                elif isinstance(node, ast.ImportFrom):
                    self._handle_import_from(node)
                elif isinstance(node, ast.ClassDef):
                    self._handle_class_def(node)

            return {
                "param_classes": self.param_classes,
                "param_parameters": self.param_parameters,
                "imports": self.imports,
            }
        except SyntaxError as e:
            logger.error(f"Syntax error in file: {e}")
            return {}

    def _reset_analysis(self):
        """Reset analysis state."""
        self.param_classes.clear()
        self.param_parameters.clear()
        self.imports.clear()

    def _handle_import(self, node: ast.Import):
        """Handle 'import' statements."""
        for alias in node.names:
            self.imports[alias.asname or alias.name] = alias.name

    def _handle_import_from(self, node: ast.ImportFrom):
        """Handle 'from ... import ...' statements."""
        if node.module:
            for alias in node.names:
                imported_name = alias.asname or alias.name
                full_name = f"{node.module}.{alias.name}"
                self.imports[imported_name] = full_name

    def _handle_class_def(self, node: ast.ClassDef):
        """Handle class definitions that might inherit from param.Parameterized."""
        # Check if class inherits from param.Parameterized
        is_param_class = False
        for base in node.bases:
            if self._is_param_base(base):
                is_param_class = True
                break

        if is_param_class:
            self.param_classes.add(node.name)
            parameters = self._extract_parameters(node)
            self.param_parameters[node.name] = parameters

    def _is_param_base(self, base: ast.expr) -> bool:
        """Check if a base class is param.Parameterized or similar."""
        if isinstance(base, ast.Name):
            return base.id in ["Parameterized"] and "param" in self.imports
        elif isinstance(base, ast.Attribute) and isinstance(base.value, ast.Name):
            module = base.value.id
            return (module == "param" and base.attr == "Parameterized") or (
                module in self.imports
                and self.imports[module].endswith("param")
                and base.attr == "Parameterized"
            )
        return False

    def _extract_parameters(self, node: ast.ClassDef) -> list[str]:
        """Extract parameter definitions from a Param class."""
        parameters = []
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and self._is_parameter_assignment(item.value):
                        parameters.append(target.id)  # noqa: PERF401
        return parameters

    def _is_parameter_assignment(self, value: ast.expr) -> bool:
        """Check if an assignment looks like a parameter definition."""
        if isinstance(value, ast.Call):
            if isinstance(value.func, ast.Name):
                # Common param types
                param_types = {
                    "Parameter",
                    "Number",
                    "Integer",
                    "String",
                    "Boolean",
                    "List",
                    "Tuple",
                    "Dict",
                    "Array",
                    "DataFrame",
                    "Series",
                    "Range",
                    "Date",
                    "CalendarDate",
                    "Filename",
                    "Foldername",
                    "Path",
                    "Color",
                    "Composite",
                    "Dynamic",
                    "Event",
                    "Action",
                    "FileSelector",
                    "ListSelector",
                    "ObjectSelector",
                }
                return value.func.id in param_types
            elif isinstance(value.func, ast.Attribute):
                if isinstance(value.func.value, ast.Name):
                    module = value.func.value.id
                    return module == "param" or (
                        module in self.imports and "param" in self.imports[module]
                    )
        return False


class ParamLanguageServer(LanguageServer):
    """Language Server for HoloViz Param."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.analyzer = ParamAnalyzer()
        self.document_cache: dict[str, dict[str, Any]] = {}
        self.param_types = self._get_param_types()

    def _get_param_types(self) -> list[str]:
        """Get available Param parameter types."""
        if param is None:
            # Fallback list if param is not available
            return [
                "Parameter",
                "Number",
                "Integer",
                "String",
                "Boolean",
                "List",
                "Tuple",
                "Dict",
                "Array",
                "DataFrame",
                "Series",
                "Range",
                "Date",
                "CalendarDate",
                "Filename",
                "Foldername",
                "Path",
                "Color",
                "Composite",
                "Dynamic",
                "Event",
                "Action",
                "FileSelector",
                "ListSelector",
                "ObjectSelector",
            ]

        # Get actual param types from the module
        param_types = []
        for name in dir(param):
            obj = getattr(param, name)
            if inspect.isclass(obj) and issubclass(obj, param.Parameter):
                param_types.append(name)
        return param_types

    def _uri_to_path(self, uri: str) -> str:
        """Convert URI to file path."""
        parsed = urlparse(uri)
        return parsed.path

    def _analyze_document(self, uri: str, content: str):
        """Analyze a document and cache the results."""
        analysis = self.analyzer.analyze_file(content)
        self.document_cache[uri] = {"content": content, "analysis": analysis}

    def _get_completions_for_param_class(self, line: str, character: int) -> list[CompletionItem]:
        """Get completions for param class attributes and methods."""

        # Add parameter types
        completions = [
            CompletionItem(
                label=param_type,
                kind=CompletionItemKind.Class,
                detail=f"param.{param_type}",
                documentation=f"Param parameter type: {param_type}",
            )
            for param_type in self.param_types
        ]

        # Add common parameter arguments
        param_args = [
            "default",
            "doc",
            "label",
            "precedence",
            "instantiate",
            "constant",
            "readonly",
            "allow_None",
            "per_instance",
        ]

        completions.extend(
            [
                CompletionItem(
                    label=arg,
                    kind=CompletionItemKind.Property,
                    detail="Parameter argument",
                    documentation=f"Common parameter argument: {arg}",
                )
                for arg in param_args
            ]
        )

        return completions

    def _get_hover_info(self, uri: str, line: str, word: str) -> str | None:
        """Get hover information for a word."""
        if uri in self.document_cache:
            analysis = self.document_cache[uri]["analysis"]

            # Check if it's a parameter type
            if word in self.param_types:
                if param:
                    param_class = getattr(param, word, None)
                    if param_class and hasattr(param_class, "__doc__"):
                        return param_class.__doc__
                return f"Param parameter type: {word}"

            # Check if it's a parameter in a class
            for class_name, parameters in analysis.get("param_parameters", {}).items():
                if word in parameters:
                    return f"Parameter '{word}' in class '{class_name}'"

        return None


# Create the language server instance
server = ParamLanguageServer("param-lsp", "v0.1.0")


@server.feature("initialize")
def initialize(params: InitializeParams) -> InitializeResult:
    """Initialize the language server."""
    logger.info("Initializing Param LSP server")

    return InitializeResult(
        capabilities=ServerCapabilities(
            text_document_sync=TextDocumentSyncKind.Incremental,
            completion_provider=CompletionOptions(trigger_characters=[".", "=", "("]),
            hover_provider=True,
        )
    )


@server.feature("textDocument/didOpen")
def did_open(params: DidOpenTextDocumentParams):
    """Handle document open event."""
    uri = params.text_document.uri
    content = params.text_document.text
    server._analyze_document(uri, content)
    logger.info(f"Opened document: {uri}")


@server.feature("textDocument/didChange")
def did_change(params: DidChangeTextDocumentParams):
    """Handle document change event."""
    uri = params.text_document.uri

    # Apply changes to get updated content
    if uri in server.document_cache:
        content = server.document_cache[uri]["content"]
        for change in params.content_changes:
            if hasattr(change, "range") and change.range:
                # Handle incremental changes
                lines = content.split("\n")
                start_line = change.range.start.line
                start_char = change.range.start.character
                end_line = change.range.end.line
                end_char = change.range.end.character

                # Apply the change
                if start_line == end_line:
                    lines[start_line] = (
                        lines[start_line][:start_char] + change.text + lines[start_line][end_char:]
                    )
                else:
                    # Multi-line change
                    new_lines = change.text.split("\n")
                    lines[start_line] = lines[start_line][:start_char] + new_lines[0]
                    for i in range(start_line + 1, end_line + 1):
                        if i < len(lines):
                            del lines[start_line + 1]
                    if len(new_lines) > 1:
                        lines[start_line] += new_lines[-1] + lines[end_line][end_char:]
                        for i, new_line in enumerate(new_lines[1:-1], 1):
                            lines.insert(start_line + i, new_line)

                content = "\n".join(lines)
            else:
                # Full document change
                content = change.text

        server._analyze_document(uri, content)


@server.feature("textDocument/completion")
def completion(params: CompletionParams) -> CompletionList:
    """Provide completion suggestions."""
    uri = params.text_document.uri
    position = params.position

    if uri not in server.document_cache:
        return CompletionList(is_incomplete=False, items=[])

    content = server.document_cache[uri]["content"]
    lines = content.split("\n")

    if position.line >= len(lines):
        return CompletionList(is_incomplete=False, items=[])

    current_line = lines[position.line]

    # Get completions based on context
    completions = server._get_completions_for_param_class(current_line, position.character)

    return CompletionList(is_incomplete=False, items=completions)


@server.feature("textDocument/hover")
def hover(params: HoverParams) -> Hover | None:
    """Provide hover information."""
    uri = params.text_document.uri
    position = params.position

    if uri not in server.document_cache:
        return None

    content = server.document_cache[uri]["content"]
    lines = content.split("\n")

    if position.line >= len(lines):
        return None

    current_line = lines[position.line]

    # Extract word at position
    char = position.character
    if char >= len(current_line):
        return None

    # Find word boundaries
    start = char
    end = char

    while start > 0 and (current_line[start - 1].isalnum() or current_line[start - 1] == "_"):
        start -= 1
    while end < len(current_line) and (current_line[end].isalnum() or current_line[end] == "_"):
        end += 1

    if start == end:
        return None

    word = current_line[start:end]
    hover_info = server._get_hover_info(uri, current_line, word)

    if hover_info:
        return Hover(
            contents=MarkupContent(
                kind=MarkupKind.Markdown, value=f"```python\n{word}\n```\n\n{hover_info}"
            ),
            range=Range(
                start=Position(line=position.line, character=start),
                end=Position(line=position.line, character=end),
            ),
        )

    return None
