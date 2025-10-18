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

- ts_utils: AST navigation and parsing utilities (tree-sitter)
- ts_parser: Tree-sitter Python parser singleton
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

import inspect
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import _treesitter
from ._analyzer.ast_navigator import ImportHandler, ParameterDetector, SourceAnalyzer
from ._analyzer.import_resolver import ImportResolver
from ._analyzer.inheritance_resolver import InheritanceResolver
from ._analyzer.parameter_extractor import extract_parameter_info_from_assignment
from ._analyzer.static_external_analyzer import ExternalClassInspector
from ._analyzer.validation import ParameterValidator
from ._treesitter.queries import find_assignments, find_calls, find_classes, find_imports
from ._types import AnalysisResult
from .models import ParameterInfo, ParameterizedInfo

if TYPE_CHECKING:
    from tree_sitter import Node

    from ._types import (
        ImportDict,
        ParamClassDict,
        TSNode,
        TypeErrorDict,
    )

# Type aliases for better type safety
NumericValue = int | float | None  # Numeric values from nodes
BoolValue = bool | None  # Boolean values from nodes


from ._logging import get_logger

logger = get_logger(__name__, "analyzer")


class ParamAnalyzer:
    """Analyzes Python code for Param usage patterns."""

    def __init__(self, python_env: Any = None, workspace_root: str | None = None):
        """
        Initialize the Param analyzer.

        Args:
            python_env: PythonEnvironment instance for analyzing external libraries.
                       If None, uses the current Python environment.
            workspace_root: Root directory of the workspace
        """
        self.param_classes: ParamClassDict = {}
        self.imports: ImportDict = {}
        # Store file content for source line lookup
        self._current_file_content: str | None = None
        self.type_errors: list[TypeErrorDict] = []

        # Workspace-wide analysis
        self.workspace_root = Path(workspace_root) if workspace_root else None
        self.module_cache: dict[str, AnalysisResult] = {}  # module_name -> analysis_result
        self.file_cache: dict[str, AnalysisResult] = {}  # file_path -> analysis_result

        # Store python_env for passing to child analyzers
        self.python_env = python_env

        # Use static external analyzer for external class analysis
        self.external_inspector = ExternalClassInspector(python_env=python_env)

        # Maintain compatibility with external_param_classes interface
        # The static analyzer doesn't need pre-caching, so this can be empty
        self.external_param_classes: dict[str, ParameterizedInfo | None] = {}

        # Use modular AST navigation components (must be created before validator)
        self.parameter_detector = ParameterDetector(self.imports)
        self.import_handler = ImportHandler(self.imports)

        # Use modular parameter validator
        self.validator = ParameterValidator(
            param_classes=self.param_classes,
            external_param_classes=self.external_param_classes,
            imports=self.imports,
            is_parameter_assignment_func=self._is_parameter_assignment,
            external_inspector=self.external_inspector,
            workspace_root=str(self.workspace_root) if self.workspace_root else None,
        )

        # Use modular import resolver
        self.import_resolver = ImportResolver(
            workspace_root=str(self.workspace_root) if self.workspace_root else None,
            imports=self.imports,
            module_cache=self.module_cache,
            file_cache=self.file_cache,
            analyze_file_func=self._analyze_file_for_import_resolver,
        )

        # Use modular inheritance resolver
        # Filter out None values from external_param_classes
        filtered_external_classes = {
            k: v for k, v in self.external_param_classes.items() if v is not None
        }
        self.inheritance_resolver = InheritanceResolver(
            param_classes=self.param_classes,
            external_param_classes=filtered_external_classes,
            imports=self.imports,
            get_imported_param_class_info_func=self.import_resolver.get_imported_param_class_info,
            analyze_external_class_ast_func=self._analyze_external_class_ast,
            resolve_full_class_path_func=self.import_resolver.resolve_full_class_path,
        )

    def _analyze_file_for_import_resolver(
        self, content: str, file_path: str | None = None
    ) -> AnalysisResult:
        """Analyze a file for the import resolver (avoiding circular dependencies)."""
        # Create a new analyzer instance for the imported module to avoid conflicts
        # Pass through the python_env to ensure external library analysis uses the correct environment
        module_analyzer = ParamAnalyzer(
            python_env=self.python_env,
            workspace_root=str(self.workspace_root) if self.workspace_root else None,
        )
        return module_analyzer.analyze_file(content, file_path)

    def analyze_file(self, content: str, file_path: str | None = None) -> AnalysisResult:
        """Analyze a Python file for Param usage."""
        try:
            # Use tree-sitter with error recovery (always enabled)
            tree = _treesitter.parser.parse(content, error_recovery=True)
            self._reset_analysis()
            self._current_file_path = file_path
            self._current_file_content = content

            # Note: tree-sitter handles syntax errors internally with error recovery

        except Exception as e:
            # If tree-sitter completely fails, log and return empty result
            logger.error(f"Failed to parse file: {e}")
            return AnalysisResult(param_classes={}, imports={}, type_errors=[])

        # First pass: collect imports using optimized queries
        for import_node, _captures in find_imports(tree.root_node):
            if import_node.type == "import_statement":
                self.import_handler.handle_import(import_node)
            elif import_node.type == "import_from_statement":
                self.import_handler.handle_import_from(import_node)

        # Second pass: collect class definitions using optimized queries
        class_matches = find_classes(tree.root_node)
        class_nodes: list[TSNode] = [class_node for class_node, _captures in class_matches]

        # Process classes in dependency order (parents before children)
        processed_classes = set()
        while len(processed_classes) < len(class_nodes):
            progress_made = False
            for node in class_nodes:
                class_name = _treesitter.get_class_name(node)
                if not class_name or class_name in processed_classes:
                    continue

                # Check if all parent classes are processed or are external param classes
                can_process = True
                bases = _treesitter.get_class_bases(node)
                for base in bases:
                    if base.type == "identifier":
                        parent_name = _treesitter.get_value(base)
                        # If it's a class defined in this file and not processed yet, wait
                        if (
                            any(
                                _treesitter.get_class_name(cn) == parent_name for cn in class_nodes
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
                    class_name = _treesitter.get_class_name(node)
                    if class_name and class_name not in processed_classes:
                        self._handle_class_def(node)
                        processed_classes.add(class_name)
                break

        # Pre-pass: discover all external Parameterized classes using optimized queries
        self._discover_external_param_classes(tree.root_node)

        # Perform parameter validation after parsing using modular validator
        self.type_errors = self.validator.check_parameter_types(
            tree.root_node, content.split("\n")
        )

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

    def _is_parameter_assignment(self, node: TSNode) -> bool:
        """Check if a tree-sitter assignment statement looks like a parameter definition."""
        return self.parameter_detector.is_parameter_assignment(node)

    def _handle_class_def(self, node: TSNode) -> None:
        """Handle class definitions that might inherit from param.Parameterized (tree-sitter node)."""
        # Check if class inherits from param.Parameterized (directly or indirectly)
        is_param_class = False
        bases = _treesitter.get_class_bases(node)
        for base in bases:
            if self.inheritance_resolver.is_param_base(
                base, getattr(self, "_current_file_path", None)
            ):
                is_param_class = True
                break

        if is_param_class:
            class_name = _treesitter.get_class_name(node)
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
        """Extract parameter definitions from a Param class (tree-sitter node)."""
        parameters = []

        for assignment_node, target_name in _treesitter.find_all_parameter_assignments(
            node, self._is_parameter_assignment
        ):
            param_info = extract_parameter_info_from_assignment(
                assignment_node, target_name, self.imports, self._current_file_content
            )
            if param_info:
                parameters.append(param_info)

        return parameters

    def _analyze_external_class_ast(self, full_class_path: str | None) -> ParameterizedInfo | None:
        """Analyze external classes using the modular external inspector with caching."""
        if full_class_path is None:
            return None

        # Check cache first
        if full_class_path in self.external_param_classes:
            return self.external_param_classes[full_class_path]

        # Analyze and cache the result
        class_info = self.external_inspector.analyze_external_class(full_class_path)
        self.external_param_classes[full_class_path] = class_info
        return class_info

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
                source_definition = SourceAnalyzer.extract_complete_parameter_definition(
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

    def _discover_external_param_classes(self, tree: Node) -> None:
        """Pre-pass to discover all external Parameterized classes using tree-sitter queries."""
        # Use optimized query to find all function calls
        for call_node, _captures in find_calls(tree):
            if _treesitter.is_function_call(call_node):
                full_class_path = self.import_resolver.resolve_full_class_path(call_node)
                self._analyze_external_class_ast(full_class_path)

    def resolve_class_name_from_context(
        self, class_name: str, param_classes: dict[str, ParameterizedInfo], document_content: str
    ) -> str | None:
        """Resolve a class name from context, handling both direct class names and variable names using tree-sitter."""
        # If it's already a known param class, return it
        if class_name in param_classes:
            return class_name

        # If it's a variable name, try to find its assignment in the document using tree-sitter
        if document_content:
            # Parse the document with tree-sitter
            tree = _treesitter.parser.parse(document_content, error_recovery=True)

            # Look for assignments like: variable_name = ClassName(...)
            for _assignment_node, captures in find_assignments(tree.root_node):
                # Get the target (left side of assignment)
                target_node = captures.get("target")
                if not target_node:
                    continue

                # Check if the target matches our variable name
                target_name = _treesitter.get_value(target_node)
                if target_name != class_name:
                    continue

                # Get the value (right side of assignment)
                value_node = captures.get("value")
                if not value_node or value_node.type != "call":
                    continue

                # Get the function being called (the class name)
                function_node = None
                if hasattr(value_node, "child_by_field_name"):
                    function_node = value_node.child_by_field_name("function")

                if not function_node:
                    continue

                # Extract the class name from the function node
                assigned_class = self._extract_class_name_from_node(function_node)
                if not assigned_class:
                    continue

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
                            class_info = self._analyze_external_class_ast(full_class_path)
                            if class_info:
                                # Return the original dotted name for external class handling
                                return assigned_class

        return None

    def _extract_class_name_from_node(self, node: Node) -> str | None:
        """Extract a class name from a function node (handles both simple and dotted names)."""
        if node.type == "identifier":
            # Simple class name like: MyClass
            return _treesitter.get_value(node)
        elif node.type == "attribute":
            # Dotted name like: hv.Curve
            # Build the full dotted name by walking the attribute chain
            parts = []
            current = node
            while current and current.type == "attribute":
                # Get the attribute name
                if hasattr(current, "child_by_field_name"):
                    attr_node = current.child_by_field_name("attribute")
                    if attr_node:
                        parts.insert(0, _treesitter.get_value(attr_node))
                    # Move to the object part
                    current = current.child_by_field_name("object")
                else:
                    break

            # Add the final identifier
            if current and current.type == "identifier":
                parts.insert(0, _treesitter.get_value(current))

            return ".".join(parts) if parts else None

        return None
