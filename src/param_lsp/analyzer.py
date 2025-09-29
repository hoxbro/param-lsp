"""
HoloViz Param Language Server Protocol - Core Analyzer.

Provides comprehensive analysis of Param-based Python code including:
- Parameter discovery and type inference
- Cross-file inheritance resolution
- External library class introspection
- Real-time type checking and validation
- Bounds and constraint checking

Modular Architecture:
This analyzer uses a modular component architecture for maintainability
and testability:

- parso_utils: AST navigation and parsing utilities
- parameter_extractor: Parameter definition extraction
- validation: Type checking and constraint validation
- external_class_inspector: Runtime introspection of external classes
- inheritance_resolver: Parameter inheritance resolution
- import_resolver: Cross-file import and module resolution

The analyzer orchestrates these components to provide complete IDE support
for Parameterized classes from both local code and external libraries
like Panel, HoloViews, Bokeh, and others.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict, cast

import parso

from ._analyzer import parso_utils
from ._analyzer.external_class_inspector import ExternalClassInspector
from ._analyzer.import_resolver import ImportResolver
from ._analyzer.inheritance_resolver import InheritanceResolver
from ._analyzer.parameter_extractor import (
    extract_boolean_value,
    extract_numeric_value,
    extract_parameter_info_from_assignment,
    get_keyword_arguments,
    is_none_value,
    resolve_parameter_class,
)
from ._analyzer.validation import ParameterValidator
from .constants import PARAM_TYPE_MAP, PARAM_TYPES
from .models import ParameterInfo, ParameterizedInfo

if TYPE_CHECKING:
    from parso.tree import BaseNode, NodeOrLeaf

# Type aliases for better type safety
ParsoNode = "NodeOrLeaf"  # General parso node (BaseNode is a subclass)
NumericValue = int | float | None  # Numeric values from nodes
BoolValue = bool | None  # Boolean values from nodes


class TypeErrorDict(TypedDict):
    """Type definition for type error dictionaries."""

    line: int
    col: int
    end_line: int
    end_col: int
    message: str
    severity: str
    code: str


class AnalysisResult(TypedDict):
    """Type definition for analysis result dictionaries."""

    param_classes: dict[str, ParameterizedInfo]
    imports: dict[str, str]
    type_errors: list[TypeErrorDict]


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ParamAnalyzer:
    """Analyzes Python code for Param usage patterns."""

    def __init__(self, workspace_root: str | None = None):
        self.param_classes: dict[str, ParameterizedInfo] = {}
        self.imports: dict[str, str] = {}
        # Store file content for source line lookup
        self._current_file_content: str | None = None
        self.type_errors: list[TypeErrorDict] = []
        self.param_type_map = PARAM_TYPE_MAP

        # Workspace-wide analysis
        self.workspace_root = Path(workspace_root) if workspace_root else None
        self.module_cache: dict[str, AnalysisResult] = {}  # module_name -> analysis_result
        self.file_cache: dict[str, AnalysisResult] = {}  # file_path -> analysis_result

        # Use modular external class inspector
        self.external_inspector = ExternalClassInspector()
        self.external_param_classes = self.external_inspector.external_param_classes

        # Populate external library cache on initialization using modular component
        self.external_inspector.populate_external_library_cache()

        # Use modular parameter validator
        self.validator = ParameterValidator(
            param_type_map=self.param_type_map,
            param_classes=self.param_classes,
            external_param_classes=self.external_param_classes,
            imports=self.imports,
            is_parameter_assignment_func=self._is_parameter_assignment,
            workspace_root=str(self.workspace_root) if self.workspace_root else None,
        )
        # Pass external inspector to validator for external class analysis
        self.validator.external_inspector = self.external_inspector

        # Use modular import resolver
        self.import_resolver = ImportResolver(
            workspace_root=str(self.workspace_root) if self.workspace_root else None,
            imports=self.imports,
            module_cache=self.module_cache,
            file_cache=self.file_cache,
            analyze_file_func=self._analyze_file_for_import_resolver,
        )

        # Use modular inheritance resolver
        self.inheritance_resolver = InheritanceResolver(
            param_classes=self.param_classes,
            external_param_classes=self.external_param_classes,
            imports=self.imports,
            get_imported_param_class_info_func=self.import_resolver.get_imported_param_class_info,
            analyze_external_class_ast_func=self._analyze_external_class_ast,
            resolve_full_class_path_func=self.import_resolver.resolve_full_class_path,
        )

    def _analyze_file_for_import_resolver(self, content: str, file_path: str | None = None) -> AnalysisResult:
        """Analyze a file for the import resolver (avoiding circular dependencies)."""
        # Create a new analyzer instance for the imported module to avoid conflicts
        module_analyzer = ParamAnalyzer(
            str(self.workspace_root) if self.workspace_root else None
        )
        return module_analyzer.analyze_file(content, file_path)

    def analyze_file(self, content: str, file_path: str | None = None) -> AnalysisResult:
        """Analyze a Python file for Param usage."""
        try:
            # Use parso with error recovery enabled for better handling of incomplete syntax
            tree = parso.parse(content, error_recovery=True)
            self._reset_analysis()
            self._current_file_path = file_path
            self._current_file_content = content

            # Note: parso handles syntax errors internally with error_recovery=True

            # Cache the tree walk to avoid multiple expensive traversals
            all_nodes = list(parso_utils.walk_tree(tree))
        except Exception as e:
            # If parso completely fails, log and return empty result
            logger.error(f"Failed to parse file: {e}")
            return AnalysisResult(param_classes={}, imports={}, type_errors=[])

        # First pass: collect imports using cached nodes
        for node in all_nodes:
            if node.type == "import_name":
                self._handle_import(node)
            elif node.type == "import_from":
                self._handle_import_from(node)

        # Second pass: collect class definitions in order, respecting inheritance
        class_nodes: list[BaseNode] = [
            cast("BaseNode", node)
            for node in all_nodes
            if node.type == "classdef"
        ]

        # Process classes in dependency order (parents before children)
        processed_classes = set()
        while len(processed_classes) < len(class_nodes):
            progress_made = False
            for node in class_nodes:
                class_name = parso_utils.get_class_name(node)
                if not class_name or class_name in processed_classes:
                    continue

                # Check if all parent classes are processed or are external param classes
                can_process = True
                bases = parso_utils.get_class_bases(node)
                for base in bases:
                    if base.type == "name":
                        parent_name = parso_utils.get_value(base)
                        # If it's a class defined in this file and not processed yet, wait
                        if (
                            any(
                                parso_utils.get_class_name(cn) == parent_name for cn in class_nodes
                            )
                            and parent_name not in processed_classes
                        ):
                            can_process = False
                            break

                if can_process:
                    self._handle_class_def(node)
                    processed_classes.add(class_name)
                    progress_made = True

            # Prevent infinite loop if there are circular dependencies
            if not progress_made:
                # Process remaining classes anyway
                for node in class_nodes:
                    class_name = parso_utils.get_class_name(node)
                    if class_name and class_name not in processed_classes:
                        self._handle_class_def(node)
                        processed_classes.add(class_name)
                break

        # Pre-pass: discover all external Parameterized classes using cached nodes
        self._discover_external_param_classes(tree, all_nodes)

        # Perform parameter validation after parsing using modular validator with cached nodes
        self.type_errors = self.validator.check_parameter_types(tree, content.split("\n"), all_nodes)

        return {
            "param_classes": self.param_classes,
            "imports": self.imports,
            "type_errors": self.type_errors,
        }

    def _reset_analysis(self) -> None:
        """Reset analysis state."""
        self.param_classes.clear()
        self.imports.clear()
        self.type_errors.clear()

    def _is_parameter_assignment(self, node: NodeOrLeaf) -> bool:
        """Check if a parso assignment statement looks like a parameter definition."""
        # Find the right-hand side of the assignment (after '=')
        found_equals = False
        for child in parso_utils.get_children(node):
            if child.type == "operator" and parso_utils.get_value(child) == "=":
                found_equals = True
            elif found_equals and child.type in ("power", "atom_expr"):
                # Check if it's a parameter type call
                return self._is_parameter_call(child)
        return False

    def _is_parameter_call(self, node: NodeOrLeaf) -> bool:
        """Check if a parso power/atom_expr node represents a parameter type call."""
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


    def _handle_import(self, node: NodeOrLeaf) -> None:
        """Handle 'import' statements (parso node)."""
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
                # Handle "import module"
                module_name = parso_utils.get_value(child)
                if module_name:
                    self.imports[module_name] = module_name
            elif child.type == "name" and parso_utils.get_value(child) not in ("import", "as"):
                # Simple case: "import module"
                module_name = parso_utils.get_value(child)
                if module_name:
                    self.imports[module_name] = module_name

    def _handle_import_from(self, node: NodeOrLeaf) -> None:
        """Handle 'from ... import ...' statements (parso node)."""
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
                module_name = parso_utils.get_value(child)
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

    def _handle_class_def(self, node: BaseNode) -> None:
        """Handle class definitions that might inherit from param.Parameterized (parso node)."""
        # Check if class inherits from param.Parameterized (directly or indirectly)
        is_param_class = False
        bases = parso_utils.get_class_bases(node)
        for base in bases:
            if self.inheritance_resolver.is_param_base(base):
                is_param_class = True
                break

        if is_param_class:
            class_name = parso_utils.get_class_name(node)
            if class_name is None:
                return  # Skip if we can't get the class name
            class_info = ParameterizedInfo(name=class_name)

            # Get inherited parameters from parent classes first
            inherited_parameters = self.inheritance_resolver.collect_inherited_parameters(
                node, getattr(self, "_current_file_path", None)
            )
            # Add inherited parameters first
            class_info.merge_parameters(inherited_parameters)

            # Extract parameters from this class and add them (overriding inherited ones)
            current_parameters = self._extract_parameters(node)
            for param_info in current_parameters:
                class_info.add_parameter(param_info)

            self.param_classes[class_name] = class_info



    def _extract_parameters(self, node) -> list[ParameterInfo]:
        """Extract parameter definitions from a Param class (parso node)."""
        parameters = []

        for assignment_node, target_name in parso_utils.find_all_parameter_assignments(
            node, self._is_parameter_assignment
        ):
            param_info = extract_parameter_info_from_assignment(
                assignment_node, target_name, self.imports, self._current_file_content
            )
            if param_info:
                parameters.append(param_info)

        return parameters























    def _analyze_external_class_ast(self, full_class_path: str) -> ParameterizedInfo | None:
        """Analyze external classes using the modular external inspector."""
        return self.external_inspector.analyze_external_class_ast(full_class_path)

    def _get_parameter_source_location(
        self, param_obj: Any, cls: type, param_name: str
    ) -> dict[str, str] | None:
        """Get source location information for an external parameter."""
        try:
            # Try to find the class where this parameter is actually defined
            defining_class = self._find_parameter_defining_class(cls, param_name)
            if not defining_class:
                return None

            # Try to get the complete parameter definition
            source_definition = None
            try:
                # Try to get the source lines and find parameter definition
                source_lines, _start_line = inspect.getsourcelines(defining_class)
                source_definition = self._extract_complete_parameter_definition(
                    source_lines, param_name
                )
            except (OSError, TypeError):
                # Can't get source lines
                pass

            # Return the complete parameter definition
            if source_definition:
                return {
                    "source": source_definition,
                }
            else:
                # No source available
                return None

        except Exception:
            # If anything goes wrong, return None
            return None

    def _find_parameter_defining_class(self, cls: type, param_name: str) -> type | None:
        """Find the class in the MRO where a parameter is actually defined."""
        # Walk up the MRO to find where this parameter was first defined
        for base_cls in cls.__mro__:
            if hasattr(base_cls, "param") and hasattr(base_cls.param, param_name):
                # Check if this class actually defines the parameter (not just inherits it)
                if param_name in getattr(base_cls, "_param_names", []):
                    return base_cls
                # Fallback: check if the parameter object is defined in this class's dict
                if hasattr(base_cls, "_param_watchers") or param_name in base_cls.__dict__:
                    return base_cls

        # If we can't find the defining class, return the original class
        return cls

    def _get_relative_library_path(self, source_file: str, module_name: str) -> str:
        """Convert absolute source file path to a relative library path."""
        path = Path(source_file)

        # Try to find the library root by looking for the top-level package
        module_parts = module_name.split(".")
        library_name = module_parts[0]  # e.g., 'panel', 'holoviews', etc.

        # Find the library root in the path
        path_parts = path.parts
        for i, part in enumerate(reversed(path_parts)):
            if part == library_name:
                # Found the library root, create relative path from there
                lib_root_index = len(path_parts) - i - 1
                relative_parts = path_parts[lib_root_index:]
                return "/".join(relative_parts)

        # Fallback: just use the filename with module info
        return f"{library_name}/{path.name}"

    def _extract_complete_parameter_definition(
        self, source_lines: list[str], param_name: str
    ) -> str | None:
        """Extract the complete parameter definition including all lines until closing parenthesis."""
        # Find the parameter line first using simple string matching (more reliable)
        for i, line in enumerate(source_lines):
            if (
                (f"{param_name} =" in line or f"{param_name}=" in line)
                and not line.strip().startswith("#")
                and self._looks_like_parameter_assignment(line)
            ):
                # Extract the complete multiline definition
                return self._extract_multiline_definition(source_lines, i)

        return None

    def _looks_like_parameter_assignment(self, line: str) -> bool:
        """Check if a line looks like a parameter assignment."""
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

    def _extract_multiline_definition(self, source_lines: list[str], start_index: int) -> str:
        """Extract a multiline parameter definition by finding matching parentheses."""
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

    def _find_parameter_line_in_source(
        self, source_lines: list[str], start_line: int, param_name: str
    ) -> int | None:
        """Find the line number where a parameter is defined in source code."""
        # Use the same generic detection logic
        for i, line in enumerate(source_lines):
            if (
                (f"{param_name} =" in line or f"{param_name}=" in line)
                and not line.strip().startswith("#")
                and self._looks_like_parameter_assignment(line)
            ):
                return start_line + i
        return None

    def _discover_external_param_classes(self, tree: NodeOrLeaf, cached_nodes: list[NodeOrLeaf] | None = None) -> None:
        """Pre-pass to discover all external Parameterized classes using parso analysis."""
        nodes_to_check = cached_nodes if cached_nodes is not None else parso_utils.walk_tree(tree)
        for node in nodes_to_check:
            if node.type in ("power", "atom_expr") and parso_utils.is_function_call(node):
                full_class_path = self.import_resolver.resolve_full_class_path(node)
                if full_class_path:
                    self._analyze_external_class_ast(full_class_path)

    def resolve_class_name_from_context(
        self, class_name: str, param_classes: dict[str, ParameterizedInfo], document_content: str
    ) -> str | None:
        """Resolve a class name from context, handling both direct class names and variable names."""
        # If it's already a known param class, return it
        if class_name in param_classes:
            return class_name

        # If it's a variable name, try to find its assignment in the document
        if document_content:
            # Look for assignments like: variable_name = ClassName(...)
            assignment_pattern = re.compile(
                rf"^([^#]*?){re.escape(class_name)}\s*=\s*(\w+(?:\.\w+)*)\s*\(", re.MULTILINE
            )

            for match in assignment_pattern.finditer(document_content):
                assigned_class = match.group(2)

                # Check if the assigned class is a known param class
                if assigned_class in param_classes:
                    return assigned_class

                # Check if it's an external class
                if "." in assigned_class:
                    # Handle dotted names like hv.Curve
                    parts = assigned_class.split(".")
                    if len(parts) >= 2:
                        alias = parts[0]
                        class_part = ".".join(parts[1:])
                        if alias in self.imports:
                            full_module = self.imports[alias]
                            full_class_path = f"{full_module}.{class_part}"
                            class_info = self.external_param_classes.get(full_class_path)
                            if class_info is None:
                                class_info = self._analyze_external_class_ast(full_class_path)
                            if class_info:
                                # Return the original dotted name for external class handling
                                return assigned_class

        return None
