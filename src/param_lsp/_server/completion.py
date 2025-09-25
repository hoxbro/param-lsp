"""Completion mixin for providing autocompletion functionality."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import param
from lsprotocol.types import CompletionItem, CompletionItemKind, InsertTextFormat

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

# convert_to_legacy_format no longer needed in server code
from .base import LSPServerBase

if TYPE_CHECKING:
    from lsprotocol.types import Position

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
_re_class_definition = re.compile(r"^([^#]*?)class\s+(\w+)", re.MULTILINE)
_re_param_dot = re.compile(r"\.param\.(\w*)$")


class CompletionMixin(LSPServerBase):
    """Provides autocompletion functionality for the LSP server."""

    def _get_legacy_format_from_analysis(self, analysis):
        """Helper to convert analysis to legacy format for compatibility."""
        param_classes = analysis.get("param_classes", {})
        return {
            "param_classes": set(param_classes.keys()),
            "param_parameters": {
                name: info.get_parameter_names() for name, info in param_classes.items()
            },
            "param_parameter_types": {
                name: {p.name: p.param_type for p in info.parameters.values()}
                for name, info in param_classes.items()
            },
            "param_parameter_docs": {
                name: {p.name: p.doc for p in info.parameters.values() if p.doc is not None}
                for name, info in param_classes.items()
            },
            "param_parameter_bounds": {
                name: {p.name: p.bounds for p in info.parameters.values() if p.bounds}
                for name, info in param_classes.items()
            },
            "param_parameter_allow_none": {
                name: {p.name: p.allow_none for p in info.parameters.values()}
                for name, info in param_classes.items()
            },
            "param_parameter_defaults": {
                name: {p.name: p.default for p in info.parameters.values() if p.default}
                for name, info in param_classes.items()
            },
        }

    def _is_in_param_definition_context(self, line: str, character: int) -> bool:
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

    def _get_completions_for_param_class(self, line: str, character: int) -> list[CompletionItem]:
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
        legacy = self._get_legacy_format_from_analysis(analysis)
        param_classes = legacy["param_classes"]

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
            external_class_info = analyzer.external_param_classes.get(full_class_path)
            if external_class_info is None and full_class_path:
                external_class_info = analyzer._analyze_external_class_ast(full_class_path)

            if external_class_info:
                return True

        return False

    def _get_constructor_parameter_completions(
        self, uri: str, line: str, character: int
    ) -> list[CompletionItem]:
        """Get parameter completions for param class constructors like P(...)."""
        completions = []

        if uri not in self.document_cache:
            return completions

        analysis = self.document_cache[uri]["analysis"]
        legacy = self._get_legacy_format_from_analysis(analysis)
        param_classes = legacy["param_classes"]
        param_parameters = legacy["param_parameters"]
        param_parameter_types = legacy["param_parameter_types"]
        param_parameter_docs = legacy["param_parameter_docs"]
        param_parameter_bounds = legacy["param_parameter_bounds"]
        param_parameter_allow_none = legacy["param_parameter_allow_none"]
        param_parameter_defaults = legacy["param_parameter_defaults"]

        # Find which param class constructor is being called
        before_cursor = line[:character]

        # Pattern: find word followed by opening parenthesis
        match = _re_constructor_call.search(before_cursor)

        # Also check if we're inside parentheses after a class name
        if not match:
            match = _re_constructor_call_inside.search(before_cursor)

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
                    used_matches = _re_constructor_param_assignment.findall(before_cursor)
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
                    # External class info is already an ExternalClassInfo object from analyzer
                    legacy_format = external_class_info.to_legacy_dict()

                    parameters = legacy_format["parameters"]
                    parameter_types = legacy_format["parameter_types"]
                    parameter_docs = legacy_format["parameter_docs"]
                    parameter_bounds = legacy_format["parameter_bounds"]
                    parameter_allow_none = legacy_format["parameter_allow_none"]
                    parameter_defaults = legacy_format["parameter_defaults"]

                    used_params = set()
                    used_matches = _re_constructor_param_assignment.findall(before_cursor)
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
        legacy = self._get_legacy_format_from_analysis(analysis)
        param_parameters = legacy["param_parameters"]
        param_parameter_types = legacy["param_parameter_types"]
        param_parameter_docs = legacy["param_parameter_docs"]

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
        legacy = self._get_legacy_format_from_analysis(analysis)
        param_classes = legacy["param_classes"]
        param_parameters = legacy["param_parameters"]
        param_parameter_types = legacy["param_parameter_types"]
        param_parameter_docs = legacy["param_parameter_docs"]
        param_parameter_bounds = legacy["param_parameter_bounds"]
        param_parameter_allow_none = legacy["param_parameter_allow_none"]
        param_parameter_defaults = legacy["param_parameter_defaults"]

        # Check if this is a known param class (local or external)
        parameters = []
        parameter_types = {}
        parameter_docs = {}
        parameter_bounds = {}
        parameter_allow_none = {}
        parameter_defaults = {}

        # First, try to resolve the class name (could be a variable or class name)
        resolved_class_name = self._resolve_class_name_from_context(uri, class_name, param_classes)

        if resolved_class_name and resolved_class_name in param_classes:
            # Local class
            parameters = param_parameters.get(resolved_class_name, [])
            parameter_types = param_parameter_types.get(resolved_class_name, {})
            parameter_docs = param_parameter_docs.get(resolved_class_name, {})
            parameter_bounds = param_parameter_bounds.get(resolved_class_name, {})
            parameter_allow_none = param_parameter_allow_none.get(resolved_class_name, {})
            parameter_defaults = param_parameter_defaults.get(resolved_class_name, {})
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
            external_class_info = analyzer.external_param_classes.get(full_class_path)
            if external_class_info is None and full_class_path:
                external_class_info = analyzer._analyze_external_class_ast(full_class_path)

            if external_class_info:
                # External class info is already an ExternalClassInfo object from analyzer
                legacy_format = external_class_info.to_legacy_dict()

                parameters = legacy_format["parameters"]
                parameter_types = legacy_format["parameter_types"]
                parameter_docs = legacy_format["parameter_docs"]
                parameter_bounds = legacy_format["parameter_bounds"]
                parameter_allow_none = legacy_format["parameter_allow_none"]
                parameter_defaults = legacy_format["parameter_defaults"]

        # If we don't have any parameters, no completions
        if not parameters:
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
        for param_name in parameters:
            # Filter based on partial text being typed
            if partial_text and not param_name.startswith(partial_text):
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
                    doc_parts.append(f"Bounds: {left_bracket}{min_val}, {max_val}{right_bracket}")

            # Add allow_None info
            allow_none = parameter_allow_none.get(param_name, False)
            if allow_none:
                doc_parts.append("Allows None")

            # Add parameter-specific documentation
            param_doc = parameter_docs.get(param_name)
            if param_doc:
                doc_parts.append(f"Description: {param_doc}")

            # Add default value info
            default_value = parameter_defaults.get(param_name)
            if default_value:
                doc_parts.append(f"Default: {default_value}")

            documentation = "\n".join(doc_parts) if doc_parts else f"Parameter of {class_name}"

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
        legacy = self._get_legacy_format_from_analysis(analysis)
        param_classes = legacy["param_classes"]
        param_parameters = legacy["param_parameters"]
        param_parameter_types = legacy["param_parameter_types"]

        resolved_class_name = self._resolve_class_name_from_context(uri, class_name, param_classes)

        # Check if this is a valid parameter of a known class
        parameters = []
        parameter_types = {}

        if resolved_class_name and resolved_class_name in param_classes:
            # Local class
            parameters = param_parameters.get(resolved_class_name, [])
            parameter_types = param_parameter_types.get(resolved_class_name, {})
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

            external_class_info = analyzer.external_param_classes.get(full_class_path)
            if external_class_info is None and full_class_path:
                external_class_info = analyzer._analyze_external_class_ast(full_class_path)

            if external_class_info:
                parameters = external_class_info.get("parameters", [])
                parameter_types = external_class_info.get("parameter_types", {})

        # Check if param_name is a valid parameter
        if param_name not in parameters:
            return completions

        # Get the parameter type to provide appropriate completions
        param_type = parameter_types.get(param_name, "Parameter")

        # Extract partial text being typed after the parameter name
        partial_text = ""
        param_attr_match = re.search(rf"\.{re.escape(param_name)}\.(\w*)$", before_cursor)
        if param_attr_match:
            partial_text = param_attr_match.group(1)

        # Type-specific attributes
        type_specific_attributes = {}

        if param_type in NUMERIC_PARAMETER_TYPES:
            type_specific_attributes.update(TYPE_SPECIFIC_PARAMETER_ATTRIBUTES["numeric"])

        if param_type == "String":
            type_specific_attributes.update(TYPE_SPECIFIC_PARAMETER_ATTRIBUTES["string"])

        if param_type in CONTAINER_PARAMETER_TYPES:
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
                    documentation=f"{method_doc}\n\nParameter type: {param_type}",
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
                    documentation=f"{attr_doc}\n\nParameter type: {param_type}",
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
        legacy = self._get_legacy_format_from_analysis(analysis)
        param_classes = legacy["param_classes"]
        param_parameters = legacy["param_parameters"]

        resolved_class_name = self._resolve_class_name_from_context(uri, class_name, param_classes)

        # Check if this is a valid parameter of a known class
        parameters = []

        if resolved_class_name and resolved_class_name in param_classes:
            # Local class
            parameters = param_parameters.get(resolved_class_name, [])
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

            external_class_info = analyzer.external_param_classes.get(full_class_path)
            if external_class_info is None and full_class_path:
                external_class_info = analyzer._analyze_external_class_ast(full_class_path)

            if external_class_info:
                parameters = external_class_info.get("parameters", [])

        # Check if param_name is a valid parameter
        if param_name not in parameters:
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
        legacy = self._get_legacy_format_from_analysis(analysis)
        param_classes = legacy["param_classes"]
        param_parameters = legacy["param_parameters"]
        param_parameter_types = legacy["param_parameter_types"]
        param_parameter_docs = legacy["param_parameter_docs"]
        param_parameter_bounds = legacy["param_parameter_bounds"]
        param_parameter_allow_none = legacy["param_parameter_allow_none"]
        param_parameter_defaults = legacy["param_parameter_defaults"]

        # Check if this is a known param class (local or external)
        parameters = []
        parameter_types = {}
        parameter_docs = {}
        parameter_bounds = {}
        parameter_allow_none = {}
        parameter_defaults = {}

        # First, try to resolve the class name (could be a variable or class name)
        resolved_class_name = self._resolve_class_name_from_context(uri, class_name, param_classes)

        if resolved_class_name and resolved_class_name in param_classes:
            # Local class
            parameters = param_parameters.get(resolved_class_name, [])
            parameter_types = param_parameter_types.get(resolved_class_name, {})
            parameter_docs = param_parameter_docs.get(resolved_class_name, {})
            parameter_bounds = param_parameter_bounds.get(resolved_class_name, {})
            parameter_allow_none = param_parameter_allow_none.get(resolved_class_name, {})
            parameter_defaults = param_parameter_defaults.get(resolved_class_name, {})
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
            external_class_info = analyzer.external_param_classes.get(full_class_path)
            if external_class_info is None and full_class_path:
                external_class_info = analyzer._analyze_external_class_ast(full_class_path)

            if external_class_info:
                # External class info is already an ExternalClassInfo object from analyzer
                legacy_format = external_class_info.to_legacy_dict()

                parameters = legacy_format["parameters"]
                parameter_types = legacy_format["parameter_types"]
                parameter_docs = legacy_format["parameter_docs"]
                parameter_bounds = legacy_format["parameter_bounds"]
                parameter_allow_none = legacy_format["parameter_allow_none"]
                parameter_defaults = legacy_format["parameter_defaults"]

        # If we don't have any parameters, no completions
        if not parameters:
            return completions

        # Extract used parameters to avoid duplicates (similar to constructor completions)
        used_params = set()
        used_matches = _re_constructor_param_assignment.findall(before_cursor)
        used_params.update(used_matches)

        # Create completion items for each parameter as keyword arguments
        for param_name in parameters:
            # Skip the 'name' parameter as it's rarely set in updates
            if param_name == "name":
                continue

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
                    doc_parts.append(f"Bounds: {left_bracket}{min_val}, {max_val}{right_bracket}")

            # Add allow_None info
            allow_none = parameter_allow_none.get(param_name, False)
            if allow_none:
                doc_parts.append("Allows None")

            # Add parameter-specific documentation
            param_doc = parameter_docs.get(param_name)
            if param_doc:
                doc_parts.append(f"Description: {param_doc}")

            documentation = "\n".join(doc_parts) if doc_parts else f"Parameter of {class_name}"

            # Create insert text with default value if available
            default_value = parameter_defaults.get(param_name)
            if default_value is not None:
                param_type = parameter_types.get(param_name)
                display_value = self._format_default_for_display(default_value, param_type)
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

    def _format_default_for_display(
        self, default_value: str, param_type: str | None = None
    ) -> str:
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

    def _build_parameter_documentation(
        self,
        param_name: str,
        class_name: str,
        parameter_types: dict[str, str],
        parameter_docs: dict[str, str],
        parameter_bounds: dict[str, tuple],
        parameter_allow_none: dict[str, bool] | None = None,
        parameter_defaults: dict[str, str] | None = None,
    ) -> str:
        """Build standardized parameter documentation."""
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
                doc_parts.append(f"Bounds: {left_bracket}{min_val}, {max_val}{right_bracket}")

        # Add allow_None info
        if parameter_allow_none:
            allow_none = parameter_allow_none.get(param_name, False)
            if allow_none:
                doc_parts.append("Allows None")

        # Add parameter-specific documentation
        param_doc = parameter_docs.get(param_name)
        if param_doc:
            doc_parts.append(f"Description: {param_doc}")

        # Add default value info
        if parameter_defaults:
            default_value = parameter_defaults.get(param_name)
            if default_value:
                doc_parts.append(f"Default: {default_value}")

        return "\n".join(doc_parts) if doc_parts else f"Parameter of {class_name}"

    def _find_containing_class(self, lines: list[str], current_line: int) -> str | None:
        """Find the class that contains the current line."""

        # Look backwards for class definition
        for line_idx in range(current_line, -1, -1):
            if line_idx >= len(lines):
                continue
            line = lines[line_idx].strip()

            # Look for class definition
            match = _re_class_definition.match(line)
            if match:
                class_name = match.group(2)
                return class_name

        return None
