"""Completion mixin for providing autocompletion functionality."""

from __future__ import annotations

import re
import textwrap
from typing import TYPE_CHECKING

import param
from lsprotocol.types import (
    CompletionItem,
    CompletionItemKind,
    InsertTextFormat,
    Position,
    Range,
    TextEdit,
)

from param_lsp import _treesitter
from param_lsp._treesitter.queries import find_classes
from param_lsp.constants import (
    COMMON_PARAMETER_ATTRIBUTES,
    CONTAINER_PARAMETER_TYPES,
    NUMERIC_PARAMETER_TYPES,
    PARAM_ARGS,
    PARAM_METHODS,
    PARAMETER_METHODS,
    RX_METHODS,
    RX_PROPERTIES,
    TYPE_SPECIFIC_PARAMETER_ATTRIBUTES,
)

from .base import LSPServerBase

if TYPE_CHECKING:
    from collections.abc import Sequence

    from lsprotocol.types import Position

    from param_lsp.models import ParameterInfo

# Compiled regex patterns for performance
_re_param_depends = re.compile(r"^([^#]*?)@param\.depends\s*\(", re.MULTILINE)
_re_constructor_call = re.compile(r"^([^#]*?)(\w+(?:\.\w+)*)\s*\([^)]*$", re.MULTILINE)
_re_constructor_call_inside = re.compile(r"^([^#]*?)(\w+(?:\.\w+)*)\s*\([^)]*\w*$", re.MULTILINE)
_re_constructor_param_assignment = re.compile(r"\b(\w+)\s*=")
_re_quoted_string = re.compile(r'["\']([^"\']+)["\']')
_re_param_attr_access = re.compile(
    r"^([^#]*?)(\w+(?:\.\w+)*)\s*(?:\([^)]*\))?\s*\.param\.?.*$", re.MULTILINE
)
_re_param_object_attr_access = re.compile(
    r"^([^#]*?)(\w+(?:\.\w+)*)\s*(?:\([^)]*\))?\s*\.param\.(\w+)\..*$", re.MULTILINE
)
_re_reactive_expression = re.compile(
    r"^([^#]*?)(\w+(?:\.\w+)*)\s*(?:\([^)]*\))?\s*\.param\.(\w+)\.rx\..*$", re.MULTILINE
)
_re_param_update = re.compile(
    r"^([^#]*?)(\w+(?:\.\w+)*)\s*(?:\([^)]*\))?\s*\.param\.update\s*\([^)]*$", re.MULTILINE
)
_re_param_dot = re.compile(r"\.param\.(\w*)$")


class CompletionMixin(LSPServerBase):
    """Provides autocompletion functionality for the LSP server."""

    def _is_in_param_definition_context(self, line: str, character: int) -> bool:
        """Check if we're in a parameter definition context like param.String("""
        before_cursor = line[:character]

        # Check for patterns like param.ParameterType(
        param_def_pattern = re.compile(r"param\.([A-Z]\w*)\s*\([^)]*$")
        match = param_def_pattern.search(before_cursor)

        if match:
            cls = match.group(1)
            # Check if it's a valid param type
            return cls in self.classes

        return False

    def _get_completions_for_param_class(self, line: str, character: int) -> list[CompletionItem]:
        """Get completions for param class attributes and methods."""

        # Only show param types when typing after "param."
        before_cursor = line[:character]
        if before_cursor.rstrip().endswith("param."):
            completions = []
            for cls in self.classes:
                documentation = f"Param parameter type: {cls}"

                # Try to get actual documentation from param module
                if param:
                    try:
                        param_class = getattr(param, cls, None)
                        if param_class and hasattr(param_class, "__doc__") and param_class.__doc__:
                            # Extract first line of docstring for concise documentation
                            doc_lines = param_class.__doc__.strip().split("\n")
                            if doc_lines:
                                documentation = doc_lines[0].strip()
                    except (AttributeError, TypeError):
                        pass

                completions.append(
                    CompletionItem(
                        label=cls,
                        kind=CompletionItemKind.Class,
                        detail=f"param.{cls}",
                        documentation=documentation,
                    )
                )
            return completions

        # Show parameter arguments only when inside param.ParameterType(...)
        elif self._is_in_param_definition_context(line, character):
            return [
                CompletionItem(
                    label=arg_name,
                    kind=CompletionItemKind.Property,
                    detail="Parameter argument",
                    documentation=arg_doc,
                )
                for arg_name, arg_doc in PARAM_ARGS
            ]

        # Don't show any generic completions in other contexts
        return []

    def _is_in_constructor_context(self, uri: str, line: str, character: int) -> bool:
        """Check if the cursor is in a param class constructor context."""
        if uri not in self.document_cache:
            return False

        analysis = self.document_cache[uri]["analysis"]
        param_classes = set(analysis.get("param_classes", {}).keys())

        # Find which param class constructor is being called
        before_cursor = line[:character]

        # Check both patterns for constructor detection
        match = _re_constructor_call.search(before_cursor)
        if not match:
            match = _re_constructor_call_inside.search(before_cursor)

        if match:
            class_name = match.group(2)

            # Check if this is a known param class
            if class_name in param_classes:
                return True

            # Check if this is an external param class
            analyzer = self.document_cache[uri]["analyzer"]

            # Resolve the full class path using import aliases
            full_class_path = None
            if "." in class_name:
                # Handle dotted names like hv.Curve
                parts = class_name.split(".")
                if len(parts) >= 2:
                    alias = parts[0]
                    class_part = ".".join(parts[1:])
                    if alias in analyzer.imports:
                        full_module = analyzer.imports[alias]
                        full_class_path = f"{full_module}.{class_part}"
                    else:
                        full_class_path = class_name
            else:
                # Simple class name - check if it's in external classes directly
                full_class_path = class_name

            # Check if this resolved class is in external_param_classes
            class_info = analyzer._analyze_external_class_ast(full_class_path)

            if class_info:
                return True

        return False

    def _is_in_constructor_context_multiline(
        self, uri: str, lines: Sequence[str], position: Position
    ) -> tuple[bool, str | None]:
        """Check if the cursor is in a param class constructor context across multiple lines.

        Returns (is_in_context, class_name) where class_name is the constructor being called.
        """
        if uri not in self.document_cache:
            return False, None

        analysis = self.document_cache[uri]["analysis"]
        param_classes = set(analysis.get("param_classes", {}).keys())
        analyzer = self.document_cache[uri]["analyzer"]

        # Look backwards from current position to find constructor call (max 10 lines)
        for line_idx in range(position.line, max(-1, position.line - 10), -1):
            if line_idx >= len(lines):
                continue
            line = lines[line_idx]

            # Check if this line has a constructor call
            match = _re_constructor_call.search(line)
            if not match:
                match = _re_constructor_call_inside.search(line)

            if match:
                class_name = match.group(2)

                # Verify this is a param class first
                if not self._is_param_class(class_name, param_classes, analyzer):
                    continue

                # Count parentheses from constructor line to current position
                total_open = line.count("(")
                total_close = line.count(")")

                # Count parentheses in lines between constructor and current position
                for check_idx in range(line_idx + 1, position.line + 1):
                    if check_idx >= len(lines):
                        break
                    check_line = lines[check_idx]
                    if check_idx == position.line:
                        # Only count up to cursor position on current line
                        check_line = check_line[: position.character]
                    total_open += check_line.count("(")
                    total_close += check_line.count(")")

                # If we have unbalanced parentheses (more open than close), we're inside
                if total_open > total_close:
                    return True, class_name

        return False, None

    def _is_param_class(self, class_name: str, param_classes: set, analyzer) -> bool:
        """Helper to check if a class is a param class."""
        # Check if this is a known param class
        if class_name in param_classes:
            return True

        # Check if this is an external param class
        full_class_path = self._resolve_external_class_path(class_name, analyzer)
        class_info = analyzer._analyze_external_class_ast(full_class_path)

        return class_info is not None

    def _get_constructor_parameter_completions(
        self, uri: str, line: str, position: Position
    ) -> list[CompletionItem]:
        """Get parameter completions for param class constructors like P(...)."""
        if uri not in self.document_cache:
            return []

        # Find which param class constructor is being called
        class_name = self._find_constructor_class_name(line, position.character)
        if not class_name:
            return []

        # Get class info (local or external)
        analysis = self.document_cache[uri]["analysis"]
        param_classes_dict = analysis.get("param_classes", {})
        analyzer = self.document_cache[uri]["analyzer"]
        class_info = self._get_class_info(class_name, param_classes_dict, analyzer)

        if not class_info:
            return []

        # Determine completion context and generate appropriate completions
        before_cursor = line[: position.character]
        return self._get_completions_by_context(before_cursor, class_info, class_name, position)

    def _find_constructor_class_name(self, line: str, character: int) -> str | None:
        """Find the class name being constructed from the line text."""
        before_cursor = line[:character]

        # Pattern: find word followed by opening parenthesis
        match = _re_constructor_call.search(before_cursor)

        # Also check if we're inside parentheses after a class name
        if not match:
            match = _re_constructor_call_inside.search(before_cursor)

        return match.group(2) if match else None

    def _get_completions_by_context(
        self, before_cursor: str, class_info, class_name: str, position: Position
    ) -> list[CompletionItem]:
        """Generate completions based on the current typing context."""
        parameters = class_info.get_parameter_names()

        # Check for exact parameter match (e.g., "width=")
        exact_match = self._find_exact_parameter_match(before_cursor, parameters)
        if exact_match:
            return self._create_exact_match_completions(exact_match, class_info, class_name)

        # Check for partial parameter match (e.g., "w=")
        partial_match, partial_info = self._find_partial_parameter_match(before_cursor, parameters)
        if partial_match and partial_info:
            return self._create_partial_match_completions(
                partial_match, partial_info, class_info, class_name, position
            )

        # Default: suggest all unused parameters
        return self._create_normal_parameter_completions(before_cursor, class_info, class_name)

    def _find_exact_parameter_match(self, before_cursor: str, parameters: list[str]) -> str | None:
        """Check if user has typed an exact parameter assignment like 'width='."""
        for param_name in parameters:
            param_assignment_match = re.search(
                rf"^([^#]*?){re.escape(param_name)}\s*=\s*$", before_cursor, re.MULTILINE
            )
            if param_assignment_match:
                return param_name
        return None

    def _find_partial_parameter_match(
        self, before_cursor: str, parameters: list[str]
    ) -> tuple[str | None, dict | None]:
        """Check if user has typed a partial parameter assignment like 'w='."""
        partial_assignment_match = re.search(r"\b(\w+)\s*=\s*$", before_cursor)
        if not partial_assignment_match:
            return None, None

        partial_text = partial_assignment_match.group(1)
        partial_match_start = partial_assignment_match.start(1)

        # Find parameter that starts with this partial text
        for param_name in parameters:
            if param_name.startswith(partial_text) and param_name != partial_text:
                return param_name, {
                    "partial_text": partial_text,
                    "partial_match_start": partial_match_start,
                }

        return None, None

    def _create_exact_match_completions(
        self, param_name: str, class_info, class_name: str
    ) -> list[CompletionItem]:
        """Create completion for exact parameter match (suggests default value)."""
        param_info = class_info.parameters.get(param_name)

        if not param_info or param_info.default is None:
            return []

        default_value = param_info.default
        cls = param_info.cls
        display_value = self._format_default_for_display(default_value, cls)
        documentation = self._build_parameter_documentation(param_info, class_name)

        return [
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
        ]

    def _create_partial_match_completions(
        self, param_name: str, partial_info: dict, class_info, class_name: str, position: Position
    ) -> list[CompletionItem]:
        """Create completion for partial parameter match (replaces partial text)."""
        param_info = class_info.parameters.get(param_name)
        if not param_info:
            return []

        # Calculate text replacement range
        partial_match_start = partial_info["partial_match_start"]
        character = position.character
        # For single-line completions, replace_start is just the partial match start
        replace_start = partial_match_start
        replace_end = character

        # Create TextEdit to replace the partial text
        from lsprotocol.types import Position as LSPPosition

        if param_info.default is not None:
            # Parameter with default value
            default_value = param_info.default
            cls = param_info.cls
            display_value = self._format_default_for_display(default_value, cls)
            new_text = f"{param_name}={display_value}"
            label = f"{param_name}={display_value}"
        else:
            # Parameter without default value
            new_text = f"{param_name}="
            label = param_name

        text_edit = TextEdit(
            range=Range(
                start=LSPPosition(line=position.line, character=replace_start),
                end=LSPPosition(line=position.line, character=replace_end),
            ),
            new_text=new_text,
        )

        documentation = self._build_parameter_documentation(param_info, class_name)

        return [
            CompletionItem(
                label=label,
                kind=CompletionItemKind.Property,
                detail=f"Complete parameter for {param_name}",
                documentation=documentation,
                text_edit=text_edit,
                filter_text=param_name,
                sort_text="0",  # Highest priority
                preselect=True,  # Auto-select the completion
            )
        ]

    def _create_normal_parameter_completions(
        self, before_cursor: str, class_info, class_name: str
    ) -> list[CompletionItem]:
        """Create completions for all unused parameters (normal case)."""
        # Find already used parameters
        used_params = set(_re_constructor_param_assignment.findall(before_cursor))

        completions = []
        for param_name in class_info.get_parameter_names():
            # Skip parameters that are already used or should be filtered
            if param_name in used_params or param_name == "name":
                continue

            param_info = class_info.parameters.get(param_name)
            if not param_info:
                continue

            # Build documentation and completion item
            documentation = self._build_parameter_documentation(param_info, class_name)

            # Create insert text with default value if available
            if param_info.default is not None:
                default_value = param_info.default
                cls = param_info.cls
                display_value = self._format_default_for_display(default_value, cls)
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
                    filter_text=param_name,
                    sort_text=f"{param_name:0>3}",
                    preselect=False,
                )
            )

        return completions

    def _get_constructor_parameter_completions_multiline(
        self, uri: str, lines: Sequence[str], position: Position, class_name: str
    ) -> list[CompletionItem]:
        """Get parameter completions for multiline param class constructors."""
        if uri not in self.document_cache:
            return []

        analysis = self.document_cache[uri]["analysis"]
        param_classes_dict = analysis.get("param_classes", {})
        analyzer = self.document_cache[uri]["analyzer"]

        # Get class info - reuse helper from single-line version
        class_info = self._get_class_info(class_name, param_classes_dict, analyzer)
        if not class_info:
            return []

        # Find used parameters by looking at recent lines
        used_params = self._find_used_parameters_simple(lines, position, class_name)

        # Generate completions for unused parameters
        return self._generate_parameter_completions(class_info, class_name, used_params)

    def _get_class_info(self, class_name: str, param_classes_dict: dict, analyzer):
        """Get class info for local or external param classes."""
        if class_name in param_classes_dict:
            return param_classes_dict[class_name]

        # Handle external param classes
        full_class_path = self._resolve_external_class_path(class_name, analyzer)
        class_info = analyzer._analyze_external_class_ast(full_class_path)
        return class_info

    def _find_used_parameters_simple(
        self, lines: Sequence[str], position: Position, class_name: str
    ) -> set[str]:
        """Find already used parameters in constructor with simple approach."""
        used_params = set()

        # First, find the constructor line
        constructor_line_idx = None
        for line_idx in range(position.line, max(-1, position.line - 10), -1):
            if line_idx >= len(lines):
                continue
            line = lines[line_idx]

            # Check if this line has a constructor call for our class
            match = _re_constructor_call.search(line)
            if not match:
                match = _re_constructor_call_inside.search(line)

            if match and match.group(2) == class_name:
                constructor_line_idx = line_idx
                break

        if constructor_line_idx is None:
            return used_params

        # Only look at lines from constructor onwards to current position
        for line_idx in range(constructor_line_idx, position.line + 1):
            if line_idx >= len(lines):
                continue
            line = lines[line_idx]
            if line_idx == position.line:
                line = line[: position.character]

            # Find parameter assignments in this line
            used_matches = _re_constructor_param_assignment.findall(line)
            used_params.update(used_matches)

        return used_params

    def _generate_parameter_completions(
        self, class_info, class_name: str, used_params: set
    ) -> list[CompletionItem]:
        """Generate completion items for unused parameters."""
        completions = []

        for param_name in class_info.get_parameter_names():
            # Skip parameters that are already used
            if param_name in used_params:
                continue
            # Skip the 'name' parameter as it's rarely set in constructors
            if param_name == "name":
                continue

            param_info = class_info.parameters.get(param_name)
            if not param_info:
                continue

            # Build documentation and completion item
            documentation = self._build_parameter_documentation(param_info, class_name)

            if param_info.default is not None:
                default_value = param_info.default
                cls = param_info.cls
                display_value = self._format_default_for_display(default_value, cls)
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
                    filter_text=param_name,
                    sort_text=f"{param_name:0>3}",
                    preselect=False,
                )
            )

        return completions

    def _resolve_external_class_path(self, class_name: str, analyzer) -> str | None:
        """Resolve external class path using import aliases."""
        if "." in class_name:
            # Handle dotted names like hv.Curve
            parts = class_name.split(".")
            if len(parts) >= 2:
                alias = parts[0]
                class_part = ".".join(parts[1:])
                if alias in analyzer.imports:
                    full_module = analyzer.imports[alias]
                    return f"{full_module}.{class_part}"
                else:
                    return class_name
        else:
            # Simple class name
            return class_name

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
        param_classes_dict = analysis.get("param_classes", {})

        completions = []

        # Get parameters from the containing class
        class_info = param_classes_dict.get(containing_class)
        if not class_info:
            return []

        parameters = class_info.get_parameter_names()

        # Find already used parameters to avoid duplicates
        used_params = self._extract_used_depends_parameters_multiline(lines, position)

        # Extract partial text being typed to filter completions
        partial_text = self._extract_partial_parameter_text(lines, position)

        # Check if we're inside an unclosed quote
        inside_quote = self._is_inside_quote(lines, position)

        for param_name in parameters:
            # Skip parameters that are already used
            if param_name in used_params:
                continue

            # Skip the 'name' parameter as it's rarely used in decorators
            if param_name == "name":
                continue

            # Filter based on partial text being typed
            if partial_text and not param_name.startswith(partial_text):
                continue

            param_info = class_info.parameters.get(param_name)
            if not param_info:
                continue

            # Build documentation for the parameter
            documentation = self._build_parameter_documentation(param_info, containing_class)

            # Adjust label and insert_text based on whether we're inside quotes
            if inside_quote:
                # User is inside an unclosed quote, just complete the parameter name
                label = param_name
                insert_text = param_name + '"'
            else:
                # User hasn't started typing a quote, provide full quoted string
                label = f'"{param_name}"'
                insert_text = f'"{param_name}"'

            # Create completion item with quoted string for param.depends
            completions.append(
                CompletionItem(
                    label=label,
                    kind=CompletionItemKind.Property,
                    detail=f"Parameter of {containing_class}",
                    documentation=documentation,
                    insert_text=insert_text,
                    filter_text=param_name,
                    sort_text=f"{param_name:0>3}",
                )
            )

        return completions

    def _is_in_param_depends_decorator(self, lines: list[str], position: Position) -> bool:
        """Check if the current position is inside a param.depends decorator."""
        # Look for @param.depends( pattern in current line or previous lines
        for line_idx in range(max(0, position.line - 5), position.line + 1):
            if line_idx >= len(lines):
                continue
            line = lines[line_idx]

            # Check for @param.depends( pattern
            if _re_param_depends.search(line):
                # Check if we're still inside the parentheses
                if line_idx == position.line:
                    # Same line - check if cursor is after the opening parenthesis
                    match = _re_param_depends.search(line)
                    if match and position.character >= match.end():
                        # Check if parentheses are closed before cursor
                        text_before_cursor = line[: position.character]
                        open_parens = text_before_cursor.count("(")
                        close_parens = text_before_cursor.count(")")
                        if open_parens > close_parens:
                            return True
                else:
                    # Different line - check if parentheses are balanced
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

    def _is_inside_quote(self, lines: list[str], position: Position) -> bool:
        """Check if the cursor is inside an unclosed quote."""
        if position.line >= len(lines):
            return False

        line = lines[position.line]
        text_before_cursor = line[: position.character]

        # Find all quote positions
        double_quotes = [m.start() for m in re.finditer(r'"', text_before_cursor)]
        single_quotes = [m.start() for m in re.finditer(r"'", text_before_cursor)]

        # Check for unclosed quote (odd number means unclosed)
        has_unclosed_double = bool(double_quotes) and len(double_quotes) % 2 == 1
        has_unclosed_single = bool(single_quotes) and len(single_quotes) % 2 == 1
        return has_unclosed_double or has_unclosed_single

    def _extract_partial_parameter_text(self, lines: list[str], position: Position) -> str:
        """Extract the partial parameter text being typed."""
        if position.line >= len(lines):
            return ""

        line = lines[position.line]
        text_before_cursor = line[: position.character]

        # Find all quote positions
        double_quotes = [m.start() for m in re.finditer(r'"', text_before_cursor)]
        single_quotes = [m.start() for m in re.finditer(r"'", text_before_cursor)]

        # Check for unclosed double quote
        if double_quotes and len(double_quotes) % 2 == 1:
            last_quote_pos = double_quotes[-1]
            return text_before_cursor[last_quote_pos + 1 :]

        # Check for unclosed single quote
        if single_quotes and len(single_quotes) % 2 == 1:
            last_quote_pos = single_quotes[-1]
            return text_before_cursor[last_quote_pos + 1 :]

        return ""

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
            if _re_param_depends.search(line):
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
        matches = _re_quoted_string.findall(decorator_text)

        for match in matches:
            used_params.add(match)

        return used_params

    def _extract_used_depends_parameters(self, line: str, character: int) -> set[str]:
        """Extract parameter names already used in the param.depends decorator."""
        used_params = set()

        # Get the text before cursor on the current line
        before_cursor = line[:character]

        # Look for quoted strings that represent parameter names
        # Pattern matches both single and double quoted strings
        matches = _re_quoted_string.findall(before_cursor)

        for match in matches:
            used_params.add(match)

        return used_params

    def _get_param_attribute_completions(
        self, uri: str, line: str, character: int
    ) -> list[CompletionItem]:
        """Get parameter completions for param attribute access like P().param.x."""
        completions = []

        if uri not in self.document_cache:
            return completions

        # Check if we're in a param attribute access context
        before_cursor = line[:character]
        match = _re_param_attr_access.search(before_cursor)

        if not match:
            return completions

        class_name = match.group(2)

        # Get analyzer for external class resolution
        analyzer = self.document_cache[uri]["analyzer"]
        analysis = self.document_cache[uri]["analysis"]
        param_classes_dict = analysis.get("param_classes", {})

        # Check if this is a known param class (local or external)
        class_info = None

        # First, try to resolve the class name (could be a variable or class name)
        resolved_class_name = self._resolve_class_name_from_context(
            uri, class_name, set(param_classes_dict.keys())
        )

        if resolved_class_name and resolved_class_name in param_classes_dict:
            # Local class
            class_info = param_classes_dict[resolved_class_name]
        else:
            # Check if it's an external param class or if resolved_class_name is external
            # Use resolved_class_name if available, otherwise fall back to class_name
            check_class_name = resolved_class_name if resolved_class_name else class_name
            full_class_path = None

            if "." in check_class_name:
                # Handle dotted names like hv.Curve
                parts = check_class_name.split(".")
                if len(parts) >= 2:
                    alias = parts[0]
                    class_part = ".".join(parts[1:])
                    if alias in analyzer.imports:
                        full_module = analyzer.imports[alias]
                        full_class_path = f"{full_module}.{class_part}"
                    else:
                        full_class_path = check_class_name
            else:
                # Simple class name - check if it's in external classes directly
                full_class_path = check_class_name

            # Check if this resolved class is in external_param_classes
            class_info = analyzer._analyze_external_class_ast(full_class_path)

        # If we don't have class_info, no completions
        if not class_info:
            return completions

        # Extract partial text being typed after ".param."
        partial_text = ""
        param_dot_match = _re_param_dot.search(before_cursor)
        if param_dot_match:
            partial_text = param_dot_match.group(1)

        # Add param namespace method completions (objects, values, update)
        for method in PARAM_METHODS:
            method_name = method["name"]
            # Filter based on partial text being typed
            if partial_text and not method_name.startswith(partial_text):
                continue

            # Determine if parentheses should be included in insert_text
            if self._should_include_parentheses_in_insert_text(line, character, method_name):
                insert_text = method["insert_text"]  # includes ()
            else:
                insert_text = method_name  # just the method name

            # Set snippet format for update method to position cursor inside parentheses
            insert_text_format = None
            if method_name == "update" and "$0" in insert_text:
                insert_text_format = InsertTextFormat.Snippet

            completions.append(
                CompletionItem(
                    label=method_name + "()",
                    kind=CompletionItemKind.Method,
                    detail=method["detail"],
                    documentation=method["documentation"],
                    insert_text=insert_text,
                    insert_text_format=insert_text_format,
                    filter_text=method_name,
                    sort_text=f"0_{method_name}",  # Sort methods before parameters
                )
            )

        # Create completion items for each parameter
        for param_name in class_info.get_parameter_names():
            # Filter based on partial text being typed
            if partial_text and not param_name.startswith(partial_text):
                continue

            param_info = class_info.parameters.get(param_name)
            if not param_info:
                continue

            # Build documentation for the parameter
            documentation = self._build_parameter_documentation(param_info, class_info.name)

            completions.append(
                CompletionItem(
                    label=param_name,
                    kind=CompletionItemKind.Property,
                    detail=f"Parameter of {class_name}",
                    documentation=documentation,
                    insert_text=param_name,
                    filter_text=param_name,
                    sort_text=f"{param_name:0>3}",
                )
            )

        return completions

    def _get_param_object_attribute_completions(
        self, uri: str, line: str, character: int
    ) -> list[CompletionItem]:
        """Get attribute completions for Parameter objects like P().param.x.default."""
        completions = []

        if uri not in self.document_cache:
            return completions

        # Check if we're in a Parameter object attribute access context
        before_cursor = line[:character]
        match = _re_param_object_attr_access.search(before_cursor)

        if not match:
            return completions

        class_name = match.group(2)
        param_name = match.group(3)

        # Resolve the class name (could be a variable or class name)
        analyzer = self.document_cache[uri]["analyzer"]
        analysis = self.document_cache[uri]["analysis"]
        param_classes_dict = analysis.get("param_classes", {})

        resolved_class_name = self._resolve_class_name_from_context(
            uri, class_name, set(param_classes_dict.keys())
        )

        # Check if this is a valid parameter of a known class
        class_info = None

        if resolved_class_name and resolved_class_name in param_classes_dict:
            # Local class
            class_info = param_classes_dict[resolved_class_name]
        else:
            # Check if it's an external param class
            check_class_name = resolved_class_name if resolved_class_name else class_name
            full_class_path = None

            if "." in check_class_name:
                # Handle dotted names like hv.Curve
                parts = check_class_name.split(".")
                if len(parts) >= 2:
                    alias = parts[0]
                    class_part = ".".join(parts[1:])
                    if alias in analyzer.imports:
                        full_module = analyzer.imports[alias]
                        full_class_path = f"{full_module}.{class_part}"
                    else:
                        full_class_path = check_class_name
            else:
                # Simple class name
                full_class_path = check_class_name

            class_info = analyzer._analyze_external_class_ast(full_class_path)

        # Check if param_name is a valid parameter
        if not class_info or param_name not in class_info.parameters:
            return completions

        # Get the parameter type to provide appropriate completions
        param_info = class_info.parameters[param_name]
        cls = param_info.cls or "Parameter"

        # Extract partial text being typed after the parameter name
        partial_text = ""
        param_attr_match = re.search(rf"\.{re.escape(param_name)}\.(\w*)$", before_cursor)
        if param_attr_match:
            partial_text = param_attr_match.group(1)

        # Type-specific attributes
        type_specific_attributes = {}

        if cls in NUMERIC_PARAMETER_TYPES:
            type_specific_attributes.update(TYPE_SPECIFIC_PARAMETER_ATTRIBUTES["numeric"])

        if cls == "String":
            type_specific_attributes.update(TYPE_SPECIFIC_PARAMETER_ATTRIBUTES["string"])

        if cls in CONTAINER_PARAMETER_TYPES:
            type_specific_attributes.update(TYPE_SPECIFIC_PARAMETER_ATTRIBUTES["container"])

        # Combine all available attributes
        all_attributes = {**COMMON_PARAMETER_ATTRIBUTES, **type_specific_attributes}

        # Add parameter methods
        for method_name, method_doc in PARAMETER_METHODS.items():
            # Filter based on partial text being typed
            if partial_text and not method_name.startswith(partial_text):
                continue

            # Determine if parentheses should be included in insert_text
            if self._should_include_parentheses_in_insert_text(line, character, method_name):
                insert_text = f"{method_name}()"
            else:
                insert_text = method_name

            completions.append(
                CompletionItem(
                    label=f"{method_name}()",
                    kind=CompletionItemKind.Method,
                    detail=f"Parameter.{method_name}()",
                    documentation=f"{method_doc}\n\nParameter type: {cls}",
                    insert_text=insert_text,
                    filter_text=method_name,
                    sort_text=f"0_{method_name}",  # Sort methods before properties
                )
            )

        # Create completion items for matching attributes
        for attr_name, attr_doc in all_attributes.items():
            # Filter based on partial text being typed
            if partial_text and not attr_name.startswith(partial_text):
                continue

            completions.append(
                CompletionItem(
                    label=attr_name,
                    kind=CompletionItemKind.Property,
                    detail=f"Parameter.{attr_name}",
                    documentation=f"{attr_doc}\n\nParameter type: {cls}",
                    insert_text=attr_name,
                    filter_text=attr_name,
                    sort_text=f"{attr_name:0>3}",
                )
            )

        return completions

    def _get_reactive_expression_completions(
        self, uri: str, line: str, character: int
    ) -> list[CompletionItem]:
        """Get method completions for reactive expressions like P().param.x.rx.method."""
        completions = []

        if uri not in self.document_cache:
            return completions

        # Check if we're in a reactive expression context
        before_cursor = line[:character]
        match = _re_reactive_expression.search(before_cursor)

        if not match:
            return completions

        class_name = match.group(2)
        param_name = match.group(3)

        # Resolve the class name (could be a variable or class name)
        analyzer = self.document_cache[uri]["analyzer"]
        analysis = self.document_cache[uri]["analysis"]
        param_classes_dict = analysis.get("param_classes", {})

        resolved_class_name = self._resolve_class_name_from_context(
            uri, class_name, set(param_classes_dict.keys())
        )

        # Check if this is a valid parameter of a known class
        class_info = None

        if resolved_class_name and resolved_class_name in param_classes_dict:
            # Local class
            class_info = param_classes_dict[resolved_class_name]
        else:
            # Check if it's an external param class
            check_class_name = resolved_class_name if resolved_class_name else class_name
            full_class_path = None

            if "." in check_class_name:
                # Handle dotted names like hv.Curve
                parts = check_class_name.split(".")
                if len(parts) >= 2:
                    alias = parts[0]
                    class_part = ".".join(parts[1:])
                    if alias in analyzer.imports:
                        full_module = analyzer.imports[alias]
                        full_class_path = f"{full_module}.{class_part}"
                    else:
                        full_class_path = check_class_name
            else:
                # Simple class name
                full_class_path = check_class_name

            class_info = analyzer._analyze_external_class_ast(full_class_path)

        # Check if param_name is a valid parameter
        if not class_info or param_name not in class_info.parameters:
            return completions

        # Extract partial text being typed after .rx.
        partial_text = ""
        rx_method_match = re.search(rf"\.{re.escape(param_name)}\.rx\.(\w*)$", before_cursor)
        if rx_method_match:
            partial_text = rx_method_match.group(1)

        # Add method completions
        for method_name, method_doc in RX_METHODS.items():
            # Filter based on partial text being typed
            if partial_text and not method_name.startswith(partial_text):
                continue

            # Determine if parentheses should be included in insert_text
            if self._should_include_parentheses_in_insert_text(line, character, method_name):
                insert_text = f"{method_name}()"
            else:
                insert_text = method_name

            completions.append(
                CompletionItem(
                    label=f"{method_name}()",
                    kind=CompletionItemKind.Method,
                    detail=f"rx.{method_name}",
                    documentation=f"{method_doc}\n\nReactive expression method for parameter '{param_name}'",
                    insert_text=insert_text,
                    filter_text=method_name,
                    sort_text=f"0_{method_name}",  # Sort methods first
                )
            )

        # Add property completions
        for prop_name, prop_doc in RX_PROPERTIES.items():
            # Filter based on partial text being typed
            if partial_text and not prop_name.startswith(partial_text):
                continue

            completions.append(
                CompletionItem(
                    label=prop_name,
                    kind=CompletionItemKind.Property,
                    detail=f"rx.{prop_name}",
                    documentation=f"{prop_doc}\n\nReactive expression property for parameter '{param_name}'",
                    insert_text=prop_name,
                    filter_text=prop_name,
                    sort_text=f"{prop_name:0>3}",
                )
            )

        return completions

    def _get_param_update_completions(
        self, uri: str, line: str, character: int
    ) -> list[CompletionItem]:
        """Get parameter completions for obj.param.update() keyword arguments."""
        completions = []

        if uri not in self.document_cache:
            return completions

        # Check if we're in a param.update() context
        before_cursor = line[:character]
        match = _re_param_update.search(before_cursor)

        if not match:
            return completions

        class_name = match.group(2)

        # Get analyzer for external class resolution
        analyzer = self.document_cache[uri]["analyzer"]
        analysis = self.document_cache[uri]["analysis"]
        param_classes_dict = analysis.get("param_classes", {})

        # Check if this is a known param class (local or external)
        class_info = None

        # First, try to resolve the class name (could be a variable or class name)
        resolved_class_name = self._resolve_class_name_from_context(
            uri, class_name, set(param_classes_dict.keys())
        )

        if resolved_class_name and resolved_class_name in param_classes_dict:
            # Local class
            class_info = param_classes_dict[resolved_class_name]
        else:
            # Check if it's an external param class
            check_class_name = resolved_class_name if resolved_class_name else class_name
            full_class_path = None

            if "." in check_class_name:
                # Handle dotted names like hv.Curve
                parts = check_class_name.split(".")
                if len(parts) >= 2:
                    alias = parts[0]
                    class_part = ".".join(parts[1:])
                    if alias in analyzer.imports:
                        full_module = analyzer.imports[alias]
                        full_class_path = f"{full_module}.{class_part}"
                    else:
                        full_class_path = check_class_name
            else:
                # Simple class name - check if it's in external classes directly
                full_class_path = check_class_name

            # Check if this resolved class is in external_param_classes
            class_info = analyzer._analyze_external_class_ast(full_class_path)

        # If we don't have class_info, no completions
        if not class_info:
            return completions

        # Extract used parameters to avoid duplicates (similar to constructor completions)
        used_params = set()
        used_matches = _re_constructor_param_assignment.findall(before_cursor)
        used_params.update(used_matches)

        # Create completion items for each parameter as keyword arguments
        for param_name in class_info.get_parameter_names():
            # Skip the 'name' parameter as it's rarely set in updates
            if param_name == "name":
                continue

            # Skip parameters that are already used
            if param_name in used_params:
                continue

            param_info = class_info.parameters.get(param_name)
            if not param_info:
                continue

            # Build documentation for the parameter
            documentation = self._build_parameter_documentation(param_info, class_info.name)

            # Create insert text with default value if available
            if param_info.default is not None:
                default_value = param_info.default
                cls = param_info.cls
                display_value = self._format_default_for_display(default_value, cls)
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
                    filter_text=param_name,
                    sort_text=f"{param_name:0>3}",
                    preselect=False,
                )
            )

        return completions

    def _format_default_for_display(self, default_value: str, cls: str | None = None) -> str:
        """Format default value for autocomplete display."""
        # Check if the default value is a string literal (regardless of parameter type)
        is_string_literal = False

        # If it's already quoted, it's a string literal
        if (
            default_value.startswith("'")
            and default_value.endswith("'")
            and len(default_value) >= 2
        ) or (
            default_value.startswith('"')
            and default_value.endswith('"')
            and len(default_value) >= 2
        ):
            is_string_literal = True
        # If it's not quoted but contains letters (not just numbers/symbols), it might be a string
        elif default_value not in ["None", "True", "False", "[]", "{}", "()"]:
            # Check if it looks like a string value (contains letters and isn't a number)
            try:
                # If it can be parsed as a number, it's not a string literal
                float(default_value)
            except ValueError:
                # Contains non-numeric characters, likely a string
                if any(c.isalpha() for c in default_value):
                    is_string_literal = True

        # For string literals, ensure they have double quotes
        if is_string_literal:
            # If it's already quoted, standardize to double quotes
            if (
                default_value.startswith("'")
                and default_value.endswith("'")
                and len(default_value) >= 2
            ):
                unquoted = default_value[1:-1]  # Remove single quotes
                return f'"{unquoted}"'  # Add double quotes
            elif (
                default_value.startswith('"')
                and default_value.endswith('"')
                and len(default_value) >= 2
            ):
                return default_value  # Already double-quoted, keep as-is
            else:
                # Not quoted, add double quotes
                return f'"{default_value}"'
        # For non-string values, remove quotes if present
        elif (
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

    def _resolve_class_name_from_context(
        self, uri: str, class_name: str, param_classes: set[str]
    ) -> str | None:
        """Resolve a class name from context, handling both direct class names and variable names."""
        # If it's already a known param class, return it
        if class_name in param_classes:
            return class_name

        # Use analyzer's new method if available
        if hasattr(self, "document_cache") and uri in self.document_cache:
            content = self.document_cache[uri]["content"]
            analyzer = self.document_cache[uri]["analyzer"]

            if hasattr(analyzer, "resolve_class_name_from_context"):
                return analyzer.resolve_class_name_from_context(class_name, param_classes, content)

        return None

    def _should_include_parentheses_in_insert_text(
        self, line: str, character: int, method_name: str
    ) -> bool:
        """Determine if parentheses should be included in insert_text for method completions.

        Returns False if:
        - The method is already followed by parentheses (e.g., obj.param.objects()CURSOR)
        - There are already parentheses after the cursor position
        """
        # Check if the method name with parentheses appears before the cursor
        before_cursor = line[:character]
        if f"{method_name}()" in before_cursor:
            return False

        # Check if there are parentheses immediately after the cursor
        after_cursor = line[character:].lstrip()
        return not after_cursor.startswith("()")

    def _build_parameter_documentation(self, param_info: ParameterInfo, class_name: str) -> str:
        """Build standardized parameter documentation from ParameterInfo dataclass."""
        doc_parts = []

        # Add parameter type info
        if param_info.cls:
            python_type = self._get_python_type_name(param_info.cls)
            doc_parts.append(f"Type: {param_info.cls} ({python_type})")

        # Add bounds info
        if param_info.bounds:
            bounds = param_info.bounds
            if len(bounds) == 2:
                # Simple format: (min, max)
                min_val, max_val = bounds
                doc_parts.append(f"Bounds: [{min_val}, {max_val}]")
            elif len(bounds) == 4:
                # Extended format: (min, max, left_inclusive, right_inclusive)
                min_val, max_val, left_inclusive, right_inclusive = bounds
                left_bracket = "[" if left_inclusive else "("
                right_bracket = "]" if right_inclusive else ")"
                doc_parts.append(f"Bounds: {left_bracket}{min_val}, {max_val}{right_bracket}")
            else:
                # Fallback for any other format
                doc_parts.append(f"Bounds: {bounds}")

        # Add description if available
        if param_info.doc:
            clean_doc = textwrap.dedent(param_info.doc).strip()
            doc_parts.append(f"Description: {clean_doc}")

        # Add allow_None info if not default
        if param_info.allow_None is not None and param_info.allow_None:
            doc_parts.append("Allows None: Yes")

        # Add default value info
        if param_info.default is not None:
            doc_parts.append(f"Default: {param_info.default}")

        return "\n".join(doc_parts) if doc_parts else f"Parameter of {class_name}"

    def _find_containing_class(self, lines: list[str], current_line: int) -> str | None:
        """Find the class that contains the current line using tree-sitter."""
        # Parse the document using tree-sitter
        content = "\n".join(lines)
        tree = _treesitter.parser.parse(content, error_recovery=True)

        # Find all classes using tree-sitter query
        class_matches = find_classes(tree.root_node)

        # Find the class that contains the current line
        # Tree-sitter line numbers are 0-indexed, matching our current_line parameter
        for class_node, captures in class_matches:
            # Check if current_line is within the class definition
            start_line = class_node.start_point[0]
            end_line = class_node.end_point[0]

            if start_line <= current_line <= end_line and captures.get("class_name"):
                # Get the class name from captures
                class_name = _treesitter.get_value(captures["class_name"])
                if class_name:
                    return class_name

        return None
