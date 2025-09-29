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

from param_lsp.constants import PARAM_TYPES

from . import parso_utils

if TYPE_CHECKING:
    from parso.tree import NodeOrLeaf

logger = logging.getLogger(__name__)


class ParameterDetector:
    """Handles detection of parameter assignments and calls in AST."""

    def __init__(self, imports: dict[str, str]):
        """Initialize parameter detector.

        Args:
            imports: Dictionary mapping import aliases to full module names
        """
        self.imports = imports

    def is_parameter_assignment(self, node: NodeOrLeaf) -> bool:
        """Check if a parso assignment statement looks like a parameter definition.

        Args:
            node: AST node to check

        Returns:
            True if node represents a parameter assignment
        """
        # Find the right-hand side of the assignment (after '=')
        found_equals = False
        for child in parso_utils.get_children(node):
            if child.type == "operator" and parso_utils.get_value(child) == "=":
                found_equals = True
            elif found_equals and child.type in ("power", "atom_expr"):
                # Check if it's a parameter type call
                return self.is_parameter_call(child)
        return False

    def is_parameter_call(self, node: NodeOrLeaf) -> bool:
        """Check if a parso power/atom_expr node represents a parameter type call.

        Args:
            node: AST node to check

        Returns:
            True if node represents a parameter type call
        """
        # Extract the function name and check if it's a param type
        func_name = None

        # Look through children to find the actual function being called
        for child in parso_utils.get_children(node):
            if child.type == "name":
                # This could be a direct function call (e.g., "String") or module name
                func_name = parso_utils.get_value(child)
            elif child.type == "trailer":
                # Handle dotted calls like param.Integer
                for trailer_child in parso_utils.get_children(child):
                    if trailer_child.type == "name":
                        func_name = parso_utils.get_value(trailer_child)
                        break
                # If we found a function name in a trailer, that's the final function name
                if func_name:
                    break

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

    def _reconstruct_dotted_name(self, node: NodeOrLeaf) -> str | None:
        """Reconstruct a dotted name from a parso dotted_name node.

        Args:
            node: The dotted_name node

        Returns:
            The reconstructed dotted name string
        """
        if node.type != "dotted_name":
            return parso_utils.get_value(node)

        parts = [
            parso_utils.get_value(child)
            for child in parso_utils.get_children(node)
            if child.type == "name"
        ]

        # Filter out None values before joining
        valid_parts = [part for part in parts if part is not None]
        return ".".join(valid_parts) if valid_parts else None

    def handle_import(self, node: NodeOrLeaf) -> None:
        """Handle 'import' statements (parso node).

        Args:
            node: AST node representing import statement
        """
        # For parso import_name nodes, parse the import statement
        for child in parso_utils.get_children(node):
            if child.type == "dotted_as_name":
                # Handle "import module as alias"
                module_name = None
                alias_name = None
                for part in parso_utils.get_children(child):
                    if part.type == "name":
                        if module_name is None:
                            module_name = parso_utils.get_value(part)
                        else:
                            alias_name = parso_utils.get_value(part)
                if module_name:
                    self.imports[alias_name or module_name] = module_name
            elif child.type == "dotted_name":
                # Handle "import module" - reconstruct dotted name from children
                module_name = self._reconstruct_dotted_name(child)
                if module_name:
                    self.imports[module_name] = module_name
            elif child.type == "name" and parso_utils.get_value(child) not in ("import", "as"):
                # Simple case: "import module"
                module_name = parso_utils.get_value(child)
                if module_name:
                    self.imports[module_name] = module_name

    def handle_import_from(self, node: NodeOrLeaf) -> None:
        """Handle 'from ... import ...' statements (parso node).

        Args:
            node: AST node representing from-import statement
        """
        # For parso import_from nodes, parse the from...import statement
        module_name = None
        import_names = []

        # First pass: find module name and collect import names
        for child in parso_utils.get_children(node):
            if (
                child.type == "name"
                and module_name is None
                and parso_utils.get_value(child) not in ("from", "import")
            ) or (child.type == "dotted_name" and module_name is None):
                module_name = self._reconstruct_dotted_name(child)
            elif child.type == "import_as_name":
                # Handle direct "from module import name as alias"
                import_name = None
                alias_name = None
                for part in parso_utils.get_children(child):
                    if part.type == "name":
                        if import_name is None:
                            import_name = parso_utils.get_value(part)
                        else:
                            alias_name = parso_utils.get_value(part)
                if import_name:
                    import_names.append((import_name, alias_name))
            elif child.type == "import_as_names":
                for name_child in parso_utils.get_children(child):
                    if name_child.type == "import_as_name":
                        # Handle "from module import name as alias"
                        import_name = None
                        alias_name = None
                        for part in parso_utils.get_children(name_child):
                            if part.type == "name":
                                if import_name is None:
                                    import_name = parso_utils.get_value(part)
                                else:
                                    alias_name = parso_utils.get_value(part)
                        if import_name:
                            import_names.append((import_name, alias_name))
                    elif name_child.type == "name":
                        # Handle "from module import name"
                        name_value = parso_utils.get_value(name_child)
                        if name_value:
                            import_names.append((name_value, None))
            elif (
                child.type == "name"
                and parso_utils.get_value(child) not in ("from", "import")
                and module_name is not None
            ):
                # Handle simple "from module import name" where name is a direct child
                child_value = parso_utils.get_value(child)
                if child_value:
                    import_names.append((child_value, None))

        # Second pass: register all imports
        if module_name:
            for import_name, alias_name in import_names:
                full_name = f"{module_name}.{import_name}"
                self.imports[alias_name or import_name] = full_name


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
