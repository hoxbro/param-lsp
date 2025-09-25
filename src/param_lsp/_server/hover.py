"""Hover mixin for providing rich hover information."""

from __future__ import annotations

import re
import textwrap
from typing import TYPE_CHECKING

import param

from param_lsp.constants import PARAM_NAMESPACE_METHODS, RX_METHODS_DOCS

# Server code now uses new format directly
from .base import LSPServerBase

# Compiled regex patterns for performance
_re_param_rx_method = re.compile(r"\.param\.\w+\.rx\b")
_re_param_namespace_method = re.compile(r"\.param\.\w+\(")
_re_reactive_expression = re.compile(r"\.param\.\w+\.rx\.")

if TYPE_CHECKING:
    from typing import Any


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
            if hasattr(self, "param_types") and word in self.param_types:
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
                    hover_info = self._build_parameter_hover_info_new(
                        param_info,
                        class_name,
                    )
                    if hover_info:
                        return hover_info

            # Check if it's a parameter in an external class
            analyzer = self.document_cache[uri]["analyzer"]
            for class_name, class_info in analyzer.external_param_classes.items():
                if class_info and word in class_info.parameters:
                    hover_info = self._build_external_parameter_hover_info(
                        word, class_name, class_info
                    )
                    if hover_info:
                        return hover_info

        return None

    def _build_parameter_hover_info_new(self, param_info, class_name: str) -> str | None:
        """Build hover information for a parameter using new dataclass format."""
        if not param_info:
            return None

        param_name = param_info.name
        hover_parts = [f"**{param_info.param_type} Parameter '{param_name}'**"]

        # Map param types to Python types, including None if allowed
        python_type = self._get_python_type_name(param_info.param_type, param_info.allow_none)
        hover_parts.append(f"Allowed types: {python_type}")

        # Add bounds information
        if param_info.bounds:
            bounds = param_info.bounds
            if len(bounds) == 2:
                min_val, max_val = bounds
                hover_parts.append(f"Bounds: `[{min_val}, {max_val}]`")
            elif len(bounds) == 4:
                min_val, max_val, left_inclusive, right_inclusive = bounds
                left_bracket = "[" if left_inclusive else "("
                right_bracket = "]" if right_inclusive else ")"
                hover_parts.append(f"Bounds: `{left_bracket}{min_val}, {max_val}{right_bracket}`")

        # Add documentation
        if param_info.doc:
            clean_doc = self._clean_and_format_documentation(param_info.doc)
            hover_parts.append("---")
            hover_parts.append("Description:")
            hover_parts.append(clean_doc)

        # Add source location information
        if param_info.location:
            source_line = param_info.location.get("source")
            if source_line:
                hover_parts.append("---")
                hover_parts.append("Definition:")
                hover_parts.append(f"```python\n{source_line}\n```")

        return "\n".join(hover_parts)

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

    def _build_parameter_hover_info(
        self,
        param_name: str,
        class_name: str,
        param_parameter_types: dict[str, dict[str, str]],
        param_parameter_docs: dict[str, dict[str, str]],
        param_parameter_bounds: dict[str, dict[str, tuple]],
        param_parameter_allow_none: dict[str, dict[str, bool]] | None = None,
        param_parameter_locations: dict[str, dict[str, dict[str, Any]]] | None = None,
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
            clean_doc = self._clean_and_format_documentation(doc)
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
        self, param_name: str, class_name: str, class_info: dict[str, Any]
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
            clean_doc = self._clean_and_format_documentation(doc)
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

    def _clean_and_format_documentation(self, doc: str) -> str:
        """Clean and format documentation text."""
        if not doc:
            return doc

        # Clean and dedent the documentation
        clean_doc = textwrap.dedent(doc).strip()
        return clean_doc
