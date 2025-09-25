"""Completion mixin for providing autocompletion functionality."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lsprotocol.types import CompletionItem, Position

    from .protocol import LSPServerProtocol

import param
from lsprotocol.types import CompletionItem, CompletionItemKind

# Compiled regex patterns for performance
PARAM_DEPENDS_PATTERN = re.compile(r"^([^#]*?)@param\.depends\s*\(", re.MULTILINE)
CONSTRUCTOR_CALL_PATTERN = re.compile(r"^([^#]*?)(\w+(?:\.\w+)*)\s*\([^)]*$", re.MULTILINE)
CONSTRUCTOR_CALL_INSIDE_PATTERN = re.compile(
    r"^([^#]*?)(\w+(?:\.\w+)*)\s*\([^)]*\w*$", re.MULTILINE
)
CONSTRUCTOR_PARAM_ASSIGNMENT_PATTERN = re.compile(r"\b(\w+)\s*=")
QUOTED_STRING_PATTERN = re.compile(r'["\']([^"\']+)["\']')
PARAM_ATTR_ACCESS_PATTERN = re.compile(
    r"^([^#]*?)(\w+(?:\.\w+)*)\s*(?:\([^)]*\))?\s*\.param\.?.*$", re.MULTILINE
)
PARAM_OBJECT_ATTR_ACCESS_PATTERN = re.compile(
    r"^([^#]*?)(\w+(?:\.\w+)*)\s*(?:\([^)]*\))?\s*\.param\.(\w+)\..*$", re.MULTILINE
)
REACTIVE_EXPRESSION_PATTERN = re.compile(
    r"^([^#]*?)(\w+(?:\.\w+)*)\s*(?:\([^)]*\))?\s*\.param\.(\w+)\.rx\..*$", re.MULTILINE
)
PARAM_UPDATE_PATTERN = re.compile(
    r"^([^#]*?)(\w+(?:\.\w+)*)\s*(?:\([^)]*\))?\s*\.param\.update\s*\([^)]*$", re.MULTILINE
)


class CompletionMixin:
    """Provides autocompletion functionality for the LSP server."""

    def _is_in_param_definition_context(
        self: LSPServerProtocol, line: str, character: int
    ) -> bool:
        """Check if we're in a parameter definition context like param.String("""
        before_cursor = line[:character]

        # Check for patterns like param.ParameterType(
        param_def_pattern = re.compile(r"param\.([A-Z]\w*)\s*\([^)]*$")
        match = param_def_pattern.search(before_cursor)

        if match:
            param_type = match.group(1)
            # Check if it's a valid param type
            return param_type in self.param_types

        return False

    def _get_completions_for_param_class(
        self: LSPServerProtocol, line: str, character: int
    ) -> list[CompletionItem]:
        """Get completions for param class attributes and methods."""

        # Only show param types when typing after "param."
        before_cursor = line[:character]
        if before_cursor.rstrip().endswith("param."):
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
            return completions

        # Show parameter arguments only when inside param.ParameterType(...)
        elif self._is_in_param_definition_context(line, character):
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

            return [
                CompletionItem(
                    label=arg_name,
                    kind=CompletionItemKind.Property,
                    detail="Parameter argument",
                    documentation=arg_doc,
                )
                for arg_name, arg_doc in param_args
            ]

        # Don't show any generic completions in other contexts
        return []

    def _is_in_constructor_context(
        self: LSPServerProtocol, uri: str, line: str, character: int
    ) -> bool:
        """Check if the cursor is in a param class constructor context."""
        if uri not in self.document_cache:
            return False

        analysis = self.document_cache[uri]["analysis"]
        param_classes = analysis.get("param_classes", set())

        # Find which param class constructor is being called
        before_cursor = line[:character]

        # Check both patterns for constructor detection
        match = CONSTRUCTOR_CALL_PATTERN.search(before_cursor)
        if not match:
            match = CONSTRUCTOR_CALL_INSIDE_PATTERN.search(before_cursor)

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
            external_class_info = analyzer.external_param_classes.get(full_class_path)
            if external_class_info is None and full_class_path:
                external_class_info = analyzer._analyze_external_class_ast(full_class_path)

            if external_class_info:
                return True

        return False

    def _get_constructor_parameter_completions(
        self: LSPServerProtocol, uri: str, line: str, character: int
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
        before_cursor = line[:character]

        # Pattern: find word followed by opening parenthesis
        match = CONSTRUCTOR_CALL_PATTERN.search(before_cursor)

        # Also check if we're inside parentheses after a class name
        if not match:
            match = CONSTRUCTOR_CALL_INSIDE_PATTERN.search(before_cursor)

        if match:
            class_name = match.group(2)

            # Get analyzer for external class resolution
            analyzer = self.document_cache[uri]["analyzer"]

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
                        rf"^([^#]*?){re.escape(param_name)}\s*=\s*$", before_cursor, re.MULTILINE
                    )
                    if param_assignment_match:
                        specific_param_match = param_name
                        break

                if specific_param_match:
                    # User typed "param_name=", suggest only the default value for that parameter
                    param_name = specific_param_match
                    default_value = parameter_defaults.get(param_name)

                    if default_value is not None:
                        param_type = parameter_types.get(param_name)
                        display_value = self._format_default_for_display(default_value, param_type)

                        # Build documentation for this specific parameter
                        documentation = self._build_parameter_documentation(
                            param_name,
                            class_name,
                            parameter_types,
                            parameter_docs,
                            parameter_bounds,
                            parameter_allow_none,
                            parameter_defaults,
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
                    used_matches = CONSTRUCTOR_PARAM_ASSIGNMENT_PATTERN.findall(before_cursor)
                    used_params.update(used_matches)

                    for param_name in parameters:
                        # Skip parameters that are already used
                        if param_name in used_params:
                            continue
                        # Skip the 'name' parameter as it's rarely set in constructors
                        if param_name == "name":
                            continue

                        # Build documentation for the parameter
                        documentation = self._build_parameter_documentation(
                            param_name,
                            class_name,
                            parameter_types,
                            parameter_docs,
                            parameter_bounds,
                            parameter_allow_none,
                            parameter_defaults,
                        )

                        # Create insert text with default value if available
                        default_value = parameter_defaults.get(param_name)
                        if default_value is not None:
                            param_type = parameter_types.get(param_name)
                            display_value = self._format_default_for_display(
                                default_value, param_type
                            )
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
            else:
                # Handle external param classes (e.g., hv.Curve)
                full_class_path = self._resolve_external_class_path(class_name, analyzer)
                external_class_info = analyzer.external_param_classes.get(full_class_path)

                if external_class_info is None and full_class_path:
                    external_class_info = analyzer._analyze_external_class_ast(full_class_path)

                if external_class_info:
                    parameters = external_class_info.get("parameters", [])
                    parameter_types = external_class_info.get("parameter_types", {})
                    parameter_docs = external_class_info.get("parameter_docs", {})
                    parameter_bounds = external_class_info.get("parameter_bounds", {})
                    parameter_allow_none = external_class_info.get("parameter_allow_none", {})
                    parameter_defaults = external_class_info.get("parameter_defaults", {})

                    used_params = set()
                    used_matches = CONSTRUCTOR_PARAM_ASSIGNMENT_PATTERN.findall(before_cursor)
                    used_params.update(used_matches)

                    for param_name in parameters:
                        if param_name in used_params or param_name == "name":
                            continue

                        # Build documentation for external parameter
                        documentation = self._build_parameter_documentation(
                            param_name,
                            full_class_path or class_name,
                            parameter_types,
                            parameter_docs,
                            parameter_bounds,
                            parameter_allow_none,
                            parameter_defaults,
                        )

                        # Create insert text with default value if available
                        default_value = parameter_defaults.get(param_name)
                        if default_value is not None:
                            param_type = parameter_types.get(param_name)
                            display_value = self._format_default_for_display(
                                default_value, param_type
                            )
                            insert_text = f"{param_name}={display_value}"
                            label = f"{param_name}={display_value}"
                        else:
                            insert_text = f"{param_name}="
                            label = param_name

                        completions.append(
                            CompletionItem(
                                label=label,
                                kind=CompletionItemKind.Property,
                                detail=f"Parameter of {full_class_path}",
                                documentation=documentation,
                                insert_text=insert_text,
                                filter_text=param_name,
                                sort_text=f"{param_name:0>3}",
                                preselect=False,
                            )
                        )

        return completions

    def _resolve_external_class_path(
        self: LSPServerProtocol, class_name: str, analyzer
    ) -> str | None:
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
        self: LSPServerProtocol, uri: str, lines: list[str], position: Position
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

        # Extract partial text being typed to filter completions
        partial_text = self._extract_partial_parameter_text(lines, position)

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

            # Build documentation for the parameter
            documentation = self._build_parameter_documentation(
                param_name,
                containing_class,
                parameter_types,
                parameter_docs,
                {},  # No bounds for depends
                {},  # No allow_none for depends
                {},  # No defaults for depends
            )

            # Create completion item with quoted string for param.depends
            completions.append(
                CompletionItem(
                    label=f'"{param_name}"',
                    kind=CompletionItemKind.Property,
                    detail=f"Parameter of {containing_class}",
                    documentation=documentation,
                    insert_text=f'"{param_name}"',
                    filter_text=param_name,
                    sort_text=f"{param_name:0>3}",
                )
            )

        return completions

    def _is_in_param_depends_decorator(
        self: LSPServerProtocol, lines: list[str], position: Position
    ) -> bool:
        """Check if the current position is inside a param.depends decorator."""
        # Look for @param.depends( pattern in current line or previous lines
        for line_idx in range(max(0, position.line - 5), position.line + 1):
            if line_idx >= len(lines):
                continue
            line = lines[line_idx]

            # Check for @param.depends( pattern
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

    def _extract_partial_parameter_text(
        self: LSPServerProtocol, lines: list[str], position: Position
    ) -> str:
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
        self: LSPServerProtocol, lines: list[str], position: Position
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

    def _extract_used_depends_parameters(
        self: LSPServerProtocol, line: str, character: int
    ) -> set[str]:
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

    def _get_param_attribute_completions(
        self: LSPServerProtocol, uri: str, line: str, character: int
    ) -> list[CompletionItem]:
        """Get parameter completions for param attribute access like P().param.x."""
        # Stub - implementation follows the same pattern as other completion methods
        return []

    def _get_param_object_attribute_completions(
        self: LSPServerProtocol, uri: str, line: str, character: int
    ) -> list[CompletionItem]:
        """Get attribute completions for Parameter objects like P().param.x.default."""
        # Stub - implementation follows the same pattern as other completion methods
        return []

    def _get_reactive_expression_completions(
        self: LSPServerProtocol, uri: str, line: str, character: int
    ) -> list[CompletionItem]:
        """Get method completions for reactive expressions like P().param.x.rx.method."""
        # Stub - implementation follows the same pattern as other completion methods
        return []

    def _get_param_update_completions(
        self: LSPServerProtocol, uri: str, line: str, character: int
    ) -> list[CompletionItem]:
        """Get parameter completions for obj.param.update() keyword arguments."""
        # Stub - implementation follows the same pattern as other completion methods
        return []
