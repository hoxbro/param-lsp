from __future__ import annotations

import inspect
import logging
import re
import textwrap
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

from . import __version__
from .analyzer import ParamAnalyzer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Compiled regex patterns for performance
PARAM_DEPENDS_PATTERN = re.compile(r"^([^#]*?)@param\.depends\s*\(", re.MULTILINE)
CONSTRUCTOR_CALL_PATTERN = re.compile(r"(\w+)\s*\([^)]*$")
CONSTRUCTOR_CALL_INSIDE_PATTERN = re.compile(r"(\w+)\s*\([^)]*\w*$")
PARAM_ASSIGNMENT_PATTERN = re.compile(r"(\w+)\s*=")
CLASS_DEFINITION_PATTERN = re.compile(r"^class\s+(\w+)")
QUOTED_STRING_PATTERN = re.compile(r'["\']([^"\']+)["\']')


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
        match = CONSTRUCTOR_CALL_PATTERN.search(before_cursor)

        # Also check if we're inside parentheses after a class name
        # This helps catch cases where user has started typing parameter letters
        if not match:
            # Look for pattern like: ClassName(some_text
            match = CONSTRUCTOR_CALL_INSIDE_PATTERN.search(before_cursor)

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

                # Check if user has typed a specific parameter assignment like "x="
                specific_param_match = None
                for param_name in parameters:
                    param_assignment_match = re.search(
                        rf"\b{re.escape(param_name)}\s*=\s*$", before_cursor
                    )
                    if param_assignment_match:
                        specific_param_match = param_name
                        break

                if specific_param_match:
                    # User typed "param_name=", suggest only the default value for that parameter
                    param_name = specific_param_match
                    default_value = parameter_defaults.get(param_name)

                    if default_value is not None:
                        display_value = self._format_default_for_display(default_value)

                        # Build documentation for this specific parameter
                        doc_parts = []
                        param_type = parameter_types.get(param_name)
                        if param_type:
                            python_type = self._get_python_type_name(param_type)
                            doc_parts.append(f"Type: {param_type} ({python_type})")

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

                        allow_none = parameter_allow_none.get(param_name, False)
                        if allow_none:
                            doc_parts.append("Allows None")

                        param_doc = parameter_docs.get(param_name)
                        if param_doc:
                            doc_parts.append(f"Description: {param_doc}")

                        documentation = (
                            "\n".join(doc_parts) if doc_parts else f"Parameter of {class_name}"
                        )

                        completions.append(
                            CompletionItem(
                                label=f"{param_name}={display_value}",
                                kind=CompletionItemKind.Property,
                                detail=f"Default value for {param_name}",
                                documentation=documentation,
                                insert_text=display_value,
                                filter_text=param_name,
                                sort_text="0",  # Highest priority
                                preselect=True,  # Auto-select the default value
                            )
                        )
                else:
                    # Normal case - suggest all unused parameters
                    used_params = set()
                    used_matches = PARAM_ASSIGNMENT_PATTERN.findall(before_cursor)
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
                            display_value = self._format_default_for_display(default_value)
                            insert_text = f"{param_name}={display_value}"
                            label = f"{param_name}={display_value}"
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

    def _format_default_for_display(self, default_value: str) -> str:
        """Format default value for autocomplete display, removing unnecessary quotes."""
        # If it's a quoted string, remove the quotes for display
        if (
            default_value.startswith("'")
            and default_value.endswith("'")
            and len(default_value) >= 2
        ):
            return default_value[1:-1]  # Remove single quotes
        elif (
            default_value.startswith('"')
            and default_value.endswith('"')
            and len(default_value) >= 2
        ):
            return default_value[1:-1]  # Remove double quotes
        else:
            return default_value  # Return as-is for numbers, booleans, etc.

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

            # Check if it's a parameter in a local class
            param_parameters = analysis.get("param_parameters", {})
            param_parameter_types = analysis.get("param_parameter_types", {})
            param_parameter_docs = analysis.get("param_parameter_docs", {})
            param_parameter_bounds = analysis.get("param_parameter_bounds", {})

            for class_name, parameters in param_parameters.items():
                if word in parameters:
                    hover_info = self._build_parameter_hover_info(
                        word,
                        class_name,
                        param_parameter_types,
                        param_parameter_docs,
                        param_parameter_bounds,
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

    def _build_parameter_hover_info(
        self,
        param_name: str,
        class_name: str,
        param_parameter_types: dict,
        param_parameter_docs: dict,
        param_parameter_bounds: dict,
    ) -> str | None:
        """Build hover information for a local parameter."""
        param_type = param_parameter_types.get(class_name, {}).get(param_name)

        if param_type:
            hover_parts = [f"**{param_type} Parameter '{param_name}'**"]
            # Map param types to Python types
            python_type = self._get_python_type_name(param_type)
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

        # Add documentation at the bottom with proper formatting
        doc = param_parameter_docs.get(class_name, {}).get(param_name)
        if doc:
            # Clean and dedent the documentation
            clean_doc = textwrap.dedent(doc).strip()
            hover_parts.append(f"---\n{clean_doc}")

        return "\n\n".join(hover_parts)

    def _build_external_parameter_hover_info(
        self, param_name: str, class_name: str, class_info: dict
    ) -> str | None:
        """Build hover information for an external parameter."""
        param_type = class_info.get("parameter_types", {}).get(param_name)

        if param_type:
            hover_parts = [f"**{param_type} Parameter '{param_name}' (from {class_name})**"]
            # Map param types to Python types
            python_type = self._get_python_type_name(param_type)
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

        # Add allow_None information
        allow_none = class_info.get("parameter_allow_none", {}).get(param_name)
        if allow_none is not None:
            hover_parts.append(f"Allow None: `{allow_none}`")

        # Add documentation at the bottom with proper formatting
        doc = class_info.get("parameter_docs", {}).get(param_name)
        if doc:
            # Clean and dedent the documentation
            clean_doc = textwrap.dedent(doc).strip()
            hover_parts.append(f"---\n{clean_doc}")

        return "\n\n".join(hover_parts)

    def _get_param_depends_completions(
        self, uri: str, lines: list[str], position: Position
    ) -> list[CompletionItem]:
        """Get parameter completions for param.depends decorator."""
        if uri not in self.document_cache:
            return []

        # Check if we're in a param.depends decorator context
        if not self._is_in_param_depends_decorator(lines, position):
            return []

        # Find the class that contains this method
        containing_class = self._find_containing_class(lines, position.line)
        if not containing_class:
            return []

        analysis = self.document_cache[uri]["analysis"]
        param_parameters = analysis.get("param_parameters", {})
        param_parameter_types = analysis.get("param_parameter_types", {})
        param_parameter_docs = analysis.get("param_parameter_docs", {})

        completions = []

        # Get parameters from the containing class
        parameters = param_parameters.get(containing_class, [])
        parameter_types = param_parameter_types.get(containing_class, {})
        parameter_docs = param_parameter_docs.get(containing_class, {})

        # Find already used parameters to avoid duplicates
        used_params = self._extract_used_depends_parameters_multiline(lines, position)

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

            # Add parameter-specific documentation
            param_doc = parameter_docs.get(param_name)
            if param_doc:
                doc_parts.append(f"Description: {param_doc}")

            documentation = (
                "\n".join(doc_parts) if doc_parts else f"Parameter of {containing_class}"
            )

            # Create completion item with quoted string for param.depends
            completions.append(
                CompletionItem(
                    label=f'"{param_name}"',
                    kind=CompletionItemKind.Property,
                    detail=f"Parameter of {containing_class}",
                    documentation=documentation,
                    insert_text=f'"{param_name}"',
                    filter_text=param_name,  # Help with filtering
                    sort_text=f"{param_name:0>3}",  # Ensure stable sort order
                )
            )

        return completions

    def _is_in_param_depends_decorator(self, lines: list[str], position: Position) -> bool:
        """Check if the current position is inside a param.depends decorator."""
        # Look for @param.depends( pattern in current line or previous lines
        # Handle multi-line decorators
        for line_idx in range(max(0, position.line - 5), position.line + 1):
            if line_idx >= len(lines):
                continue
            line = lines[line_idx]

            # Check for @param.depends( pattern (regex automatically excludes commented cases)
            if PARAM_DEPENDS_PATTERN.search(line):
                # Check if we're still inside the parentheses
                if line_idx == position.line:
                    # Same line - check if cursor is after the opening parenthesis
                    match = PARAM_DEPENDS_PATTERN.search(line)
                    if match and position.character >= match.end():
                        # Check if parentheses are closed before cursor
                        text_before_cursor = line[: position.character]
                        open_parens = text_before_cursor.count("(")
                        close_parens = text_before_cursor.count(")")
                        if open_parens > close_parens:
                            return True
                else:
                    # Different line - check if parentheses are balanced from decorator to current position
                    decorator_line = line
                    total_open = decorator_line.count("(")
                    total_close = decorator_line.count(")")

                    # Check lines between decorator and current position
                    for check_line_idx in range(line_idx + 1, position.line + 1):
                        if check_line_idx >= len(lines):
                            break
                        check_line = lines[check_line_idx]
                        if check_line_idx == position.line:
                            # Only count up to cursor position on current line
                            check_line = check_line[: position.character]
                        total_open += check_line.count("(")
                        total_close += check_line.count(")")

                    if total_open > total_close:
                        return True

        return False

    def _find_containing_class(self, lines: list[str], current_line: int) -> str | None:
        """Find the class that contains the current line."""
        # Look backwards for class definition
        for line_idx in range(current_line, -1, -1):
            if line_idx >= len(lines):
                continue
            line = lines[line_idx].strip()

            # Look for class definition
            match = CLASS_DEFINITION_PATTERN.match(line)
            if match:
                class_name = match.group(1)
                return class_name

        return None

    def _extract_used_depends_parameters(self, line: str, character: int) -> set[str]:
        """Extract parameter names already used in the param.depends decorator."""
        used_params = set()

        # Get the text before cursor on the current line
        before_cursor = line[:character]

        # Look for quoted strings that represent parameter names
        # Pattern matches both single and double quoted strings
        matches = QUOTED_STRING_PATTERN.findall(before_cursor)

        for match in matches:
            used_params.add(match)

        return used_params

    def _extract_used_depends_parameters_multiline(
        self, lines: list[str], position: Position
    ) -> set[str]:
        """Extract parameter names already used in the param.depends decorator across multiple lines."""
        used_params = set()

        # Find the start of the param.depends decorator
        start_line = None
        for line_idx in range(max(0, position.line - 5), position.line + 1):
            if line_idx >= len(lines):
                continue
            line = lines[line_idx]
            if PARAM_DEPENDS_PATTERN.search(line):
                start_line = line_idx
                break

        if start_line is None:
            return used_params

        # Collect all text from decorator start to current position
        decorator_text = ""
        for line_idx in range(start_line, position.line + 1):
            if line_idx >= len(lines):
                break
            line = lines[line_idx]
            if line_idx == position.line:
                # Only include text up to cursor position on current line
                line = line[: position.character]
            decorator_text += line + " "

        # Look for quoted strings that represent parameter names
        matches = QUOTED_STRING_PATTERN.findall(decorator_text)

        for match in matches:
            used_params.add(match)

        return used_params


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
