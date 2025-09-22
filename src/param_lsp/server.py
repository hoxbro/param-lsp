from __future__ import annotations

import inspect
import logging
import re
from typing import Any
from urllib.parse import urlparse

import param
from lsprotocol.types import (
    CompletionItem,
    CompletionItemKind,
    CompletionList,
    CompletionOptions,
    CompletionParams,
    Diagnostic,
    DiagnosticOptions,
    DiagnosticSeverity,
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
    TextDocumentSyncKind,
)
from pygls.server import LanguageServer

from .analyzer import ParamAnalyzer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ParamLanguageServer(LanguageServer):
    """Language Server for HoloViz Param."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.workspace_root: str | None = None
        self.analyzer = ParamAnalyzer()
        self.document_cache: dict[str, dict[str, Any]] = {}
        self.param_types = self._get_param_types()

    def _get_param_types(self) -> list[str]:
        """Get available Param parameter types."""

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
        file_path = self._uri_to_path(uri)

        # Update analyzer with workspace root if available
        if self.workspace_root and not self.analyzer.workspace_root:
            self.analyzer = ParamAnalyzer(self.workspace_root)

        analysis = self.analyzer.analyze_file(content, file_path)
        self.document_cache[uri] = {"content": content, "analysis": analysis}

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
        self.publish_diagnostics(uri, diagnostics)

    def _get_completions_for_param_class(self, line: str, character: int) -> list[CompletionItem]:
        """Get completions for param class attributes and methods."""

        # Add parameter types with enhanced documentation
        completions = []
        for param_type in self.param_types:
            documentation = f"Param parameter type: {param_type}"

            # Try to get actual documentation from param module
            if param:
                try:
                    param_class = getattr(param, param_type, None)
                    if param_class and hasattr(param_class, "__doc__") and param_class.__doc__:
                        # Extract first line of docstring for concise documentation
                        doc_lines = param_class.__doc__.strip().split("\n")
                        if doc_lines:
                            documentation = doc_lines[0].strip()
                except (AttributeError, TypeError):
                    pass

            completions.append(
                CompletionItem(
                    label=param_type,
                    kind=CompletionItemKind.Class,
                    detail=f"param.{param_type}",
                    documentation=documentation,
                )
            )

        # Add common parameter arguments with detailed documentation
        param_args = [
            ("default", "Default value for the parameter"),
            ("doc", "Documentation string describing the parameter"),
            ("label", "Human-readable name for the parameter"),
            ("precedence", "Numeric precedence for parameter ordering"),
            ("instantiate", "Whether to instantiate the default value per instance"),
            ("constant", "Whether the parameter value cannot be changed after construction"),
            ("readonly", "Whether the parameter value can be modified after construction"),
            ("allow_None", "Whether None is allowed as a valid value"),
            ("per_instance", "Whether the parameter is stored per instance"),
            ("bounds", "Tuple of (min, max) values for numeric parameters"),
            ("inclusive_bounds", "Tuple of (left_inclusive, right_inclusive) booleans"),
            ("softbounds", "Tuple of (soft_min, soft_max) for suggested ranges"),
        ]

        completions.extend(
            [
                CompletionItem(
                    label=arg_name,
                    kind=CompletionItemKind.Property,
                    detail="Parameter argument",
                    documentation=arg_doc,
                )
                for arg_name, arg_doc in param_args
            ]
        )

        return completions

    def _get_constructor_parameter_completions(
        self, uri: str, line: str, character: int
    ) -> list[CompletionItem]:
        """Get parameter completions for param class constructors like P(...)."""
        completions = []

        if uri not in self.document_cache:
            return completions

        analysis = self.document_cache[uri]["analysis"]
        param_classes = analysis.get("param_classes", set())
        param_parameters = analysis.get("param_parameters", {})
        param_parameter_types = analysis.get("param_parameter_types", {})
        param_parameter_docs = analysis.get("param_parameter_docs", {})
        param_parameter_bounds = analysis.get("param_parameter_bounds", {})
        param_parameter_allow_none = analysis.get("param_parameter_allow_none", {})
        param_parameter_defaults = analysis.get("param_parameter_defaults", {})

        # Find which param class constructor is being called
        # Look backwards in the line to find ClassName(
        before_cursor = line[:character]

        # Pattern: find word followed by opening parenthesis, allowing for parameters already typed
        # This pattern matches ClassName( with optional whitespace and existing parameters
        pattern = r"(\w+)\s*\([^)]*$"
        match = re.search(pattern, before_cursor)

        # Also check if we're inside parentheses after a class name
        # This helps catch cases where user has started typing parameter letters
        if not match:
            # Look for pattern like: ClassName(some_text
            pattern_inside = r"(\w+)\s*\([^)]*\w*$"
            match = re.search(pattern_inside, before_cursor)

        if match:
            class_name = match.group(1)

            # Check if this is a known param class
            if class_name in param_classes:
                parameters = param_parameters.get(class_name, [])
                parameter_types = param_parameter_types.get(class_name, {})
                parameter_docs = param_parameter_docs.get(class_name, {})
                parameter_bounds = param_parameter_bounds.get(class_name, {})
                parameter_allow_none = param_parameter_allow_none.get(class_name, {})
                parameter_defaults = param_parameter_defaults.get(class_name, {})

                # Find already used parameters to avoid duplicates
                used_params = set()
                param_pattern = r"(\w+)\s*="
                used_matches = re.findall(param_pattern, before_cursor)
                used_params.update(used_matches)

                for param_name in parameters:
                    # Skip parameters that are already used
                    if param_name in used_params:
                        continue
                    # Build documentation for the parameter
                    doc_parts = []

                    # Add parameter type info
                    param_type = parameter_types.get(param_name)
                    if param_type:
                        python_type = self._get_python_type_name(param_type)
                        doc_parts.append(f"Type: {param_type} ({python_type})")

                    # Add bounds info
                    bounds = parameter_bounds.get(param_name)
                    if bounds:
                        if len(bounds) == 2:
                            min_val, max_val = bounds
                            doc_parts.append(f"Bounds: [{min_val}, {max_val}]")
                        elif len(bounds) == 4:
                            min_val, max_val, left_inclusive, right_inclusive = bounds
                            left_bracket = "[" if left_inclusive else "("
                            right_bracket = "]" if right_inclusive else ")"
                            doc_parts.append(
                                f"Bounds: {left_bracket}{min_val}, {max_val}{right_bracket}"
                            )

                    # Add allow_None info
                    allow_none = parameter_allow_none.get(param_name, False)
                    if allow_none:
                        doc_parts.append("Allows None")

                    # Add parameter-specific documentation
                    param_doc = parameter_docs.get(param_name)
                    if param_doc:
                        doc_parts.append(f"Description: {param_doc}")

                    documentation = (
                        "\n".join(doc_parts) if doc_parts else f"Parameter of {class_name}"
                    )

                    # Create insert text with default value if available
                    default_value = parameter_defaults.get(param_name)
                    if default_value is not None:
                        insert_text = f"{param_name}={default_value}"
                        label = f"{param_name}={default_value}"
                    else:
                        insert_text = f"{param_name}="
                        label = param_name

                    completions.append(
                        CompletionItem(
                            label=label,
                            kind=CompletionItemKind.Property,
                            detail=f"Parameter of {class_name}",
                            documentation=documentation,
                            insert_text=insert_text,
                            filter_text=param_name,  # Help with filtering
                            sort_text=f"{param_name:0>3}",  # Ensure stable sort order
                            preselect=False,  # Don't auto-select, show all options
                        )
                    )

        return completions

    def _get_python_type_name(self, param_type: str) -> str:
        """Map param type to Python type name for hover display using existing param_type_map."""
        if param_type in self.analyzer.param_type_map:
            python_types = self.analyzer.param_type_map[param_type]
            if isinstance(python_types, tuple):
                # Multiple types like (int, float) -> "int or float"
                type_names = [t.__name__ for t in python_types]
                return " or ".join(type_names)
            else:
                # Single type like int -> "int"
                return python_types.__name__
        return param_type.lower()

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
            param_parameters = analysis.get("param_parameters", {})
            param_parameter_types = analysis.get("param_parameter_types", {})
            param_parameter_docs = analysis.get("param_parameter_docs", {})
            param_parameter_bounds = analysis.get("param_parameter_bounds", {})

            for class_name, parameters in param_parameters.items():
                if word in parameters:
                    # Get parameter type information
                    param_type = param_parameter_types.get(class_name, {}).get(word)

                    if param_type:
                        hover_parts = [f"**{param_type} Parameter '{word}'**"]
                        # Map param types to Python types
                        python_type = self._get_python_type_name(param_type)
                        hover_parts.append(f"Allowed types: {python_type}")
                    else:
                        hover_parts = [f"**Parameter '{word}' in class '{class_name}'**"]

                    # Add bounds information
                    bounds = param_parameter_bounds.get(class_name, {}).get(word)
                    if bounds:
                        if len(bounds) == 2:
                            min_val, max_val = bounds
                            hover_parts.append(f"Bounds: `[{min_val}, {max_val}]`")
                        elif len(bounds) == 4:
                            min_val, max_val, left_inclusive, right_inclusive = bounds
                            left_bracket = "[" if left_inclusive else "("
                            right_bracket = "]" if right_inclusive else ")"
                            hover_parts.append(
                                f"Bounds: `{left_bracket}{min_val}, {max_val}{right_bracket}`"
                            )

                    # Add documentation
                    doc = param_parameter_docs.get(class_name, {}).get(word)
                    if doc:
                        hover_parts.append(f"\n{doc}")

                    return "\n\n".join(hover_parts)

        return None


server = ParamLanguageServer("param-lsp", "v0.1.0")


@server.feature("initialize")
def initialize(params: InitializeParams) -> InitializeResult:
    """Initialize the language server."""
    logger.info("Initializing Param LSP server")

    # Capture workspace root for cross-file analysis
    if params.workspace_folders and len(params.workspace_folders) > 0:
        workspace_uri = params.workspace_folders[0].uri
        server.workspace_root = server._uri_to_path(workspace_uri)
    elif params.root_uri:
        server.workspace_root = server._uri_to_path(params.root_uri)
    elif params.root_path:
        server.workspace_root = params.root_path

    logger.info(f"Workspace root: {server.workspace_root}")

    return InitializeResult(
        capabilities=ServerCapabilities(
            text_document_sync=TextDocumentSyncKind.Incremental,
            completion_provider=CompletionOptions(trigger_characters=[".", "=", "("]),
            hover_provider=True,
            diagnostic_provider=DiagnosticOptions(
                inter_file_dependencies=False, workspace_diagnostics=False
            ),
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
            if getattr(change, "range", None):
                # Handle incremental changes
                lines = content.split("\n")
                range_obj = change.range  # pyright: ignore[reportAttributeAccessIssue]
                start_line = range_obj.start.line
                start_char = range_obj.start.character
                end_line = range_obj.end.line
                end_char = range_obj.end.character

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

    # Check if we're in a constructor call context (e.g., P(...) )
    constructor_completions = server._get_constructor_parameter_completions(
        uri, current_line, position.character
    )
    if constructor_completions:
        # Mark as complete and ensure all items are visible
        completion_list = CompletionList(is_incomplete=False, items=constructor_completions)
        return completion_list

    # Get completions based on general context
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
