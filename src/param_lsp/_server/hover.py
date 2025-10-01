"""Hover mixin for providing rich hover information."""

from __future__ import annotations

import re
import textwrap

import param

from param_lsp.constants import PARAM_NAMESPACE_METHODS, RX_METHODS_DOCS, SELECTOR_PARAM_TYPES

from .base import LSPServerBase

# Compiled regex patterns for performance
_re_param_rx_method = re.compile(r"\.param\.\w+\.rx\b")
_re_param_namespace_method = re.compile(r"\.param\.\w+\(")
_re_reactive_expression = re.compile(r"\.param\.\w+\.rx\.")


class HoverMixin(LSPServerBase):
    """Provides hover information functionality for the LSP server."""

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
            if hasattr(self, "classes") and word in self.classes:
                if param:
                    param_class = getattr(param, word, None)
                    if param_class and hasattr(param_class, "__doc__"):
                        return param_class.__doc__
                return f"Param parameter type: {word}"

            # Check if it's a parameter in a local class
            param_classes = analysis.get("param_classes", {})

            for class_name, class_info in param_classes.items():
                if word in class_info.parameters:
                    param_info = class_info.parameters[word]
                    hover_info = self._build_parameter_hover_info(
                        param_info,
                        class_name,
                    )
                    if hover_info:
                        return hover_info

            # Check if it's a parameter in an external class
            analyzer = self.document_cache[uri]["analyzer"]
            for class_name, class_info in analyzer.external_param_classes.items():
                if class_info and word in class_info.parameters:
                    param_info = class_info.get_parameter(word)
                    if param_info:
                        hover_info = self._build_parameter_hover_info(param_info, class_name)
                        if hover_info:
                            return hover_info

        return None

    def _build_parameter_hover_info(self, param_info, class_name: str) -> str | None:
        """Build hover information for a parameter."""
        if not param_info:
            return None

        param_name = param_info.name

        # Build header section with type info
        # Check if this is from an external class (contains dots in class name)
        if "." in class_name:
            header_parts = [f"**{param_info.cls} Parameter '{param_name}' (from {class_name})**"]
        else:
            header_parts = [f"**{param_info.cls} Parameter '{param_name}'**"]
        # For Selector parameters with objects, show allowed values only
        if param_info.objects and param_info.cls in SELECTOR_PARAM_TYPES:
            # Format objects: numbers without quotes, strings with quotes
            formatted_objects = []
            for obj in param_info.objects:
                if isinstance(obj, (int, float)):
                    formatted_objects.append(str(obj))
                else:
                    formatted_objects.append(f'"{obj}"')
            objects_str = ", ".join(formatted_objects)
            header_parts.append(f"Allowed objects: [{objects_str}]")
        elif param_info.cls not in SELECTOR_PARAM_TYPES:
            # Only show "Allowed types" for non-Selector parameters
            python_type = self._get_python_type_name(param_info.cls, param_info.allow_None)
            header_parts.append(f"Allowed types: {python_type}")

        # Add bounds information to header section
        if param_info.bounds:
            bounds = param_info.bounds
            if len(bounds) == 2:
                min_val, max_val = bounds
                header_parts.append(f"Bounds: `[{min_val}, {max_val}]`")
            elif len(bounds) == 4:
                min_val, max_val, left_inclusive, right_inclusive = bounds
                left_bracket = "[" if left_inclusive else "("
                right_bracket = "]" if right_inclusive else ")"
                header_parts.append(f"Bounds: `{left_bracket}{min_val}, {max_val}{right_bracket}`")

        hover_sections = ["\n\n".join(header_parts)]

        # Add documentation section
        if param_info.doc:
            clean_doc = textwrap.dedent(param_info.doc).strip()
            doc_section = "---\nDescription:\n\n" + clean_doc
            hover_sections.append(doc_section)

        # Add source location section
        if param_info.location:
            source_line = param_info.location.get("source")
            line_number = param_info.location.get("line")
            if source_line:
                # Clean and dedent multiline parameter definitions
                clean_source = textwrap.dedent(source_line).strip()
                if line_number:
                    definition_header = f"Definition (line {line_number}):"
                else:
                    definition_header = "Definition:"
                source_section = f"---\n{definition_header}\n```python\n{clean_source}\n```"
                hover_sections.append(source_section)

        return "\n\n".join(hover_sections)

    def _is_rx_method_context(self, line: str) -> bool:
        """Check if the rx word is in a parameter context like obj.param.x.rx."""
        # Check if line contains pattern like .param.something.rx
        return bool(_re_param_rx_method.search(line))

    def _build_rx_method_hover_info(self) -> str:
        """Build hover information for the rx property."""
        hover_parts = [
            "**rx Property**",
            "Create a reactive expression for this parameter.",
            "",
            "Reactive expressions enable you to build computational graphs that automatically update when parameter values change.",
            "",
            "**Documentation**: [Reactive Expressions Guide](https://param.holoviz.org/user_guide/Reactive_Expressions.html)",
        ]
        return "\n".join(hover_parts)

    def _get_param_namespace_method_hover_info(self, line: str, word: str) -> str | None:
        """Get hover information for param namespace methods like obj.param.values()."""
        # Check if we're in a param namespace method context
        if not _re_param_namespace_method.search(line):
            return None

        if word in PARAM_NAMESPACE_METHODS:
            method_info = PARAM_NAMESPACE_METHODS[word]
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
        if not _re_reactive_expression.search(line):
            return None

        if word in RX_METHODS_DOCS:
            method_info = RX_METHODS_DOCS[word]
            hover_parts = [
                f"**{method_info['signature']}**",
                "",
                method_info["description"],
                "",
                f"**Example**: `{method_info['example']}`",
            ]
            return "\n".join(hover_parts)

        return None
