"""
HoloViz Param Language Server Protocol implementation.
Provides IDE support for Param-based Python code including autocompletion,
hover information, and diagnostics.
"""

from __future__ import annotations

import ast
import inspect
import logging
from typing import Any
from urllib.parse import urlparse

# from pygls.protocol import LanguageServerProtocol
import param
from lsprotocol.types import (
    CompletionItem,
    CompletionItemKind,
    CompletionList,
    CompletionOptions,
    CompletionParams,
    Diagnostic,
    DiagnosticOptions,
    DiagnosticSeverity,
    DidChangeTextDocumentParams,
    DidOpenTextDocumentParams,
    Hover,
    HoverParams,
    InitializeParams,
    InitializeResult,
    MarkupContent,
    MarkupKind,
    Position,
    Range,
    ServerCapabilities,
    TextDocumentSyncKind,
)
from pygls.server import LanguageServer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ParamAnalyzer:
    """Analyzes Python code for Param usage patterns."""

    def __init__(self):
        self.param_classes: set[str] = set()
        self.param_parameters: dict[str, list[str]] = {}
        # class_name -> {param_name: param_type}
        self.param_parameter_types: dict[str, dict[str, str]] = {}
        # class_name -> {param_name: (min, max)}
        self.param_parameter_bounds: dict[str, dict[str, tuple]] = {}
        # class_name -> {param_name: doc_string}
        self.param_parameter_docs: dict[str, dict[str, str]] = {}
        self.imports: dict[str, str] = {}
        self.type_errors: list[dict[str, Any]] = []
        self.param_type_map = {
            "Number": (int, float),
            "Integer": int,
            "String": str,
            "Boolean": bool,
            "List": list,
            "Tuple": tuple,
            "Dict": dict,
            "Array": (list, tuple),
            "Range": (int, float),
            "Date": str,
            "CalendarDate": str,
            "Filename": str,
            "Foldername": str,
            "Path": str,
            "Color": str,
        }

    def analyze_file(self, content: str) -> dict[str, Any]:
        """Analyze a Python file for Param usage."""
        try:
            tree = ast.parse(content)
            self._reset_analysis()

            # First pass: collect imports
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self._handle_import(node)
                elif isinstance(node, ast.ImportFrom):
                    self._handle_import_from(node)

            # Second pass: collect class definitions in order, respecting inheritance
            class_nodes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]

            # Process classes in dependency order (parents before children)
            processed_classes = set()
            while len(processed_classes) < len(class_nodes):
                progress_made = False
                for node in class_nodes:
                    if node.name in processed_classes:
                        continue

                    # Check if all parent classes are processed or are external param classes
                    can_process = True
                    for base in node.bases:
                        if isinstance(base, ast.Name):
                            parent_name = base.id
                            # If it's a class defined in this file and not processed yet, wait
                            if (
                                any(cn.name == parent_name for cn in class_nodes)
                                and parent_name not in processed_classes
                            ):
                                can_process = False
                                break

                    if can_process:
                        self._handle_class_def(node)
                        processed_classes.add(node.name)
                        progress_made = True

                # Prevent infinite loop if there are circular dependencies
                if not progress_made:
                    # Process remaining classes anyway
                    for node in class_nodes:
                        if node.name not in processed_classes:
                            self._handle_class_def(node)
                            processed_classes.add(node.name)
                    break

            # Perform type inference after parsing
            self._check_parameter_types(tree, content.split("\n"))

            return {
                "param_classes": self.param_classes,
                "param_parameters": self.param_parameters,
                "param_parameter_types": self.param_parameter_types,
                "param_parameter_bounds": self.param_parameter_bounds,
                "param_parameter_docs": self.param_parameter_docs,
                "imports": self.imports,
                "type_errors": self.type_errors,
            }
        except SyntaxError as e:
            logger.error(f"Syntax error in file: {e}")
            return {}

    def _reset_analysis(self):
        """Reset analysis state."""
        self.param_classes.clear()
        self.param_parameters.clear()
        self.param_parameter_types.clear()
        self.param_parameter_bounds.clear()
        self.param_parameter_docs.clear()
        self.imports.clear()
        self.type_errors.clear()

    def _handle_import(self, node: ast.Import):
        """Handle 'import' statements."""
        for alias in node.names:
            self.imports[alias.asname or alias.name] = alias.name

    def _handle_import_from(self, node: ast.ImportFrom):
        """Handle 'from ... import ...' statements."""
        if node.module:
            for alias in node.names:
                imported_name = alias.asname or alias.name
                full_name = f"{node.module}.{alias.name}"
                self.imports[imported_name] = full_name

    def _handle_class_def(self, node: ast.ClassDef):
        """Handle class definitions that might inherit from param.Parameterized."""
        # Check if class inherits from param.Parameterized (directly or indirectly)
        is_param_class = False
        for base in node.bases:
            if self._is_param_base(base):
                is_param_class = True
                break

        if is_param_class:
            self.param_classes.add(node.name)
            parameters, parameter_types, parameter_bounds, parameter_docs = (
                self._extract_parameters(node)
            )

            # For inherited classes, we need to collect parameters from parent classes too
            # Get parent class parameters and merge them
            (
                parent_parameters,
                parent_parameter_types,
                parent_parameter_bounds,
                parent_parameter_docs,
            ) = self._collect_inherited_parameters(node)

            # Merge parent parameters with current class parameters
            all_parameters = parent_parameters + parameters
            all_parameter_types = {**parent_parameter_types, **parameter_types}
            all_parameter_bounds = {**parent_parameter_bounds, **parameter_bounds}
            all_parameter_docs = {**parent_parameter_docs, **parameter_docs}

            self.param_parameters[node.name] = all_parameters
            self.param_parameter_types[node.name] = all_parameter_types
            self.param_parameter_bounds[node.name] = all_parameter_bounds
            self.param_parameter_docs[node.name] = all_parameter_docs

    def _format_base(self, base: ast.expr) -> str:
        """Format base class for debugging."""
        if isinstance(base, ast.Name):
            return base.id
        elif isinstance(base, ast.Attribute) and isinstance(base.value, ast.Name):
            return f"{base.value.id}.{base.attr}"
        return str(type(base))

    def _is_param_base(self, base: ast.expr) -> bool:
        """Check if a base class is param.Parameterized or similar."""
        if isinstance(base, ast.Name):
            # Check if it's a direct param.Parameterized import
            if base.id in ["Parameterized"] and "param" in self.imports.values():
                return True
            # Check if it's a known param class (from inheritance)
            return base.id in self.param_classes
        elif isinstance(base, ast.Attribute) and isinstance(base.value, ast.Name):
            module = base.value.id
            return (module == "param" and base.attr == "Parameterized") or (
                module in self.imports
                and self.imports[module].endswith("param")
                and base.attr == "Parameterized"
            )
        return False

    def _collect_inherited_parameters(
        self, node: ast.ClassDef
    ) -> tuple[list[str], dict[str, str], dict[str, tuple], dict[str, str]]:
        """Collect parameters from parent classes in inheritance hierarchy."""
        inherited_parameters = []
        inherited_parameter_types = {}
        inherited_parameter_bounds = {}
        inherited_parameter_docs = {}

        for base in node.bases:
            if isinstance(base, ast.Name):
                parent_class_name = base.id
                if parent_class_name in self.param_classes:
                    # Get parameters from the parent class
                    parent_params = self.param_parameters.get(parent_class_name, [])
                    parent_types = self.param_parameter_types.get(parent_class_name, {})
                    parent_bounds = self.param_parameter_bounds.get(parent_class_name, {})
                    parent_docs = self.param_parameter_docs.get(parent_class_name, {})

                    # Add parent parameters (avoid duplicates)
                    for param in parent_params:
                        if param not in inherited_parameters:
                            inherited_parameters.append(param)
                        if param in parent_types:
                            inherited_parameter_types[param] = parent_types[param]
                        if param in parent_bounds:
                            inherited_parameter_bounds[param] = parent_bounds[param]
                        if param in parent_docs:
                            inherited_parameter_docs[param] = parent_docs[param]

        return (
            inherited_parameters,
            inherited_parameter_types,
            inherited_parameter_bounds,
            inherited_parameter_docs,
        )

    def _extract_parameters(
        self, node: ast.ClassDef
    ) -> tuple[list[str], dict[str, str], dict[str, tuple], dict[str, str]]:
        """Extract parameter definitions from a Param class."""
        parameters = []
        parameter_types = {}
        parameter_bounds = {}
        parameter_docs = {}
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and self._is_parameter_assignment(item.value):
                        param_name = target.id
                        parameters.append(param_name)

                        # Get parameter type
                        if isinstance(item.value, ast.Call):
                            param_class_info = self._resolve_parameter_class(item.value.func)
                            if param_class_info:
                                parameter_types[param_name] = param_class_info["type"]

                        # Get bounds if present
                        if isinstance(item.value, ast.Call):
                            bounds = self._extract_bounds_from_call(item.value)
                            if bounds:
                                parameter_bounds[param_name] = bounds

                            # Get doc string if present
                            doc_string = self._extract_doc_from_call(item.value)
                            if doc_string is not None:
                                parameter_docs[param_name] = doc_string

        return parameters, parameter_types, parameter_bounds, parameter_docs

    def _extract_bounds_from_call(self, call_node: ast.Call) -> tuple | None:
        """Extract bounds from a parameter call."""
        bounds_info = None
        inclusive_bounds = (True, True)  # Default to inclusive

        for keyword in call_node.keywords:
            if keyword.arg == "bounds":
                if isinstance(keyword.value, ast.Tuple) and len(keyword.value.elts) == 2:
                    min_val = self._extract_numeric_value(keyword.value.elts[0])
                    max_val = self._extract_numeric_value(keyword.value.elts[1])
                    if min_val is not None and max_val is not None:
                        bounds_info = (min_val, max_val)
            elif (
                keyword.arg == "inclusive_bounds"
                and isinstance(keyword.value, ast.Tuple)
                and len(keyword.value.elts) == 2
            ):
                # Extract boolean values for inclusive bounds
                left_inclusive = self._extract_boolean_value(keyword.value.elts[0])
                right_inclusive = self._extract_boolean_value(keyword.value.elts[1])
                if left_inclusive is not None and right_inclusive is not None:
                    inclusive_bounds = (left_inclusive, right_inclusive)

        if bounds_info:
            # Return (min, max, left_inclusive, right_inclusive)
            return (*bounds_info, *inclusive_bounds)
        return None

    def _extract_doc_from_call(self, call_node: ast.Call) -> str | None:
        """Extract doc string from a parameter call."""
        for keyword in call_node.keywords:
            if keyword.arg == "doc":
                return self._extract_string_value(keyword.value)
        return None

    def _extract_string_value(self, node: ast.expr) -> str | None:
        """Extract string value from AST node."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    def _extract_boolean_value(self, node: ast.expr) -> bool | None:
        """Extract boolean value from AST node."""
        if isinstance(node, ast.Constant) and isinstance(node.value, bool):
            return node.value
        return None

    def _is_parameter_assignment(self, value: ast.expr) -> bool:
        """Check if an assignment looks like a parameter definition."""
        if isinstance(value, ast.Call):
            param_class_info = self._resolve_parameter_class(value.func)
            if param_class_info:
                param_type = param_class_info["type"]
                param_module = param_class_info.get("module")

                # Common param types
                param_types = {
                    "Parameter",
                    "Number",
                    "Integer",
                    "String",
                    "Boolean",
                    "List",
                    "Tuple",
                    "Dict",
                    "Array",
                    "DataFrame",
                    "Series",
                    "Range",
                    "Date",
                    "CalendarDate",
                    "Filename",
                    "Foldername",
                    "Path",
                    "Color",
                    "Composite",
                    "Dynamic",
                    "Event",
                    "Action",
                    "FileSelector",
                    "ListSelector",
                    "ObjectSelector",
                }

                # If we have module info, verify it's from param
                if param_module and "param" in param_module:
                    return param_type in param_types
                # If no module but type matches and we have param imports, likely a param type
                elif (
                    param_module is None
                    and param_type in param_types
                    and any("param" in imp for imp in self.imports.values())
                ):
                    return True
                # Direct param.X() call
                elif param_module == "param":
                    return param_type in param_types

        return False

    def _check_parameter_types(self, tree: ast.AST, lines: list[str]):
        """Check for type errors in parameter assignments."""
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in self.param_classes:
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name) and self._is_parameter_assignment(
                                item.value
                            ):
                                self._check_parameter_default_type(item, target.id, lines)

            # Check runtime parameter assignments like obj.param = value
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Attribute):
                        self._check_runtime_parameter_assignment(node, target, lines)

    def _check_parameter_default_type(self, node: ast.Assign, param_name: str, lines: list[str]):
        """Check if parameter default value matches declared type."""
        if not isinstance(node.value, ast.Call):
            return

        # Resolve the actual parameter class type
        param_class_info = self._resolve_parameter_class(node.value.func)
        if not param_class_info:
            return

        param_type = param_class_info["type"]
        param_class_info.get("module")

        # Get default value from keyword arguments
        default_value = None
        for keyword in node.value.keywords:
            if keyword.arg == "default":
                default_value = keyword.value
                break

        if param_type and default_value and param_type in self.param_type_map:
            expected_types = self.param_type_map[param_type]
            if not isinstance(expected_types, tuple):
                expected_types = (expected_types,)

            inferred_type = self._infer_value_type(default_value)

            # Special handling for Boolean parameters - they should only accept actual bool values
            if param_type == "Boolean" and inferred_type and inferred_type is not bool:
                # For Boolean parameters, only accept actual boolean values
                if not (
                    isinstance(default_value, ast.Constant)
                    and isinstance(default_value.value, bool)
                ):
                    self.type_errors.append(
                        {
                            "line": node.lineno - 1,  # Convert to 0-based
                            "col": node.col_offset,
                            "end_line": node.end_lineno - 1
                            if node.end_lineno
                            else node.lineno - 1,
                            "end_col": node.end_col_offset
                            if node.end_col_offset
                            else node.col_offset,
                            "message": f"Parameter '{param_name}' of type Boolean expects bool but got {inferred_type.__name__}",
                            "severity": "error",
                            "code": "boolean-type-mismatch",
                        }
                    )
            elif inferred_type and not any(
                (isinstance(inferred_type, type) and issubclass(inferred_type, t))
                or inferred_type == t
                for t in expected_types
            ):
                self.type_errors.append(
                    {
                        "line": node.lineno - 1,  # Convert to 0-based
                        "col": node.col_offset,
                        "end_line": node.end_lineno - 1 if node.end_lineno else node.lineno - 1,
                        "end_col": node.end_col_offset if node.end_col_offset else node.col_offset,
                        "message": f"Parameter '{param_name}' of type {param_type} expects {self._format_expected_types(expected_types)} but got {inferred_type.__name__}",
                        "severity": "error",
                        "code": "type-mismatch",
                    }
                )

        # Check for additional parameter constraints
        self._check_parameter_constraints(node, param_name, lines)

    def _check_runtime_parameter_assignment(
        self, node: ast.Assign, target: ast.Attribute, lines: list[str]
    ):
        """Check runtime parameter assignments like obj.param = value."""
        instance_class = None
        param_name = target.attr
        assigned_value = node.value

        if isinstance(target.value, ast.Call):
            # Case: MyClass().x = value
            instance_class = self._get_instance_class(target.value)
        elif isinstance(target.value, ast.Name):
            # Case: instance_var.x = value
            # We need to infer the class from context or assume it could be any param class
            # For now, check if the parameter name exists in any param class
            for class_name in self.param_classes:
                if param_name in self.param_parameters.get(class_name, []):
                    instance_class = class_name
                    break

        if not instance_class or instance_class not in self.param_classes:
            return

        # Get the parameter type from the class definition
        param_type = self._get_parameter_type_from_class(instance_class, param_name)
        if not param_type:
            return

        # Check if assigned value matches expected type
        if param_type in self.param_type_map:
            expected_types = self.param_type_map[param_type]
            if not isinstance(expected_types, tuple):
                expected_types = (expected_types,)

            inferred_type = self._infer_value_type(assigned_value)

            # Special handling for Boolean parameters - they should only accept actual bool values
            if param_type == "Boolean" and inferred_type and inferred_type is not bool:
                # For Boolean parameters, only accept actual boolean values
                if not (
                    isinstance(assigned_value, ast.Constant)
                    and isinstance(assigned_value.value, bool)
                ):
                    self.type_errors.append(
                        {
                            "line": node.lineno - 1,  # Convert to 0-based
                            "col": node.col_offset,
                            "end_line": node.end_lineno - 1
                            if node.end_lineno
                            else node.lineno - 1,
                            "end_col": node.end_col_offset
                            if node.end_col_offset
                            else node.col_offset,
                            "message": f"Cannot assign {inferred_type.__name__} to Boolean parameter '{param_name}' (expects True/False)",
                            "severity": "error",
                            "code": "runtime-boolean-type-mismatch",
                        }
                    )
            elif inferred_type and not any(
                (isinstance(inferred_type, type) and issubclass(inferred_type, t))
                or inferred_type == t
                for t in expected_types
            ):
                self.type_errors.append(
                    {
                        "line": node.lineno - 1,  # Convert to 0-based
                        "col": node.col_offset,
                        "end_line": node.end_lineno - 1 if node.end_lineno else node.lineno - 1,
                        "end_col": node.end_col_offset if node.end_col_offset else node.col_offset,
                        "message": f"Cannot assign {inferred_type.__name__} to parameter '{param_name}' of type {param_type} (expects {self._format_expected_types(expected_types)})",
                        "severity": "error",
                        "code": "runtime-type-mismatch",
                    }
                )

        # Check bounds for numeric parameters
        self._check_runtime_bounds(node, instance_class, param_name, param_type, assigned_value)

    def _check_runtime_bounds(
        self,
        node: ast.Assign,
        instance_class: str,
        param_name: str,
        param_type: str,
        assigned_value: ast.expr,
    ):
        """Check if assigned value is within parameter bounds."""
        # Only check bounds for numeric types
        if param_type not in ["Number", "Integer"]:
            return

        # Get bounds for this parameter
        bounds = self._get_parameter_bounds(instance_class, param_name)
        if not bounds:
            return

        # Extract numeric value from assigned value
        assigned_numeric = self._extract_numeric_value(assigned_value)
        if assigned_numeric is None:
            return

        # Handle both old format (min, max) and new format (min, max, left_inclusive, right_inclusive)
        if len(bounds) == 2:
            min_val, max_val = bounds
            left_inclusive, right_inclusive = True, True  # Default to inclusive
        elif len(bounds) == 4:
            min_val, max_val, left_inclusive, right_inclusive = bounds
        else:
            return

        # Check if value is within bounds based on inclusivity
        bound_description = f"{'[' if left_inclusive else '('}{min_val}, {max_val}{']' if right_inclusive else ')'}"

        if left_inclusive:
            violates_lower = assigned_numeric < min_val
        else:
            violates_lower = assigned_numeric <= min_val

        if right_inclusive:
            violates_upper = assigned_numeric > max_val
        else:
            violates_upper = assigned_numeric >= max_val

        if violates_lower or violates_upper:
            self.type_errors.append(
                {
                    "line": node.lineno - 1,
                    "col": node.col_offset,
                    "end_line": node.end_lineno - 1 if node.end_lineno else node.lineno - 1,
                    "end_col": node.end_col_offset if node.end_col_offset else node.col_offset,
                    "message": f"Value {assigned_numeric} for parameter '{param_name}' is outside bounds {bound_description}",
                    "severity": "error",
                    "code": "bounds-violation",
                }
            )

    def _get_parameter_bounds(self, class_name: str, param_name: str) -> tuple | None:
        """Get parameter bounds from a class definition."""
        if class_name in self.param_parameter_bounds:
            return self.param_parameter_bounds[class_name].get(param_name)
        return None

    def _get_instance_class(self, call_node: ast.Call) -> str | None:
        """Get the class name from an instance creation call."""
        if isinstance(call_node.func, ast.Name):
            return call_node.func.id
        elif isinstance(call_node.func, ast.Attribute):
            return call_node.func.attr
        return None

    def _get_parameter_type_from_class(self, class_name: str, param_name: str) -> str | None:
        """Get the parameter type from a class definition."""
        if class_name in self.param_parameter_types:
            return self.param_parameter_types[class_name].get(param_name)
        return None

    def _resolve_parameter_class(self, func_node: ast.expr) -> dict[str, str | None] | None:
        """Resolve the actual parameter class from the function call."""
        if isinstance(func_node, ast.Name):
            # Direct reference like Integer()
            class_name = func_node.id
            return {"type": class_name, "module": None}

        elif isinstance(func_node, ast.Attribute):
            # Attribute reference like param.Integer() or p.Integer()
            if isinstance(func_node.value, ast.Name):
                module_alias = func_node.value.id
                class_name = func_node.attr

                # Check if this is a known param module
                if module_alias in self.imports:
                    full_module_name = self.imports[module_alias]
                    if "param" in full_module_name:
                        return {"type": class_name, "module": full_module_name}
                elif module_alias == "param":
                    return {"type": class_name, "module": "param"}

        return None

    def _format_expected_types(self, expected_types: tuple) -> str:
        """Format expected types for error messages."""
        if len(expected_types) == 1:
            return expected_types[0].__name__
        else:
            type_names = [t.__name__ for t in expected_types]
            return " or ".join(type_names)

    def _infer_value_type(self, node: ast.expr) -> type | None:
        """Infer Python type from AST node."""
        if isinstance(node, ast.Constant):
            return type(node.value)
        elif isinstance(node, ast.List):
            return list
        elif isinstance(node, ast.Tuple):
            return tuple
        elif isinstance(node, ast.Dict):
            return dict
        elif isinstance(node, ast.Set):
            return set
        elif isinstance(node, ast.Name):
            # Could be a variable - would need more sophisticated analysis
            return None
        return None

    def _check_parameter_constraints(self, node: ast.Assign, param_name: str, lines: list[str]):
        """Check for parameter-specific constraints."""
        if not isinstance(node.value, ast.Call):
            return

        # Resolve the actual parameter class type for constraint checking
        param_class_info = self._resolve_parameter_class(node.value.func)
        if not param_class_info:
            return

        resolved_param_type = param_class_info["type"]

        # Check bounds for Number/Integer parameters
        if resolved_param_type in ["Number", "Integer"]:
            bounds = None
            inclusive_bounds = (True, True)  # Default to inclusive
            default_value = None

            for keyword in node.value.keywords:
                if keyword.arg == "bounds":
                    bounds = keyword.value
                elif keyword.arg == "inclusive_bounds":
                    inclusive_bounds_node = keyword.value
                    if (
                        isinstance(inclusive_bounds_node, ast.Tuple)
                        and len(inclusive_bounds_node.elts) == 2
                    ):
                        left_inclusive = self._extract_boolean_value(inclusive_bounds_node.elts[0])
                        right_inclusive = self._extract_boolean_value(
                            inclusive_bounds_node.elts[1]
                        )
                        if left_inclusive is not None and right_inclusive is not None:
                            inclusive_bounds = (left_inclusive, right_inclusive)
                elif keyword.arg == "default":
                    default_value = keyword.value

            if bounds and isinstance(bounds, ast.Tuple) and len(bounds.elts) == 2:
                # Check if bounds are valid (min < max)
                try:
                    min_val = self._extract_numeric_value(bounds.elts[0])
                    max_val = self._extract_numeric_value(bounds.elts[1])

                    if min_val is not None and max_val is not None and min_val >= max_val:
                        self.type_errors.append(
                            {
                                "line": node.lineno - 1,
                                "col": node.col_offset,
                                "end_line": node.end_lineno - 1
                                if node.end_lineno
                                else node.lineno - 1,
                                "end_col": node.end_col_offset
                                if node.end_col_offset
                                else node.col_offset,
                                "message": f"Parameter '{param_name}' has invalid bounds: min ({min_val}) >= max ({max_val})",
                                "severity": "error",
                                "code": "invalid-bounds",
                            }
                        )

                    # Check if default value violates bounds
                    if default_value is not None and min_val is not None and max_val is not None:
                        default_numeric = self._extract_numeric_value(default_value)
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
                                bound_description = f"{'[' if left_inclusive else '('}{min_val}, {max_val}{']' if right_inclusive else ')'}"
                                self.type_errors.append(
                                    {
                                        "line": node.lineno - 1,
                                        "col": node.col_offset,
                                        "end_line": node.end_lineno - 1
                                        if node.end_lineno
                                        else node.lineno - 1,
                                        "end_col": node.end_col_offset
                                        if node.end_col_offset
                                        else node.col_offset,
                                        "message": f"Default value {default_numeric} for parameter '{param_name}' is outside bounds {bound_description}",
                                        "severity": "error",
                                        "code": "default-bounds-violation",
                                    }
                                )

                except (ValueError, TypeError):
                    pass

        # Check for empty lists/tuples with List/Tuple parameters
        elif resolved_param_type in ["List", "Tuple"]:
            for keyword in node.value.keywords:
                if keyword.arg == "default" and (
                    isinstance(keyword.value, (ast.List, ast.Tuple))
                    and len(keyword.value.elts) == 0
                ):
                    # This is usually fine, but flag if bounds are specified
                    bounds_specified = any(kw.arg == "bounds" for kw in node.value.keywords)
                    if bounds_specified:
                        self.type_errors.append(
                            {
                                "line": node.lineno - 1,
                                "col": node.col_offset,
                                "end_line": node.end_lineno - 1
                                if node.end_lineno
                                else node.lineno - 1,
                                "end_col": node.end_col_offset
                                if node.end_col_offset
                                else node.col_offset,
                                "message": f"Parameter '{param_name}' has empty default but bounds specified",
                                "severity": "warning",
                                "code": "empty-default-with-bounds",
                            }
                        )

    def _extract_numeric_value(self, node: ast.expr) -> float | int | None:
        """Extract numeric value from AST node."""
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            # Handle negative numbers
            val = self._extract_numeric_value(node.operand)
            return -val if val is not None else None
        return None


class ParamLanguageServer(LanguageServer):
    """Language Server for HoloViz Param."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.analyzer = ParamAnalyzer()
        self.document_cache: dict[str, dict[str, Any]] = {}
        self.param_types = self._get_param_types()

    def _get_param_types(self) -> list[str]:
        """Get available Param parameter types."""
        if param is None:
            # Fallback list if param is not available
            return [
                "Parameter",
                "Number",
                "Integer",
                "String",
                "Boolean",
                "List",
                "Tuple",
                "Dict",
                "Array",
                "DataFrame",
                "Series",
                "Range",
                "Date",
                "CalendarDate",
                "Filename",
                "Foldername",
                "Path",
                "Color",
                "Composite",
                "Dynamic",
                "Event",
                "Action",
                "FileSelector",
                "ListSelector",
                "ObjectSelector",
            ]

        # Get actual param types from the module
        param_types = []
        for name in dir(param):
            obj = getattr(param, name)
            if inspect.isclass(obj) and issubclass(obj, param.Parameter):
                param_types.append(name)
        return param_types

    def _uri_to_path(self, uri: str) -> str:
        """Convert URI to file path."""
        parsed = urlparse(uri)
        return parsed.path

    def _analyze_document(self, uri: str, content: str):
        """Analyze a document and cache the results."""
        analysis = self.analyzer.analyze_file(content)
        self.document_cache[uri] = {"content": content, "analysis": analysis}

        # Debug logging
        logger.info(f"Analysis results for {uri}:")
        logger.info(f"  Param classes: {analysis.get('param_classes', set())}")
        logger.info(f"  Parameters: {analysis.get('param_parameters', {})}")
        logger.info(f"  Parameter types: {analysis.get('param_parameter_types', {})}")
        logger.info(f"  Type errors: {analysis.get('type_errors', [])}")

        # Publish diagnostics for type errors
        self._publish_diagnostics(uri, analysis.get("type_errors", []))

    def _publish_diagnostics(self, uri: str, type_errors: list[dict[str, Any]]):
        """Publish diagnostics for type errors."""
        diagnostics = []

        for error in type_errors:
            severity = (
                DiagnosticSeverity.Error
                if error.get("severity") == "error"
                else DiagnosticSeverity.Warning
            )

            diagnostic = Diagnostic(
                range=Range(
                    start=Position(line=error["line"], character=error["col"]),
                    end=Position(line=error["end_line"], character=error["end_col"]),
                ),
                message=error["message"],
                severity=severity,
                code=error.get("code"),
                source="param-lsp",
            )
            diagnostics.append(diagnostic)

        # Publish diagnostics
        self.publish_diagnostics(uri, diagnostics)

    def _get_completions_for_param_class(self, line: str, character: int) -> list[CompletionItem]:
        """Get completions for param class attributes and methods."""

        # Add parameter types with enhanced documentation
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

        # Add common parameter arguments with detailed documentation
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

        completions.extend(
            [
                CompletionItem(
                    label=arg_name,
                    kind=CompletionItemKind.Property,
                    detail="Parameter argument",
                    documentation=arg_doc,
                )
                for arg_name, arg_doc in param_args
            ]
        )

        return completions

    def _get_hover_info(self, uri: str, line: str, word: str) -> str | None:
        """Get hover information for a word."""
        if uri in self.document_cache:
            analysis = self.document_cache[uri]["analysis"]

            # Check if it's a parameter type
            if word in self.param_types:
                if param:
                    param_class = getattr(param, word, None)
                    if param_class and hasattr(param_class, "__doc__"):
                        return param_class.__doc__
                return f"Param parameter type: {word}"

            # Check if it's a parameter in a class
            param_parameters = analysis.get("param_parameters", {})
            param_parameter_types = analysis.get("param_parameter_types", {})
            param_parameter_docs = analysis.get("param_parameter_docs", {})
            param_parameter_bounds = analysis.get("param_parameter_bounds", {})

            for class_name, parameters in param_parameters.items():
                if word in parameters:
                    hover_parts = [f"**Parameter '{word}' in class '{class_name}'**"]

                    # Add parameter type information
                    param_type = param_parameter_types.get(class_name, {}).get(word)
                    if param_type:
                        hover_parts.append(f"Type: `{param_type}`")

                    # Add bounds information
                    bounds = param_parameter_bounds.get(class_name, {}).get(word)
                    if bounds:
                        if len(bounds) == 2:
                            min_val, max_val = bounds
                            hover_parts.append(f"Bounds: `[{min_val}, {max_val}]`")
                        elif len(bounds) == 4:
                            min_val, max_val, left_inclusive, right_inclusive = bounds
                            left_bracket = "[" if left_inclusive else "("
                            right_bracket = "]" if right_inclusive else ")"
                            hover_parts.append(
                                f"Bounds: `{left_bracket}{min_val}, {max_val}{right_bracket}`"
                            )

                    # Add documentation
                    doc = param_parameter_docs.get(class_name, {}).get(word)
                    if doc:
                        hover_parts.append(f"\n{doc}")

                    return "\n\n".join(hover_parts)

        return None


# Create the language server instance
server = ParamLanguageServer("param-lsp", "v0.1.0")


@server.feature("initialize")
def initialize(params: InitializeParams) -> InitializeResult:
    """Initialize the language server."""
    logger.info("Initializing Param LSP server")

    return InitializeResult(
        capabilities=ServerCapabilities(
            text_document_sync=TextDocumentSyncKind.Incremental,
            completion_provider=CompletionOptions(trigger_characters=[".", "=", "("]),
            hover_provider=True,
            diagnostic_provider=DiagnosticOptions(
                inter_file_dependencies=False, workspace_diagnostics=False
            ),
        )
    )


@server.feature("textDocument/didOpen")
def did_open(params: DidOpenTextDocumentParams):
    """Handle document open event."""
    uri = params.text_document.uri
    content = params.text_document.text
    server._analyze_document(uri, content)
    logger.info(f"Opened document: {uri}")


@server.feature("textDocument/didChange")
def did_change(params: DidChangeTextDocumentParams):
    """Handle document change event."""
    uri = params.text_document.uri

    # Apply changes to get updated content
    if uri in server.document_cache:
        content = server.document_cache[uri]["content"]
        for change in params.content_changes:
            if getattr(change, "range", None):
                # Handle incremental changes
                lines = content.split("\n")
                range_obj = change.range  # pyright: ignore[reportAttributeAccessIssue]
                start_line = range_obj.start.line
                start_char = range_obj.start.character
                end_line = range_obj.end.line
                end_char = range_obj.end.character

                # Apply the change
                if start_line == end_line:
                    lines[start_line] = (
                        lines[start_line][:start_char] + change.text + lines[start_line][end_char:]
                    )
                else:
                    # Multi-line change
                    new_lines = change.text.split("\n")
                    lines[start_line] = lines[start_line][:start_char] + new_lines[0]
                    for i in range(start_line + 1, end_line + 1):
                        if i < len(lines):
                            del lines[start_line + 1]
                    if len(new_lines) > 1:
                        lines[start_line] += new_lines[-1] + lines[end_line][end_char:]
                        for i, new_line in enumerate(new_lines[1:-1], 1):
                            lines.insert(start_line + i, new_line)

                content = "\n".join(lines)
            else:
                # Full document change
                content = change.text

        server._analyze_document(uri, content)


@server.feature("textDocument/completion")
def completion(params: CompletionParams) -> CompletionList:
    """Provide completion suggestions."""
    uri = params.text_document.uri
    position = params.position

    if uri not in server.document_cache:
        return CompletionList(is_incomplete=False, items=[])

    content = server.document_cache[uri]["content"]
    lines = content.split("\n")

    if position.line >= len(lines):
        return CompletionList(is_incomplete=False, items=[])

    current_line = lines[position.line]

    # Get completions based on context
    completions = server._get_completions_for_param_class(current_line, position.character)

    return CompletionList(is_incomplete=False, items=completions)


@server.feature("textDocument/hover")
def hover(params: HoverParams) -> Hover | None:
    """Provide hover information."""
    uri = params.text_document.uri
    position = params.position

    if uri not in server.document_cache:
        return None

    content = server.document_cache[uri]["content"]
    lines = content.split("\n")

    if position.line >= len(lines):
        return None

    current_line = lines[position.line]

    # Extract word at position
    char = position.character
    if char >= len(current_line):
        return None

    # Find word boundaries
    start = char
    end = char

    while start > 0 and (current_line[start - 1].isalnum() or current_line[start - 1] == "_"):
        start -= 1
    while end < len(current_line) and (current_line[end].isalnum() or current_line[end] == "_"):
        end += 1

    if start == end:
        return None

    word = current_line[start:end]
    hover_info = server._get_hover_info(uri, current_line, word)

    if hover_info:
        return Hover(
            contents=MarkupContent(
                kind=MarkupKind.Markdown, value=f"```python\n{word}\n```\n\n{hover_info}"
            ),
            range=Range(
                start=Position(line=position.line, character=start),
                end=Position(line=position.line, character=end),
            ),
        )

    return None
