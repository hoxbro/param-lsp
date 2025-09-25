from __future__ import annotations

import inspect
import logging
import re
import textwrap
from typing import Any
from urllib.parse import urlparse

import param
from lsprotocol.types import (
    CompletionList,
    CompletionOptions,
    CompletionParams,
    DiagnosticOptions,
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

from param_lsp import __version__
from param_lsp.analyzer import ParamAnalyzer

from .completion import CompletionMixin
from .hover import HoverMixin
from .utils import ParamUtilsMixin
from .validation import ValidationMixin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ParamLanguageServer(
    ParamUtilsMixin, ValidationMixin, HoverMixin, CompletionMixin, LanguageServer
):
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

    def _get_hover_info(self, uri: str, line: str, word: str) -> str | None:
        """Get hover information for a word."""
        if uri in self.document_cache:
            analysis = self.document_cache[uri]["analysis"]

            # Check if it's the rx method in parameter context
            if word == "rx" and self._is_rx_method_context(line):
                return self._build_rx_method_hover_info()

            # Check if it's a param namespace method (values, objects)
            param_namespace_method_info = self._get_param_namespace_method_hover_info(line, word)
            if param_namespace_method_info:
                return param_namespace_method_info

            # Check if it's a reactive expression method
            rx_method_info = self._get_reactive_expression_method_hover_info(line, word)
            if rx_method_info:
                return rx_method_info

            # Check if it's a parameter type
            if word in self.param_types:
                if param:
                    param_class = getattr(param, word, None)
                    if param_class and hasattr(param_class, "__doc__"):
                        return param_class.__doc__
                return f"Param parameter type: {word}"

            # Check if it's a parameter in a local class
            param_parameters = analysis.get("param_parameters", {})
            param_parameter_types = analysis.get("param_parameter_types", {})
            param_parameter_docs = analysis.get("param_parameter_docs", {})
            param_parameter_bounds = analysis.get("param_parameter_bounds", {})
            param_parameter_allow_none = analysis.get("param_parameter_allow_none", {})
            param_parameter_locations = analysis.get("param_parameter_locations", {})

            for class_name, parameters in param_parameters.items():
                if word in parameters:
                    hover_info = self._build_parameter_hover_info(
                        word,
                        class_name,
                        param_parameter_types,
                        param_parameter_docs,
                        param_parameter_bounds,
                        param_parameter_allow_none,
                        param_parameter_locations,
                    )
                    if hover_info:
                        return hover_info

            # Check if it's a parameter in an external class
            analyzer = self.document_cache[uri]["analyzer"]
            for class_name, class_info in analyzer.external_param_classes.items():
                if class_info and word in class_info.get("parameters", []):
                    hover_info = self._build_external_parameter_hover_info(
                        word, class_name, class_info
                    )
                    if hover_info:
                        return hover_info

        return None

    def _get_param_namespace_method_hover_info(self, line: str, word: str) -> str | None:
        """Get hover information for param namespace methods like obj.param.values()."""
        # Check if we're in a param namespace method context
        if not re.search(r"\.param\.\w+\(", line):
            return None

        # Define param namespace methods with their documentation
        param_namespace_methods = {
            "values": {
                "signature": "values()",
                "description": "Returns a dictionary mapping parameter names to their current values for all parameters of this Parameterized object.",
                "example": "obj.param.values()\n# Output: {'x': 5, 'y': 'hello', 'z': True}",
                "returns": "Dict[str, Any] (actual parameter values)",
                "note": "Returns the actual current parameter values, not parameter names or objects",
            },
            "objects": {
                "signature": "objects()",
                "description": "Returns a dictionary mapping parameter names to their Parameter objects for all parameters of this Parameterized object.",
                "example": "obj.param.objects()\n# Output: {'x': Integer(default=5), 'y': String(default='hello'), 'z': Boolean(default=True)}",
                "returns": "Dict[str, Parameter] (parameter objects with metadata)",
                "note": "Returns the Parameter objects themselves (with metadata), not the current parameter values",
            },
            "update": {
                "signature": "update(**params)",
                "description": "Update multiple parameters at once by passing parameter names as keyword arguments.",
                "example": "obj.param.update(x=10, y='new_value')\n# Updates multiple parameters simultaneously",
                "returns": "None",
                "note": "Efficiently updates multiple parameters with validation and triggers watchers",
            },
        }

        if word in param_namespace_methods:
            method_info = param_namespace_methods[word]
            hover_parts = [
                f"**obj.param.{method_info['signature']}**",
                "",
                method_info["description"],
                "",
                f"**Returns**: `{method_info['returns']}`",
            ]

            hover_parts.extend(
                [
                    "",
                    "**Example**:",
                    "```python",
                    f"{method_info['example']}",
                    "```",
                ]
            )
            # Add note if present
            if "note" in method_info:
                hover_parts.extend(["", f"**Note**: {method_info['note']}"])
            return "\n".join(hover_parts)

        return None

    def _get_reactive_expression_method_hover_info(self, line: str, word: str) -> str | None:
        """Get hover information for reactive expression methods."""
        # Check if we're in a reactive expression context
        if not re.search(r"\.param\.\w+\.rx\.", line):
            return None

        # Define reactive expression methods with their documentation
        rx_methods_docs = {
            "and_": {
                "signature": "and_(other)",
                "description": "Returns a reactive expression that applies the `and` operator between this expression and another value.",
                "example": "param_rx.and_(other_value)",
            },
            "bool": {
                "signature": "bool()",
                "description": "Returns a reactive expression that applies the `bool()` function to this expression's value.",
                "example": "param_rx.bool()",
            },
            "in_": {
                "signature": "in_(container)",
                "description": "Returns a reactive expression that checks if this expression's value is in the given container.",
                "example": "param_rx.in_([1, 2, 3])",
            },
            "is_": {
                "signature": "is_(other)",
                "description": "Returns a reactive expression that checks object identity between this expression and another value using the `is` operator.",
                "example": "param_rx.is_(None)",
            },
            "is_not": {
                "signature": "is_not(other)",
                "description": "Returns a reactive expression that checks absence of object identity using the `is not` operator.",
                "example": "param_rx.is_not(None)",
            },
            "len": {
                "signature": "len()",
                "description": "Returns a reactive expression that applies the `len()` function to this expression's value.",
                "example": "param_rx.len()",
            },
            "map": {
                "signature": "map(func, *args, **kwargs)",
                "description": "Returns a reactive expression that maps a function over the collection items in this expression's value.",
                "example": "param_rx.map(lambda x: x * 2)",
            },
            "or_": {
                "signature": "or_(other)",
                "description": "Returns a reactive expression that applies the `or` operator between this expression and another value.",
                "example": "param_rx.or_(default_value)",
            },
            "pipe": {
                "signature": "pipe(func, *args, **kwargs)",
                "description": "Returns a reactive expression that pipes this expression's value into the given function.",
                "example": "param_rx.pipe(str.upper)",
            },
            "updating": {
                "signature": "updating()",
                "description": "Returns a boolean reactive expression indicating whether this expression is currently updating.",
                "example": "param_rx.updating()",
            },
            "when": {
                "signature": "when(*conditions)",
                "description": "Returns a reactive expression that only updates when the specified conditions are met.",
                "example": "param_rx.when(condition_rx)",
            },
            "where": {
                "signature": "where(condition, other)",
                "description": "Returns a reactive expression implementing a ternary conditional (like numpy.where).",
                "example": "param_rx.where(condition, true_value)",
            },
            "watch": {
                "signature": "watch(callback, onlychanged=True)",
                "description": "Triggers a side-effect callback when this reactive expression outputs a new event.",
                "example": "param_rx.watch(lambda x: print(f'Value changed to {x}'))",
            },
            "value": {
                "signature": "value",
                "description": "Property to get or set the current value of this reactive expression.",
                "example": "current_val = param_rx.value",
            },
        }

        if word in rx_methods_docs:
            method_info = rx_methods_docs[word]
            hover_parts = [
                f"**{method_info['signature']}**",
                "",
                method_info["description"],
                "",
                f"**Example**: `{method_info['example']}`",
            ]
            return "\n".join(hover_parts)

        return None

    def _build_parameter_hover_info(
        self,
        param_name: str,
        class_name: str,
        param_parameter_types: dict,
        param_parameter_docs: dict,
        param_parameter_bounds: dict,
        param_parameter_allow_none: dict | None = None,
        param_parameter_locations: dict | None = None,
    ) -> str | None:
        """Build hover information for a local parameter."""
        param_type = param_parameter_types.get(class_name, {}).get(param_name)

        if param_type:
            hover_parts = [f"**{param_type} Parameter '{param_name}'**"]
            # Check if None is allowed for this parameter
            allow_none = False
            if param_parameter_allow_none:
                allow_none = param_parameter_allow_none.get(class_name, {}).get(param_name, False)
            # Map param types to Python types, including None if allowed
            python_type = self._get_python_type_name(param_type, allow_none)
            hover_parts.append(f"Allowed types: {python_type}")
        else:
            hover_parts = [f"**Parameter '{param_name}' in class '{class_name}'**"]

        # Add bounds information
        bounds = param_parameter_bounds.get(class_name, {}).get(param_name)
        if bounds:
            if len(bounds) == 2:
                min_val, max_val = bounds
                hover_parts.append(f"Bounds: `[{min_val}, {max_val}]`")
            elif len(bounds) == 4:
                min_val, max_val, left_inclusive, right_inclusive = bounds
                left_bracket = "[" if left_inclusive else "("
                right_bracket = "]" if right_inclusive else ")"
                hover_parts.append(f"Bounds: `{left_bracket}{min_val}, {max_val}{right_bracket}`")

        # Add documentation first with title and separator
        doc = param_parameter_docs.get(class_name, {}).get(param_name)
        if doc:
            # Clean and dedent the documentation
            clean_doc = textwrap.dedent(doc).strip()
            hover_parts.append("---")
            hover_parts.append("Description:")
            hover_parts.append(clean_doc)

        # Add source location information after documentation
        if param_parameter_locations:
            location_info = param_parameter_locations.get(class_name, {}).get(param_name)
            if location_info and isinstance(location_info, dict):
                source_line = location_info.get("source")
                line_number = location_info.get("line")
                if source_line:
                    # Add separator line before definition
                    hover_parts.append("---")
                    # Show definition with or without line number
                    if line_number:
                        hover_parts.append(f"Definition (line {line_number}):")
                    else:
                        hover_parts.append("Definition:")
                    hover_parts.append(f"```python\n{source_line}\n```")

        return "\n\n".join(hover_parts)

    def _build_external_parameter_hover_info(
        self, param_name: str, class_name: str, class_info: dict
    ) -> str | None:
        """Build hover information for an external parameter."""
        param_type = class_info.get("parameter_types", {}).get(param_name)

        if param_type:
            hover_parts = [f"**{param_type} Parameter '{param_name}' (from {class_name})**"]
            # Check if None is allowed for this parameter
            allow_none = class_info.get("parameter_allow_none", {}).get(param_name, False)
            # Map param types to Python types, including None if allowed
            python_type = self._get_python_type_name(param_type, allow_none)
            hover_parts.append(f"Allowed types: {python_type}")
        else:
            hover_parts = [f"**Parameter '{param_name}' in external class '{class_name}'**"]

        # Add bounds information
        bounds = class_info.get("parameter_bounds", {}).get(param_name)
        if bounds:
            if len(bounds) == 2:
                min_val, max_val = bounds
                hover_parts.append(f"Bounds: `[{min_val}, {max_val}]`")
            elif len(bounds) == 4:
                min_val, max_val, left_inclusive, right_inclusive = bounds
                left_bracket = "[" if left_inclusive else "("
                right_bracket = "]" if right_inclusive else ")"
                hover_parts.append(f"Bounds: `{left_bracket}{min_val}, {max_val}{right_bracket}`")

        # Add documentation first with title and separator
        doc = class_info.get("parameter_docs", {}).get(param_name)
        if doc:
            # Clean and dedent the documentation
            clean_doc = textwrap.dedent(doc).strip()
            hover_parts.append("---")
            hover_parts.append("Description:")
            hover_parts.append(clean_doc)

        # Add source location information after documentation
        parameter_locations = class_info.get("parameter_locations", {})
        if parameter_locations:
            location_info = parameter_locations.get(param_name)
            if location_info and isinstance(location_info, dict):
                source_line = location_info.get("source")
                if source_line:
                    # Add separator line before definition
                    hover_parts.append("---")
                    hover_parts.append("Definition:")
                    hover_parts.append(f"```python\n{source_line}\n```")

        return "\n\n".join(hover_parts)


server = ParamLanguageServer("param-lsp", __version__)


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

                    # Get the text before the start position and after the end position
                    prefix = lines[start_line][:start_char]
                    suffix = lines[end_line][end_char:] if end_line < len(lines) else ""

                    # Remove lines from end_line down to start_line + 1 (but keep start_line)
                    for _ in range(end_line, start_line, -1):
                        if _ < len(lines):
                            del lines[_]

                    # Handle the replacement
                    if len(new_lines) == 1:
                        # Single line replacement
                        lines[start_line] = prefix + new_lines[0] + suffix
                    else:
                        # Multi-line replacement
                        lines[start_line] = prefix + new_lines[0]
                        # Insert middle lines
                        for i, new_line in enumerate(new_lines[1:-1], 1):
                            lines.insert(start_line + i, new_line)
                        # Add the last line with suffix
                        lines.insert(start_line + len(new_lines) - 1, new_lines[-1] + suffix)

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

    # Check if we're in a param.depends decorator context
    depends_completions = server._get_param_depends_completions(uri, lines, position)
    if depends_completions:
        return CompletionList(is_incomplete=False, items=depends_completions)

    # Check if we're in a param.update({}) context
    update_completions = server._get_param_update_completions(
        uri, current_line, position.character
    )
    if update_completions:
        return CompletionList(is_incomplete=False, items=update_completions)

    # Check if we're in a reactive expression context (e.g., P().param.x.rx.method)
    rx_completions = server._get_reactive_expression_completions(
        uri, current_line, position.character
    )
    if rx_completions:
        return CompletionList(is_incomplete=False, items=rx_completions)

    # Check if we're in a Parameter object attribute access context (e.g., P().param.x.default)
    param_obj_attr_completions = server._get_param_object_attribute_completions(
        uri, current_line, position.character
    )
    if param_obj_attr_completions:
        return CompletionList(is_incomplete=False, items=param_obj_attr_completions)

    # Check if we're in a param attribute access context (e.g., P().param.x)
    param_attr_completions = server._get_param_attribute_completions(
        uri, current_line, position.character
    )
    if param_attr_completions:
        return CompletionList(is_incomplete=False, items=param_attr_completions)

    # Check if we're in a constructor call context (e.g., P(...) )
    constructor_completions = server._get_constructor_parameter_completions(
        uri, current_line, position.character
    )
    if constructor_completions:
        # Mark as complete and ensure all items are visible
        completion_list = CompletionList(is_incomplete=False, items=constructor_completions)
        return completion_list

    # Check if we're in a constructor context but have no completions (all params used)
    # In this case, don't fall back to generic param completions
    if server._is_in_constructor_context(uri, current_line, position.character):
        return CompletionList(is_incomplete=False, items=[])

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
