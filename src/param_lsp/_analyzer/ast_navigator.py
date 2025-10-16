"""
AST Navigation Module for param-lsp analyzer.

This module contains AST navigation and parsing logic that was extracted
from the main analyzer to improve modularity and maintainability.

Components:
- ParameterDetector: Detects parameter assignments and calls in AST
- ImportHandler: Handles import statement parsing
- ClassHandler: Handles class definition processing
- SourceAnalyzer: Analyzes source code for parameter definitions
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from param_lsp import _treesitter
from param_lsp.constants import PARAM_TYPES

if TYPE_CHECKING:
    from tree_sitter import Node

logger = logging.getLogger(__name__)


class ParameterDetector:
    """Handles detection of parameter assignments and calls in AST."""

    def __init__(self, imports: dict[str, str]):
        """Initialize parameter detector.

        Args:
            imports: Dictionary mapping import aliases to full module names
        """
        self.imports = imports

    def is_parameter_assignment(self, node: Node) -> bool:
        """Check if a tree-sitter assignment statement looks like a parameter definition.

        Args:
            node: AST node to check

        Returns:
            True if node represents a parameter assignment
        """
        # In tree-sitter: assignment node has 'left', 'right' fields
        if node.type == "assignment":
            right_node = node.child_by_field_name("right")
            if right_node and right_node.type == "call":
                return self.is_parameter_call(right_node)

        # Fallback: scan children for '=' and check right side
        found_equals = False
        for child in _treesitter.get_children(node):
            if child.text == b"=" or _treesitter.get_value(child) == "=":
                found_equals = True
            elif found_equals and child.type == "call":
                # Check if it's a parameter type call
                return self.is_parameter_call(child)
        return False

    def is_parameter_call(self, node: Node) -> bool:
        """Check if a tree-sitter call node represents a parameter type call.

        Args:
            node: AST node to check

        Returns:
            True if node represents a parameter type call
        """
        if node.type != "call":
            return False

        # Get the function being called (the 'function' field)
        func_node = node.child_by_field_name("function")
        if not func_node:
            return False

        # Extract the function name
        func_name = None

        if func_node.type == "identifier":
            # Simple call: String()
            func_name = _treesitter.get_value(func_node)
        elif func_node.type == "attribute":
            # Dotted call: param.String()
            attr_node = func_node.child_by_field_name("attribute")
            if attr_node:
                func_name = _treesitter.get_value(attr_node)

        if func_name:
            # Check if it's a direct param type
            if func_name in PARAM_TYPES:
                return True

            # Check if it's an imported param type
            if func_name in self.imports:
                imported_full_name = self.imports[func_name]
                if imported_full_name.startswith("param."):
                    param_type = imported_full_name.split(".")[-1]
                    return param_type in PARAM_TYPES

        return False


class ImportHandler:
    """Handles parsing of import statements in AST."""

    def __init__(self, imports: dict[str, str]):
        """Initialize import handler.

        Args:
            imports: Dictionary to store import mappings
        """
        self.imports = imports

    def _reconstruct_dotted_name(self, node: Node) -> str | None:
        """Reconstruct a dotted name from a tree-sitter dotted_name/attribute node.

        Args:
            node: The dotted_name or attribute node

        Returns:
            The reconstructed dotted name string
        """
        if node.type == "identifier":
            return _treesitter.get_value(node)

        if node.type == "dotted_name":
            parts = [
                _treesitter.get_value(child)
                for child in _treesitter.get_children(node)
                if child.type == "identifier"
            ]
            # Filter out None values before joining
            valid_parts = [part for part in parts if part is not None]
            return ".".join(valid_parts) if valid_parts else None

        if node.type == "attribute":
            # Recursively build dotted name from attribute chain
            obj_node = node.child_by_field_name("object")
            attr_node = node.child_by_field_name("attribute")
            if obj_node and attr_node:
                obj_name = self._reconstruct_dotted_name(obj_node)
                attr_name = _treesitter.get_value(attr_node)
                if obj_name and attr_name:
                    return f"{obj_name}.{attr_name}"

        return _treesitter.get_value(node)

    def handle_import(self, node: Node) -> None:
        """Handle 'import' statements (tree-sitter node).

        Args:
            node: AST node representing import statement
        """
        # Tree-sitter import_statement structure:
        # import_statement -> name: dotted_name/identifier, alias: (as) identifier?
        for child in _treesitter.get_children(node):
            if child.type == "aliased_import":
                # Handle "import module as alias"
                name_node = child.child_by_field_name("name")
                alias_node = child.child_by_field_name("alias")
                if name_node:
                    module_name = self._reconstruct_dotted_name(name_node)
                    alias_name = _treesitter.get_value(alias_node) if alias_node else None
                    if module_name:
                        self.imports[alias_name or module_name] = module_name
            elif child.type in ("dotted_name", "identifier"):
                # Handle "import module"
                module_name = self._reconstruct_dotted_name(child)
                if module_name:
                    self.imports[module_name] = module_name

    def handle_import_from(self, node: Node) -> None:
        """Handle 'from ... import ...' statements (tree-sitter node).

        Args:
            node: AST node representing from-import statement
        """
        # Tree-sitter import_from_statement has 'module_name' field
        module_node = node.child_by_field_name("module_name")
        if not module_node:
            return

        module_name = self._reconstruct_dotted_name(module_node)
        if not module_name:
            return

        # Find imported names - look for aliased_import, identifier, or dotted_name children
        for child in _treesitter.get_children(node):
            if child.type == "aliased_import":
                # Handle "from module import name as alias"
                name_node = child.child_by_field_name("name")
                alias_node = child.child_by_field_name("alias")
                if name_node:
                    import_name = _treesitter.get_value(name_node)
                    alias_name = _treesitter.get_value(alias_node) if alias_node else None
                    if import_name:
                        full_name = f"{module_name}.{import_name}"
                        self.imports[alias_name or import_name] = full_name
            elif child.type in ("identifier", "dotted_name") and child != module_node:
                # Handle "from module import name"
                import_name = self._reconstruct_dotted_name(child)
                if import_name and import_name not in ("from", "import"):
                    full_name = f"{module_name}.{import_name}"
                    self.imports[import_name] = full_name


class SourceAnalyzer:
    """Analyzes source code for parameter definitions and multiline constructs."""

    @staticmethod
    def looks_like_parameter_assignment(line: str) -> bool:
        """Check if a line looks like a parameter assignment.

        Args:
            line: Source code line to check

        Returns:
            True if line appears to be a parameter assignment
        """
        # Remove the assignment part and check if there's a function call
        if "=" not in line:
            return False

        right_side = line.split("=", 1)[1].strip()

        # Look for patterns that suggest this is a parameter:
        # - Contains a function call with parentheses
        # - Doesn't look like a simple value assignment
        return (
            "(" in right_side
            and not right_side.startswith(("'", '"', "[", "{", "True", "False"))
            and not right_side.replace(".", "").replace("_", "").isdigit()
        )

    @staticmethod
    def extract_multiline_definition(source_lines: list[str], start_index: int) -> str:
        """Extract a multiline parameter definition by finding matching parentheses.

        Args:
            source_lines: List of source code lines
            start_index: Starting line index

        Returns:
            Complete multiline definition as string
        """
        definition_lines = []
        paren_count = 0
        bracket_count = 0
        brace_count = 0
        in_string = False
        string_char = None

        for i in range(start_index, len(source_lines)):
            line = source_lines[i]
            definition_lines.append(line.rstrip())

            # Parse character by character to handle nested structures properly
            j = 0
            while j < len(line):
                char = line[j]

                # Handle string literals
                if char in ('"', "'") and (j == 0 or line[j - 1] != "\\"):
                    if not in_string:
                        in_string = True
                        string_char = char
                    elif char == string_char:
                        in_string = False
                        string_char = None

                # Skip counting if we're inside a string
                if not in_string:
                    if char == "(":
                        paren_count += 1
                    elif char == ")":
                        paren_count -= 1
                    elif char == "[":
                        bracket_count += 1
                    elif char == "]":
                        bracket_count -= 1
                    elif char == "{":
                        brace_count += 1
                    elif char == "}":
                        brace_count -= 1

                j += 1

            # Check if we've closed all parentheses/brackets/braces
            if paren_count <= 0 and bracket_count <= 0 and brace_count <= 0:
                break

        # Join the lines and clean up the formatting
        complete_definition = "\n".join(definition_lines)
        return complete_definition.strip()

    @staticmethod
    def extract_complete_parameter_definition(
        source_lines: list[str], param_name: str
    ) -> str | None:
        """Extract the complete parameter definition including all lines until closing parenthesis.

        Args:
            source_lines: List of source code lines
            param_name: Name of parameter to find

        Returns:
            Complete parameter definition or None if not found
        """
        # Find the parameter line first using simple string matching (more reliable)
        for i, line in enumerate(source_lines):
            if (
                (f"{param_name} =" in line or f"{param_name}=" in line)
                and not line.strip().startswith("#")
                and SourceAnalyzer.looks_like_parameter_assignment(line)
            ):
                # Extract the complete multiline definition
                return SourceAnalyzer.extract_multiline_definition(source_lines, i)

        return None

    @staticmethod
    def find_parameter_line_in_source(
        source_lines: list[str], start_line: int, param_name: str
    ) -> int | None:
        """Find the line number where a parameter is defined in source code.

        Args:
            source_lines: List of source code lines
            start_line: Starting line number offset
            param_name: Name of parameter to find

        Returns:
            Line number where parameter is defined or None if not found
        """
        # Use the same generic detection logic
        for i, line in enumerate(source_lines):
            if (
                (f"{param_name} =" in line or f"{param_name}=" in line)
                and not line.strip().startswith("#")
                and SourceAnalyzer.looks_like_parameter_assignment(line)
            ):
                return start_line + i
        return None
