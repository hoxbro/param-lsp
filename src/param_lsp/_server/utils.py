"""Utility mixin for shared functionality across LSP features."""

from __future__ import annotations

import re
import textwrap

from .base import LSPServerBase


class ParamUtilsMixin(LSPServerBase):
    """Provides shared utility methods for parameter handling across LSP features."""

    def _get_python_type_name(self, param_type: str, allow_none: bool = False) -> str:
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
            if allow_none:
                type_names.append("None")

            return " | ".join(type_names)

        # For unknown param types, just return the param type name
        base_type = param_type.lower()
        return f"{base_type} | None" if allow_none else base_type

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

    def _find_containing_class(self, lines: list[str], current_line: int) -> str | None:
        """Find the class that contains the current line."""
        # Compiled regex patterns for performance
        CLASS_DEFINITION_PATTERN = re.compile(r"^([^#]*?)class\s+(\w+)", re.MULTILINE)

        # Look backwards for class definition
        for line_idx in range(current_line, -1, -1):
            if line_idx >= len(lines):
                continue
            line = lines[line_idx].strip()

            # Look for class definition
            match = CLASS_DEFINITION_PATTERN.match(line)
            if match:
                class_name = match.group(2)
                return class_name

        return None

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

    def _clean_and_format_documentation(self, doc: str) -> str:
        """Clean and format documentation text."""
        if not doc:
            return doc

        # Clean and dedent the documentation
        clean_doc = textwrap.dedent(doc).strip()
        return clean_doc
