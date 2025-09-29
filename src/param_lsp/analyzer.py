"""
HoloViz Param Language Server Protocol implementation.
Provides IDE support for Param-based Python code including autocompletion,
hover information, and diagnostics.

This version uses modular components for external class inspection
while preserving all existing functionality.
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

        # Use modular inheritance resolver
        self.inheritance_resolver = InheritanceResolver(
            param_classes=self.param_classes,
            external_param_classes=self.external_param_classes,
            imports=self.imports,
            get_imported_param_class_info_func=self._get_imported_param_class_info,
            analyze_external_class_ast_func=self._analyze_external_class_ast,
            resolve_full_class_path_func=self._resolve_full_class_path,
        )

    def analyze_file(self, content: str, file_path: str | None = None) -> AnalysisResult:
        """Analyze a Python file for Param usage."""
        try:
            # Use parso with error recovery enabled for better handling of incomplete syntax
            tree = parso.parse(content, error_recovery=True)
            self._reset_analysis()
            self._current_file_path = file_path
            self._current_file_content = content

            # Note: parso handles syntax errors internally with error_recovery=True

            # Walk the parse tree to extract parameter information
            parso_utils.walk_tree(tree)
        except Exception as e:
            # If parso completely fails, log and return empty result
            logger.error(f"Failed to parse file: {e}")
            return AnalysisResult(param_classes={}, imports={}, type_errors=[])

        # First pass: collect imports
        for node in parso_utils.walk_tree(tree):
            if node.type == "import_name":
                self._handle_import(node)
            elif node.type == "import_from":
                self._handle_import_from(node)

        # Second pass: collect class definitions in order, respecting inheritance
        class_nodes: list[BaseNode] = [
            cast("BaseNode", node)
            for node in parso_utils.walk_tree(tree)
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

        # Pre-pass: discover all external Parameterized classes using parso
        self._discover_external_param_classes(tree)

        # Perform parameter validation after parsing using modular validator
        self.type_errors = self.validator.check_parameter_types(tree, content.split("\n"))

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

    def _has_attribute_target(self, node: NodeOrLeaf) -> bool:
        """Check if assignment has an attribute target (like obj.attr = value)."""
        for child in parso_utils.get_children(node):
            if child.type in ("power", "atom_expr"):
                # Check if this node has attribute access (trailer with '.')
                for sub_child in parso_utils.get_children(child):
                    if (
                        sub_child.type == "trailer"
                        and parso_utils.get_children(sub_child)
                        and parso_utils.get_value(parso_utils.get_children(sub_child)[0]) == "."
                    ):
                        return True
            elif child.type == "operator" and parso_utils.get_value(child) == "=":
                break
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

    def _format_base(self, base) -> str:
        """Format base class for debugging (parso node)."""
        if base.type == "name":
            value = parso_utils.get_value(base)
            return value if value is not None else "<unknown>"
        elif base.type == "power":
            # Handle dotted names like module.Class
            parts = []
            for child in parso_utils.get_children(base):
                if child.type == "name":
                    parts.append(parso_utils.get_value(child))
                elif child.type == "trailer":
                    parts.extend(
                        [
                            parso_utils.get_value(trailer_child)
                            for trailer_child in parso_utils.get_children(child)
                            if trailer_child.type == "name"
                        ]
                    )
            return ".".join(parts)
        return str(base.type)


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

    def _parse_bounds_format(
        self, bounds: tuple
    ) -> tuple[float | None, float | None, bool, bool] | None:
        """Parse bounds tuple into (min_val, max_val, left_inclusive, right_inclusive).

        Args:
            bounds: Either (min, max) or (min, max, left_inclusive, right_inclusive)

        Returns:
            Tuple of (min_val, max_val, left_inclusive, right_inclusive) or None if invalid
        """
        if len(bounds) == 2:
            min_val, max_val = bounds
            left_inclusive, right_inclusive = True, True  # Default to inclusive
            return min_val, max_val, left_inclusive, right_inclusive
        elif len(bounds) == 4:
            min_val, max_val, left_inclusive, right_inclusive = bounds
            return min_val, max_val, left_inclusive, right_inclusive
        else:
            return None

    def _format_bounds_description(
        self,
        min_val: float | None,
        max_val: float | None,
        left_inclusive: bool,
        right_inclusive: bool,
    ) -> str:
        """Format bounds into a human-readable string with proper bracket notation.

        Args:
            min_val: Minimum value (or None for unbounded)
            max_val: Maximum value (or None for unbounded)
            left_inclusive: Whether left bound is inclusive
            right_inclusive: Whether right bound is inclusive

        Returns:
            Formatted bounds string like "[0, 10]" or "(0, 10)" etc.
        """
        min_str = str(min_val) if min_val is not None else "-∞"
        max_str = str(max_val) if max_val is not None else "∞"
        left_bracket = "[" if left_inclusive else "("
        right_bracket = "]" if right_inclusive else ")"
        return f"{left_bracket}{min_str}, {max_str}{right_bracket}"

    def _check_parameter_types(self, tree: NodeOrLeaf, lines: list[str]) -> None:
        """Check for type errors in parameter assignments."""
        for node in parso_utils.walk_tree(tree):
            if node.type == "classdef":
                self._check_class_parameter_defaults(cast("BaseNode", node), lines)

            # Check runtime parameter assignments like obj.param = value
            elif node.type == "expr_stmt" and parso_utils.is_assignment_stmt(node):
                if self._has_attribute_target(node):
                    self._check_runtime_parameter_assignment_parso(node, lines)

            # Check constructor calls like MyClass(x="A")
            elif node.type in ("power", "atom_expr") and parso_utils.is_function_call(node):
                self._check_constructor_parameter_types(node, lines)

    def _check_class_parameter_defaults(self, class_node: BaseNode, lines: list[str]) -> None:
        """Check parameter default types within a class definition."""
        class_name = parso_utils.get_class_name(class_node)
        if not class_name or class_name not in self.param_classes:
            return

        for assignment_node, target_name in parso_utils.find_all_parameter_assignments(
            class_node, self._is_parameter_assignment
        ):
            self._check_parameter_default_type(assignment_node, target_name, lines)

    def _check_constructor_parameter_types(self, node: NodeOrLeaf, lines: list[str]) -> None:
        """Check for type errors in constructor parameter calls like MyClass(x="A") (parso version)."""
        # Get the class name from the call
        class_name = self._get_instance_class(node)
        if not class_name:
            return

        # Check if this is a valid param class (local or external)
        is_valid_param_class = class_name in self.param_classes or (
            class_name in self.external_param_classes and self.external_param_classes[class_name]
        )

        if not is_valid_param_class:
            return

        # Get keyword arguments from the parso node
        kwargs = get_keyword_arguments(node)

        # Check each keyword argument passed to the constructor
        for param_name, param_value in kwargs.items():
            # Get the expected parameter type
            cls = self._get_parameter_type_from_class(class_name, param_name)
            if not cls:
                continue  # Skip if parameter not found (could be inherited or not a param)

            # Check if None is allowed for this parameter
            inferred_type = self._infer_value_type(param_value)
            if inferred_type is type(None):  # None value
                allow_None = self._get_parameter_allow_None(class_name, param_name)
                if allow_None:
                    continue  # None is allowed, skip further validation
                # If allow_None is False or not specified, continue with normal type checking

            # Check if assigned value matches expected type
            if cls in self.param_type_map:
                expected_types = self.param_type_map[cls]
                if not isinstance(expected_types, tuple):
                    expected_types = (expected_types,)

                # inferred_type was already computed above

                # Special handling for Boolean parameters - they should only accept actual bool values
                if cls == "Boolean" and inferred_type and inferred_type is not bool:
                    # For parso nodes, check if it's a keyword node with True/False
                    is_bool_value = (
                        hasattr(param_value, "type")
                        and param_value.type == "keyword"
                        and parso_utils.get_value(param_value) in ("True", "False")
                    )
                    if not is_bool_value:
                        message = f"Cannot assign {inferred_type.__name__} to Boolean parameter '{param_name}' in {class_name}() constructor (expects True/False)"
                        self._create_type_error(node, message, "constructor-boolean-type-mismatch")
                elif inferred_type and not any(
                    (isinstance(inferred_type, type) and issubclass(inferred_type, t))
                    or inferred_type == t
                    for t in expected_types
                ):
                    message = f"Cannot assign {inferred_type.__name__} to parameter '{param_name}' of type {cls} in {class_name}() constructor (expects {self._format_expected_types(expected_types)})"
                    self._create_type_error(node, message, "constructor-type-mismatch")

            # Check bounds for numeric parameters in constructor calls
            self._check_constructor_bounds(node, class_name, param_name, cls, param_value)

    def _check_constructor_bounds(
        self,
        node: NodeOrLeaf,
        class_name: str,
        param_name: str,
        cls: str,
        param_value: NodeOrLeaf,
    ) -> None:
        """Check if constructor parameter value is within parameter bounds."""
        # Only check bounds for numeric types
        if cls not in ["Number", "Integer"]:
            return

        # Get bounds for this parameter
        bounds = self._get_parameter_bounds(class_name, param_name)
        if not bounds:
            return

        # Extract numeric value from parameter value
        assigned_numeric = extract_numeric_value(param_value)
        if assigned_numeric is None:
            return

        # Parse bounds format
        parsed_bounds = self._parse_bounds_format(bounds)
        if not parsed_bounds:
            return
        min_val, max_val, left_inclusive, right_inclusive = parsed_bounds

        # Check if value is within bounds based on inclusivity
        violates_lower = False
        violates_upper = False

        if min_val is not None:
            if left_inclusive:
                violates_lower = assigned_numeric < min_val
            else:
                violates_lower = assigned_numeric <= min_val

        if max_val is not None:
            if right_inclusive:
                violates_upper = assigned_numeric > max_val
            else:
                violates_upper = assigned_numeric >= max_val

        if violates_lower or violates_upper:
            bound_description = self._format_bounds_description(
                min_val, max_val, left_inclusive, right_inclusive
            )
            message = f"Value {assigned_numeric} for parameter '{param_name}' in {class_name}() constructor is outside bounds {bound_description}"
            self._create_type_error(node, message, "constructor-bounds-violation")

    def _check_parameter_default_type(
        self, node: NodeOrLeaf, param_name: str, lines: list[str]
    ) -> None:
        """Check if parameter default value matches declared type (parso version)."""
        # Find the parameter call on the right side of the assignment
        param_call = None
        for child in parso_utils.get_children(node):
            if child.type in ("power", "atom_expr"):
                param_call = child
                break

        if not param_call:
            return

        # Resolve the actual parameter class type
        param_class_info = resolve_parameter_class(param_call, self.imports)
        if not param_class_info:
            return

        cls = param_class_info["type"]

        # Get default value and allow_None from keyword arguments
        kwargs = get_keyword_arguments(param_call)
        default_value = kwargs.get("default")
        allow_None_node = kwargs.get("allow_None")
        allow_None = (
            extract_boolean_value(allow_None_node)
            if "allow_None" in kwargs and allow_None_node is not None
            else None
        )

        # Param automatically sets allow_None=True when default=None
        if default_value is not None and is_none_value(default_value):
            allow_None = True

        if cls and default_value and cls in self.param_type_map:
            expected_types = self.param_type_map[cls]
            if not isinstance(expected_types, tuple):
                expected_types = (expected_types,)

            inferred_type = self._infer_value_type(default_value)

            # Check if None is allowed for this parameter
            if allow_None and inferred_type is type(None):
                return  # None is allowed, skip further validation

            # Special handling for Boolean parameters - they should only accept actual bool values
            if cls == "Boolean" and inferred_type and inferred_type is not bool:
                # For Boolean parameters, only accept actual boolean values
                if not (
                    default_value.type == "name"
                    and parso_utils.get_value(default_value) in ("True", "False")
                ):
                    message = f"Parameter '{param_name}' of type Boolean expects bool but got {inferred_type.__name__}"
                    self._create_type_error(node, message, "boolean-type-mismatch")
            elif inferred_type and not any(
                (isinstance(inferred_type, type) and issubclass(inferred_type, t))
                or inferred_type == t
                for t in expected_types
            ):
                message = f"Parameter '{param_name}' of type {cls} expects {self._format_expected_types(expected_types)} but got {inferred_type.__name__}"
                self._create_type_error(node, message, "type-mismatch")

        # Check for additional parameter constraints
        self._check_parameter_constraints(node, param_name, lines)

    def _check_runtime_parameter_assignment_parso(
        self, node: NodeOrLeaf, lines: list[str]
    ) -> None:
        """Check runtime parameter assignments like obj.param = value (parso version)."""
        # Extract target and assigned value from parso expr_stmt node
        target = None
        assigned_value = None

        # Look for attribute target and assigned value
        for child in parso_utils.get_children(node):
            if child.type in ("power", "atom_expr"):
                # Check if this is an attribute access (obj.attr)
                has_attribute = False
                for sub_child in parso_utils.get_children(child):
                    if (
                        sub_child.type == "trailer"
                        and parso_utils.get_children(sub_child)
                        and parso_utils.get_value(parso_utils.get_children(sub_child)[0]) == "."
                    ):
                        has_attribute = True
                        break
                if has_attribute:
                    target = child
            elif child.type == "operator" and parso_utils.get_value(child) == "=":
                # Next non-operator child should be the assigned value
                continue
            elif target is not None and child.type != "operator":
                assigned_value = child
                break

        if not target or not assigned_value:
            return

        # Extract parameter name from the attribute access
        param_name = None
        for child in parso_utils.get_children(target):
            if (
                child.type == "trailer"
                and len(parso_utils.get_children(child)) >= 2
                and parso_utils.get_value(parso_utils.get_children(child)[0]) == "."
                and parso_utils.get_children(child)[1].type == "name"
            ):
                param_name = parso_utils.get_value(parso_utils.get_children(child)[1])
                break

        if not param_name:
            return

        # Determine the instance class
        instance_class = None

        # Check if this is a direct instantiation (has parentheses before the dot)
        has_call = False
        for child in parso_utils.get_children(target):
            if (
                child.type == "trailer"
                and len(parso_utils.get_children(child)) >= 2
                and parso_utils.get_value(parso_utils.get_children(child)[0]) == "("
                and parso_utils.get_value(parso_utils.get_children(child)[-1]) == ")"
            ):
                has_call = True
                break

        if has_call:
            # Case: MyClass().param = value (direct instantiation)
            instance_class = self._get_instance_class(target)
        else:
            # Case: instance_var.param = value
            # Try to find which param class has this parameter
            for class_name, class_info in self.param_classes.items():
                if param_name in class_info.parameters:
                    instance_class = class_name
                    break

            # If not found in local classes, check external param classes
            if not instance_class:
                for class_name, class_info in self.external_param_classes.items():
                    if class_info and param_name in class_info.parameters:
                        instance_class = class_name
                        break

        if not instance_class:
            return

        # Check if this is a valid param class
        is_valid_param_class = instance_class in self.param_classes or (
            instance_class in self.external_param_classes
            and self.external_param_classes[instance_class]
        )

        if not is_valid_param_class:
            return

        # Get the parameter type from the class definition
        cls = self._get_parameter_type_from_class(instance_class, param_name)
        if not cls:
            return

        # Check if assigned value matches expected type
        if cls in self.param_type_map:
            expected_types = self.param_type_map[cls]
            if not isinstance(expected_types, tuple):
                expected_types = (expected_types,)

            inferred_type = self._infer_value_type(assigned_value)

            # Check if None is allowed for this parameter
            if inferred_type is type(None):  # None value
                allow_None = self._get_parameter_allow_None(instance_class, param_name)
                if allow_None:
                    return  # None is allowed, skip further validation

            # Special handling for Boolean parameters
            if cls == "Boolean" and inferred_type and inferred_type is not bool:
                # For Boolean parameters, only accept actual boolean values
                if not self._is_boolean_literal(assigned_value):
                    message = f"Cannot assign {inferred_type.__name__} to Boolean parameter '{param_name}' (expects True/False)"
                    self._create_type_error(node, message, "runtime-boolean-type-mismatch")
            elif inferred_type and not any(
                (isinstance(inferred_type, type) and issubclass(inferred_type, t))
                or inferred_type == t
                for t in expected_types
            ):
                message = f"Cannot assign {inferred_type.__name__} to parameter '{param_name}' of type {cls} (expects {self._format_expected_types(expected_types)})"
                self._create_type_error(node, message, "runtime-type-mismatch")

        # Check bounds for numeric parameters
        self._check_runtime_bounds_parso(node, instance_class, param_name, cls, assigned_value)

    def _is_boolean_literal(self, node: NodeOrLeaf) -> bool:
        """Check if a parso node represents a boolean literal (True/False)."""
        return (node.type == "name" and parso_utils.get_value(node) in ("True", "False")) or (
            node.type == "keyword" and parso_utils.get_value(node) in ("True", "False")
        )

    def _check_runtime_bounds_parso(
        self,
        node: NodeOrLeaf,
        instance_class: str,
        param_name: str,
        cls: str,
        assigned_value: NodeOrLeaf,
    ) -> None:
        """Check if assigned value is within parameter bounds (parso version)."""
        # Only check bounds for numeric types
        if cls not in ["Number", "Integer"]:
            return

        # Get bounds for this parameter
        bounds = self._get_parameter_bounds(instance_class, param_name)
        if not bounds:
            return

        # Extract numeric value from assigned value
        assigned_numeric = extract_numeric_value(assigned_value)
        if assigned_numeric is None:
            return

        # Parse bounds format
        parsed_bounds = self._parse_bounds_format(bounds)
        if not parsed_bounds:
            return
        min_val, max_val, left_inclusive, right_inclusive = parsed_bounds

        # Check if value is within bounds based on inclusivity
        violates_lower = False
        violates_upper = False

        if min_val is not None:
            if left_inclusive:
                violates_lower = assigned_numeric < min_val
            else:
                violates_lower = assigned_numeric <= min_val

        if max_val is not None:
            if right_inclusive:
                violates_upper = assigned_numeric > max_val
            else:
                violates_upper = assigned_numeric >= max_val

        if violates_lower or violates_upper:
            bound_description = self._format_bounds_description(
                min_val, max_val, left_inclusive, right_inclusive
            )
            message = f"Value {assigned_numeric} for parameter '{param_name}' is outside bounds {bound_description}"
            self._create_type_error(node, message, "bounds-violation")

    def _get_parameter_bounds(self, class_name: str, param_name: str) -> tuple | None:
        """Get parameter bounds from a class definition."""
        # Check local classes first
        if class_name in self.param_classes:
            param_info = self.param_classes[class_name].get_parameter(param_name)
            return param_info.bounds if param_info else None

        # Check external classes
        class_info = self.external_param_classes.get(class_name)
        if class_info:
            param_info = class_info.get_parameter(param_name)
            return param_info.bounds if param_info else None

        return None

    def _get_instance_class(self, call_node) -> str | None:
        """Get the class name from an instance creation call (parso version)."""
        # For parso nodes, we need to find the function name from the power/atom_expr structure
        if call_node.type in ("power", "atom_expr"):
            # First try to resolve the full class path for external classes
            full_class_path = self._resolve_full_class_path(call_node)
            if full_class_path:
                # Check if this is an external Parameterized class
                class_info = self._analyze_external_class_ast(full_class_path)
                if class_info:
                    # Return the full path as the class identifier for external classes
                    return full_class_path

            # If not an external class, look for local class names
            # We need to find the class name that's actually being called
            # For Outer.Inner(), we want "Inner", not "Outer"

            # Find the last name before a function call (parentheses trailer)
            last_name = None
            for child in parso_utils.get_children(call_node):
                if child.type == "name":
                    last_name = parso_utils.get_value(child)
                elif child.type == "trailer":
                    if (
                        len(parso_utils.get_children(child)) >= 2
                        and parso_utils.get_children(child)[1].type == "name"
                    ):
                        # This is a dot access like .Inner
                        last_name = parso_utils.get_value(parso_utils.get_children(child)[1])
                    elif (
                        len(parso_utils.get_children(child)) >= 1
                        and parso_utils.get_children(child)[0].type == "operator"
                        and parso_utils.get_value(parso_utils.get_children(child)[0]) == "("
                    ):
                        # This is the function call parentheses - return the last name we found
                        return last_name

            # If we found a name but no explicit function call, return the last name
            return last_name
        return None

    def _resolve_full_class_path(self, base) -> str | None:
        """Resolve the full class path from a parso power/atom_expr node like pn.widgets.IntSlider."""
        parts = []
        for child in parso_utils.get_children(base):
            if child.type == "name":
                parts.append(parso_utils.get_value(child))
            elif child.type == "trailer":
                parts.extend(
                    [
                        parso_utils.get_value(trailer_child)
                        for trailer_child in parso_utils.get_children(child)
                        if trailer_child.type == "name"
                    ]
                )

        if parts:
            # Resolve the root module through imports
            root_alias = parts[0]
            if root_alias in self.imports:
                full_module_name = self.imports[root_alias]
                # Replace the alias with the full module name
                parts[0] = full_module_name
                return ".".join(parts)
            else:
                # Use the alias directly if no import mapping found
                return ".".join(parts)

        return None

    def _get_parameter_type_from_class(self, class_name: str, param_name: str) -> str | None:
        """Get the parameter type from a class definition."""
        # Check local classes first
        if class_name in self.param_classes:
            param_info = self.param_classes[class_name].get_parameter(param_name)
            return param_info.cls if param_info else None

        # Check external classes
        class_info = self.external_param_classes.get(class_name)
        if class_info:
            param_info = class_info.get_parameter(param_name)
            return param_info.cls if param_info else None

        return None

    def _get_parameter_allow_None(self, class_name: str, param_name: str) -> bool:
        """Get the allow_None setting for a parameter from a class definition."""
        # Check local classes first
        if class_name in self.param_classes:
            param_info = self.param_classes[class_name].get_parameter(param_name)
            return param_info.allow_None if param_info else False

        # Check external classes
        class_info = self.external_param_classes.get(class_name)
        if class_info:
            param_info = class_info.get_parameter(param_name)
            return param_info.allow_None if param_info else False

        return False

    def _format_expected_types(self, expected_types: tuple) -> str:
        """Format expected types for error messages."""
        if len(expected_types) == 1:
            return expected_types[0].__name__
        else:
            type_names = [t.__name__ for t in expected_types]
            return " or ".join(type_names)

    def _create_type_error(self, node, message: str, code: str, severity: str = "error") -> None:
        """Helper function to create and append a type error (parso version)."""
        # Get position information from parso node
        if hasattr(node, "start_pos"):
            line = node.start_pos[0] - 1  # Convert to 0-based
            col = node.start_pos[1]
            end_line = node.end_pos[0] - 1 if hasattr(node, "end_pos") else line
            end_col = node.end_pos[1] if hasattr(node, "end_pos") else col
        else:
            # Fallback if position info is not available
            line = 0
            col = 0
            end_line = 0
            end_col = 0

        self.type_errors.append(
            {
                "line": line,
                "col": col,
                "end_line": end_line,
                "end_col": end_col,
                "message": message,
                "severity": severity,
                "code": code,
            }
        )

    def _infer_value_type(self, node: NodeOrLeaf) -> type | None:
        """Infer Python type from parso node."""
        if hasattr(node, "type"):
            if node.type == "number":
                # Check if it's a float or int
                value = parso_utils.get_value(node)
                if value is None:
                    return None
                if "." in value:
                    return float
                else:
                    return int
            elif node.type == "string":
                return str
            elif node.type == "name":
                if parso_utils.get_value(node) in {"True", "False"}:
                    return bool
                elif parso_utils.get_value(node) == "None":
                    return type(None)
                # Could be a variable - would need more sophisticated analysis
                return None
            elif node.type == "keyword":
                if parso_utils.get_value(node) in {"True", "False"}:
                    return bool
                elif parso_utils.get_value(node) == "None":
                    return type(None)
                return None
            elif node.type == "atom":
                # Check for list, dict, tuple
                if (
                    parso_utils.get_children(node)
                    and parso_utils.get_value(parso_utils.get_children(node)[0]) == "["
                ):
                    return list
                elif (
                    parso_utils.get_children(node)
                    and parso_utils.get_value(parso_utils.get_children(node)[0]) == "{"
                ):
                    return dict
                elif (
                    parso_utils.get_children(node)
                    and parso_utils.get_value(parso_utils.get_children(node)[0]) == "("
                ):
                    return tuple
        return None

    def _check_parameter_constraints(
        self, node: NodeOrLeaf, param_name: str, lines: list[str]
    ) -> None:
        """Check for parameter-specific constraints (parso version)."""
        # Find the parameter call on the right side of the assignment
        param_call = None
        for child in parso_utils.get_children(node):
            if child.type in ("power", "atom_expr"):
                param_call = child
                break

        if not param_call:
            return

        # Resolve the actual parameter class type for constraint checking
        param_class_info = resolve_parameter_class(param_call, self.imports)
        if not param_class_info:
            return

        resolved_cls = param_class_info["type"]

        # Get keyword arguments
        kwargs = get_keyword_arguments(param_call)

        # Check bounds for Number/Integer parameters
        if resolved_cls in ["Number", "Integer"]:
            bounds_node = kwargs.get("bounds")
            inclusive_bounds_node = kwargs.get("inclusive_bounds")
            default_value = kwargs.get("default")

            inclusive_bounds = (True, True)  # Default to inclusive

            # Parse inclusive_bounds if present
            if inclusive_bounds_node and inclusive_bounds_node.type == "atom":
                # Parse (True, False) pattern
                for child in parso_utils.get_children(inclusive_bounds_node):
                    if child.type == "testlist_comp":
                        elements = [
                            c
                            for c in parso_utils.get_children(child)
                            if c.type in ("name", "keyword")
                        ]
                        if len(elements) >= 2:
                            left_inclusive = extract_boolean_value(elements[0])
                            right_inclusive = extract_boolean_value(elements[1])
                            if left_inclusive is not None and right_inclusive is not None:
                                inclusive_bounds = (left_inclusive, right_inclusive)

            # Parse bounds if present
            if bounds_node and bounds_node.type == "atom":
                # Parse (min, max) pattern
                for child in parso_utils.get_children(bounds_node):
                    if child.type == "testlist_comp":
                        elements = [
                            c
                            for c in parso_utils.get_children(child)
                            if c.type in ("number", "name", "factor")
                        ]
                        if len(elements) >= 2:
                            try:
                                min_val = extract_numeric_value(elements[0])
                                max_val = extract_numeric_value(elements[1])

                                if (
                                    min_val is not None
                                    and max_val is not None
                                    and min_val >= max_val
                                ):
                                    message = f"Parameter '{param_name}' has invalid bounds: min ({min_val}) >= max ({max_val})"
                                    self._create_type_error(node, message, "invalid-bounds")

                                # Check if default value violates bounds
                                if (
                                    default_value is not None
                                    and min_val is not None
                                    and max_val is not None
                                ):
                                    default_numeric = extract_numeric_value(default_value)
                                    if default_numeric is not None:
                                        left_inclusive, right_inclusive = inclusive_bounds

                                        # Check bounds violation
                                        violates_lower = (
                                            (default_numeric < min_val)
                                            if left_inclusive
                                            else (default_numeric <= min_val)
                                        )
                                        violates_upper = (
                                            (default_numeric > max_val)
                                            if right_inclusive
                                            else (default_numeric >= max_val)
                                        )

                                        if violates_lower or violates_upper:
                                            bound_description = self._format_bounds_description(
                                                min_val, max_val, left_inclusive, right_inclusive
                                            )
                                            message = f"Default value {default_numeric} for parameter '{param_name}' is outside bounds {bound_description}"
                                            self._create_type_error(
                                                node, message, "default-bounds-violation"
                                            )

                            except (ValueError, TypeError):
                                pass

        # Check for empty lists/tuples with List/Tuple parameters
        elif resolved_cls in ["List", "Tuple"]:
            default_value = kwargs.get("default")
            if default_value and default_value.type == "atom":
                # Check if it's an empty list or tuple
                # Get all child values to check for empty containers
                child_values = [
                    parso_utils.get_value(child)
                    for child in parso_utils.get_children(default_value)
                    if hasattr(child, "value")
                ]
                is_empty_list = child_values == ["[", "]"]
                is_empty_tuple = child_values == ["(", ")"]

                if (is_empty_list or is_empty_tuple) and "bounds" in kwargs:
                    message = f"Parameter '{param_name}' has empty default but bounds specified"
                    self._create_type_error(node, message, "empty-default-with-bounds", "warning")

    def _resolve_module_path(
        self, module_name: str, current_file_path: str | None = None
    ) -> str | None:
        """Resolve a module name to a file path."""
        if not self.workspace_root:
            return None

        # Handle relative imports
        if module_name.startswith("."):
            if not current_file_path:
                return None
            current_dir = Path(current_file_path).parent
            # Convert relative module name to absolute path
            parts = module_name.lstrip(".").split(".")
            target_path = current_dir
            for part in parts:
                if part:
                    target_path = target_path / part

            # Try .py file
            py_file = target_path.with_suffix(".py")
            if py_file.exists():
                return str(py_file)

            # Try package __init__.py
            init_file = target_path / "__init__.py"
            if init_file.exists():
                return str(init_file)

            return None

        # Handle absolute imports
        parts = module_name.split(".")

        # Try in workspace root
        target_path = self.workspace_root
        for part in parts:
            target_path = target_path / part

        # Try .py file
        py_file = target_path.with_suffix(".py")
        if py_file.exists():
            return str(py_file)

        # Try package __init__.py
        init_file = target_path / "__init__.py"
        if init_file.exists():
            return str(init_file)

        # Try searching in Python path (for installed packages)
        try:
            spec = importlib.util.find_spec(module_name)
            if spec and spec.origin and spec.origin.endswith(".py"):
                return spec.origin
        except (ImportError, ValueError, ModuleNotFoundError):
            pass

        return None

    def _analyze_imported_module(
        self, module_name: str, current_file_path: str | None = None
    ) -> AnalysisResult:
        """Analyze an imported module and cache the results."""
        # Check cache first
        if module_name in self.module_cache:
            return self.module_cache[module_name]

        # Resolve module path
        module_path = self._resolve_module_path(module_name, current_file_path)
        if not module_path:
            return AnalysisResult(param_classes={}, imports={}, type_errors=[])

        # Check file cache
        if module_path in self.file_cache:
            result = self.file_cache[module_path]
            self.module_cache[module_name] = result
            return result

        # Read and analyze the module
        try:
            with open(module_path, encoding="utf-8") as f:
                content = f.read()

            # Create a new analyzer instance for the imported module to avoid conflicts
            module_analyzer = ParamAnalyzer(
                str(self.workspace_root) if self.workspace_root else None
            )
            result = module_analyzer.analyze_file(content)

            # Cache the result
            self.file_cache[module_path] = result
            self.module_cache[module_name] = result

            return result
        except (OSError, UnicodeDecodeError) as e:
            logger.warning(f"Failed to analyze module {module_name} at {module_path}: {e}")
            return AnalysisResult(param_classes={}, imports={}, type_errors=[])

    def _get_imported_param_class_info(
        self, class_name: str, import_name: str, current_file_path: str | None = None
    ) -> ParameterizedInfo | None:
        """Get parameter information for a class imported from another module."""
        # Get the full module name from imports
        full_import_name = self.imports.get(import_name)
        if not full_import_name:
            return None

        # Parse the import to get module name and class name
        if "." in full_import_name:
            # Handle "from module import Class" -> "module.Class"
            module_name, imported_class_name = full_import_name.rsplit(".", 1)
        else:
            # Handle "import module" -> "module"
            module_name = full_import_name
            imported_class_name = class_name

        # Analyze the imported module
        module_analysis = self._analyze_imported_module(module_name, current_file_path)
        if not module_analysis:
            return None

        # Check if the class exists in the imported module
        param_classes_dict = module_analysis.get("param_classes", {})
        if isinstance(param_classes_dict, dict) and imported_class_name in param_classes_dict:
            class_info = param_classes_dict[imported_class_name]
            # If it's a ParameterizedInfo object, return it
            if hasattr(class_info, "parameters"):
                return class_info

        return None

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

    def _discover_external_param_classes(self, tree: NodeOrLeaf) -> None:
        """Pre-pass to discover all external Parameterized classes using parso analysis."""
        for node in parso_utils.walk_tree(tree):
            if node.type in ("power", "atom_expr") and parso_utils.is_function_call(node):
                full_class_path = self._resolve_full_class_path(node)
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
