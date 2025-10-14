from __future__ import annotations

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

from param_lsp import __version__

from ._logging import get_logger
from ._server.completion import CompletionMixin
from ._server.hover import HoverMixin
from ._server.validation import ValidationMixin

logger = get_logger(__name__, "server")


class ParamLanguageServer(ValidationMixin, HoverMixin, CompletionMixin):
    """Language Server for HoloViz Param."""


def _initialize(server, params: InitializeParams) -> InitializeResult:
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


def _did_open(server, params: DidOpenTextDocumentParams):
    """Handle document open event."""
    uri = params.text_document.uri
    content = params.text_document.text
    server._analyze_document(uri, content)
    logger.info(f"Opened document: {uri}")


def _did_change(server, params: DidChangeTextDocumentParams):
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


def _completion(server, params: CompletionParams) -> CompletionList:
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
        uri, current_line, position
    )
    if constructor_completions:
        # Mark as complete and ensure all items are visible
        completion_list = CompletionList(is_incomplete=False, items=constructor_completions)
        return completion_list

    # Check if we're in a multiline constructor context
    is_multiline_constructor, class_name = server._is_in_constructor_context_multiline(
        uri, lines, position
    )
    if is_multiline_constructor and class_name:
        multiline_completions = server._get_constructor_parameter_completions_multiline(
            uri, lines, position, class_name
        )
        if multiline_completions:
            return CompletionList(is_incomplete=False, items=multiline_completions)

    # Check if we're in a constructor context but have no completions (all params used)
    # In this case, don't fall back to generic param completions
    single_line_constructor = server._is_in_constructor_context(
        uri, current_line, position.character
    )
    if single_line_constructor or is_multiline_constructor:
        return CompletionList(is_incomplete=False, items=[])

    # Get completions based on general context
    completions = server._get_completions_for_param_class(current_line, position.character)

    return CompletionList(is_incomplete=False, items=completions)


def _hover(server, params: HoverParams) -> Hover | None:
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


def create_server(python_env=None):
    """Create a Param Language Server instance.

    Args:
        python_env: PythonEnvironment instance for analyzing external libraries.
                   If None, uses the current Python environment.

    Returns:
        ParamLanguageServer instance
    """
    server = ParamLanguageServer("param-lsp", __version__, python_env=python_env)

    # Attach feature handlers
    server.feature("initialize")(lambda params: _initialize(server, params))
    server.feature("textDocument/didOpen")(lambda params: _did_open(server, params))
    server.feature("textDocument/didChange")(lambda params: _did_change(server, params))
    server.feature("textDocument/completion")(lambda params: _completion(server, params))
    server.feature("textDocument/hover")(lambda params: _hover(server, params))

    return server
