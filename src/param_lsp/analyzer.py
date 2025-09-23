"""
HoloViz Param Language Server Protocol implementation.
Provides IDE support for Param-based Python code including autocompletion,
hover information, and diagnostics.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import logging
from pathlib import Path
from typing import Any

import param

from .cache import external_library_cache

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global configuration for allowed external libraries for runtime introspection
ALLOWED_EXTERNAL_LIBRARIES = {
    "panel",
    "holoviews",
    "param",
}


class ParamAnalyzer:
    """Analyzes Python code for Param usage patterns."""

    def __init__(self, workspace_root: str | None = None):
        self.param_classes: set[str] = set()
        self.param_parameters: dict[str, list[str]] = {}
        # class_name -> {param_name: param_type}
        self.param_parameter_types: dict[str, dict[str, str]] = {}
        # class_name -> {param_name: (min, max)}
        self.param_parameter_bounds: dict[str, dict[str, tuple]] = {}
        # class_name -> {param_name: doc_string}
        self.param_parameter_docs: dict[str, dict[str, str]] = {}
        # class_name -> {param_name: allow_None}
        self.param_parameter_allow_none: dict[str, dict[str, bool]] = {}
        # class_name -> {param_name: default_value}
        self.param_parameter_defaults: dict[str, dict[str, str]] = {}
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

        # Workspace-wide analysis
        self.workspace_root = Path(workspace_root) if workspace_root else None
        self.module_cache: dict[str, dict[str, Any]] = {}  # module_name -> analysis_result
        self.file_cache: dict[str, dict[str, Any]] = {}  # file_path -> analysis_result

        # Cache for external Parameterized classes (AST-based detection)
        self.external_param_classes: dict[
            str, dict[str, Any] | None
        ] = {}  # full_class_path -> class_info

        # Populate external library cache on initialization
        self._populate_external_library_cache()

    def analyze_file(self, content: str, file_path: str | None = None) -> dict[str, Any]:
        """Analyze a Python file for Param usage."""
        tree = None
        try:
            tree = ast.parse(content)
            self._reset_analysis()
            self._current_file_path = file_path
        except SyntaxError:
            # Try to handle incomplete code (e.g., unclosed parentheses during typing)
            lines = content.split("\n")

            # First, try to fix common incomplete syntax patterns
            fixed_content = self._try_fix_incomplete_syntax(lines)
            if fixed_content != content:
                try:
                    tree = ast.parse(fixed_content)
                    self._reset_analysis()
                    self._current_file_path = file_path
                    logger.info("Successfully parsed after fixing incomplete syntax")
                    # Continue with the fixed content
                except SyntaxError:
                    pass  # Fall back to line removal approach

            # If fixing didn't work, try removing lines with incomplete syntax from the end
            if tree is None:
                for i in range(1, len(lines) + 1):
                    # Try parsing without the last i lines
                    truncated_content = "\n".join(lines[:-i] if i < len(lines) else [])

                    if not truncated_content.strip():
                        continue  # Skip empty content

                    try:
                        tree = ast.parse(truncated_content)
                        self._reset_analysis()
                        self._current_file_path = file_path
                        logger.info(
                            f"Successfully parsed after removing {i} lines with syntax errors"
                        )
                        break
                    except SyntaxError:
                        continue
                else:
                    # If we couldn't parse even with all lines removed, give up
                    logger.error("Could not parse file due to syntax errors")
                    return {}

        # At this point, tree should be assigned, but add safety check
        if tree is None:
            logger.error("Failed to parse file - tree is None")
            return {}

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

        # Pre-pass: discover all external Parameterized classes using AST
        self._discover_external_param_classes_ast(tree)

        # Perform type inference after parsing
        self._check_parameter_types(tree, content.split("\n"))

        return {
            "param_classes": self.param_classes,
            "param_parameters": self.param_parameters,
            "param_parameter_types": self.param_parameter_types,
            "param_parameter_bounds": self.param_parameter_bounds,
            "param_parameter_docs": self.param_parameter_docs,
            "param_parameter_allow_none": self.param_parameter_allow_none,
            "param_parameter_defaults": self.param_parameter_defaults,
            "imports": self.imports,
            "type_errors": self.type_errors,
        }

    def _reset_analysis(self):
        """Reset analysis state."""
        self.param_classes.clear()
        self.param_parameters.clear()
        self.param_parameter_types.clear()
        self.param_parameter_bounds.clear()
        self.param_parameter_docs.clear()
        self.param_parameter_allow_none.clear()
        self.param_parameter_defaults.clear()
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
            (
                parameters,
                parameter_types,
                parameter_bounds,
                parameter_docs,
                parameter_allow_none,
                parameter_defaults,
            ) = self._extract_parameters(node)

            # For inherited classes, we need to collect parameters from parent classes too
            # Get parent class parameters and merge them
            (
                parent_parameters,
                parent_parameter_types,
                parent_parameter_bounds,
                parent_parameter_docs,
                parent_parameter_allow_none,
                parent_parameter_defaults,
            ) = self._collect_inherited_parameters(node, getattr(self, "_current_file_path", None))

            # Merge parent parameters with current class parameters
            # Child class parameters override parent parameters with the same name
            all_parameter_types = {**parent_parameter_types, **parameter_types}
            all_parameter_bounds = {**parent_parameter_bounds, **parameter_bounds}
            all_parameter_docs = {**parent_parameter_docs, **parameter_docs}
            all_parameter_allow_none = {**parent_parameter_allow_none, **parameter_allow_none}
            all_parameter_defaults = {**parent_parameter_defaults, **parameter_defaults}

            # Create unique parameter list, with child parameters overriding parent ones
            all_parameters = []
            current_param_names = set(parameters)

            # Add current class parameters first (these take precedence)
            all_parameters.extend(parameters)

            # Add parent parameters only if they're not overridden by current class
            all_parameters.extend(
                [
                    parent_param
                    for parent_param in parent_parameters
                    if parent_param not in current_param_names
                ]
            )

            self.param_parameters[node.name] = all_parameters
            self.param_parameter_types[node.name] = all_parameter_types
            self.param_parameter_bounds[node.name] = all_parameter_bounds
            self.param_parameter_docs[node.name] = all_parameter_docs
            self.param_parameter_allow_none[node.name] = all_parameter_allow_none
            self.param_parameter_defaults[node.name] = all_parameter_defaults

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
            if (
                base.id in ["Parameterized"]
                and base.id in self.imports
                and "param.Parameterized" in self.imports[base.id]
            ):
                return True
            # Check if it's a known param class (from inheritance)
            if base.id in self.param_classes:
                return True
            # Check if it's an imported param class
            imported_class_info = self._get_imported_param_class_info(
                base.id, base.id, getattr(self, "_current_file_path", None)
            )
            if imported_class_info:
                return True
        elif isinstance(base, ast.Attribute):
            # Handle simple case: param.Parameterized
            if isinstance(base.value, ast.Name):
                module = base.value.id
                if (module == "param" and base.attr == "Parameterized") or (
                    module in self.imports
                    and self.imports[module].endswith("param")
                    and base.attr == "Parameterized"
                ):
                    return True

            # Handle complex attribute access like pn.widgets.IntSlider
            full_class_path = self._resolve_full_class_path(base)
            if full_class_path:
                # Check if this external class is a Parameterized class
                class_info = self._analyze_external_class_ast(full_class_path)
                if class_info:
                    return True
        return False

    def _collect_inherited_parameters(
        self, node: ast.ClassDef, current_file_path: str | None = None
    ) -> tuple[
        list[str],
        dict[str, str],
        dict[str, tuple],
        dict[str, str],
        dict[str, bool],
        dict[str, str],
    ]:
        """Collect parameters from parent classes in inheritance hierarchy."""
        inherited_parameters = []
        inherited_parameter_types = {}
        inherited_parameter_bounds = {}
        inherited_parameter_docs = {}
        inherited_parameter_allow_none = {}
        inherited_parameter_defaults = {}

        for base in node.bases:
            if isinstance(base, ast.Name):
                parent_class_name = base.id

                # First check if it's a local class in the same file
                if parent_class_name in self.param_classes:
                    # Get parameters from the parent class
                    parent_params = self.param_parameters.get(parent_class_name, [])
                    parent_types = self.param_parameter_types.get(parent_class_name, {})
                    parent_bounds = self.param_parameter_bounds.get(parent_class_name, {})
                    parent_docs = self.param_parameter_docs.get(parent_class_name, {})
                    parent_allow_none = self.param_parameter_allow_none.get(parent_class_name, {})
                    parent_defaults = self.param_parameter_defaults.get(parent_class_name, {})

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
                        if param in parent_allow_none:
                            inherited_parameter_allow_none[param] = parent_allow_none[param]
                        if param in parent_defaults:
                            inherited_parameter_defaults[param] = parent_defaults[param]

                # If not found locally, check if it's an imported class
                else:
                    # Check if this class was imported
                    imported_class_info = self._get_imported_param_class_info(
                        parent_class_name, parent_class_name, current_file_path
                    )

                    if imported_class_info:
                        parent_params = imported_class_info.get("parameters", [])
                        parent_types = imported_class_info.get("parameter_types", {})
                        parent_bounds = imported_class_info.get("parameter_bounds", {})
                        parent_docs = imported_class_info.get("parameter_docs", {})
                        parent_allow_none = imported_class_info.get("parameter_allow_none", {})
                        parent_defaults = imported_class_info.get("parameter_defaults", {})

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
                            if param in parent_allow_none:
                                inherited_parameter_allow_none[param] = parent_allow_none[param]
                            if param in parent_defaults:
                                inherited_parameter_defaults[param] = parent_defaults[param]

            elif isinstance(base, ast.Attribute):
                # Handle complex attribute access like pn.widgets.IntSlider
                full_class_path = self._resolve_full_class_path(base)
                if full_class_path:
                    # Check if this external class is a Parameterized class
                    class_info = self._analyze_external_class_ast(full_class_path)
                    if class_info:
                        parent_params = class_info.get("parameters", [])
                        parent_types = class_info.get("parameter_types", {})
                        parent_bounds = class_info.get("parameter_bounds", {})
                        parent_docs = class_info.get("parameter_docs", {})
                        parent_allow_none = class_info.get("parameter_allow_none", {})
                        parent_defaults = class_info.get("parameter_defaults", {})

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
                            if param in parent_allow_none:
                                inherited_parameter_allow_none[param] = parent_allow_none[param]
                            if param in parent_defaults:
                                inherited_parameter_defaults[param] = parent_defaults[param]

        return (
            inherited_parameters,
            inherited_parameter_types,
            inherited_parameter_bounds,
            inherited_parameter_docs,
            inherited_parameter_allow_none,
            inherited_parameter_defaults,
        )

    def _extract_parameters(
        self, node: ast.ClassDef
    ) -> tuple[
        list[str],
        dict[str, str],
        dict[str, tuple],
        dict[str, str],
        dict[str, bool],
        dict[str, str],
    ]:
        """Extract parameter definitions from a Param class."""
        parameters = []
        parameter_types = {}
        parameter_bounds = {}
        parameter_docs = {}
        parameter_allow_none = {}
        parameter_defaults = {}
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

                            # Get allow_None if present
                            allow_none = self._extract_allow_none_from_call(item.value)
                            default_value = self._extract_default_from_call(item.value)

                            # Store default value as a string representation
                            if default_value is not None:
                                parameter_defaults[param_name] = self._format_default_value(
                                    default_value
                                )

                            # Param automatically sets allow_None=True when default=None
                            if default_value is not None and self._is_none_value(default_value):
                                parameter_allow_none[param_name] = True
                            elif allow_none is not None:
                                parameter_allow_none[param_name] = allow_none

        return (
            parameters,
            parameter_types,
            parameter_bounds,
            parameter_docs,
            parameter_allow_none,
            parameter_defaults,
        )

    def _extract_bounds_from_call(self, call_node: ast.Call) -> tuple | None:
        """Extract bounds from a parameter call."""
        bounds_info = None
        inclusive_bounds = (True, True)  # Default to inclusive

        for keyword in call_node.keywords:
            if keyword.arg == "bounds":
                if isinstance(keyword.value, ast.Tuple) and len(keyword.value.elts) == 2:
                    min_val = self._extract_numeric_value(keyword.value.elts[0])
                    max_val = self._extract_numeric_value(keyword.value.elts[1])
                    # Accept bounds even if one side is None (unbounded)
                    # But require at least one bound to be numeric
                    if min_val is not None or max_val is not None:
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

    def _extract_allow_none_from_call(self, call_node: ast.Call) -> bool | None:
        """Extract allow_None from a parameter call."""
        for keyword in call_node.keywords:
            if keyword.arg == "allow_None":
                return self._extract_boolean_value(keyword.value)
        return None

    def _extract_default_from_call(self, call_node: ast.Call) -> ast.expr | None:
        """Extract default value from a parameter call."""
        for keyword in call_node.keywords:
            if keyword.arg == "default":
                return keyword.value
        return None

    def _is_none_value(self, node: ast.expr) -> bool:
        """Check if an AST node represents None."""
        return isinstance(node, ast.Constant) and node.value is None

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

    def _format_default_value(self, node: ast.expr) -> str:
        """Format an AST node as a string representation for display."""
        if isinstance(node, ast.Constant):
            if node.value is None:
                return "None"
            elif isinstance(node.value, str):
                return repr(node.value)  # Use repr to include quotes
            else:
                return str(node.value)
        elif isinstance(node, ast.List):
            elements = [self._format_default_value(elem) for elem in node.elts]
            return f"[{', '.join(elements)}]"
        elif isinstance(node, ast.Tuple):
            elements = [self._format_default_value(elem) for elem in node.elts]
            if len(elements) == 1:
                return f"({elements[0]},)"  # Single-element tuple
            return f"({', '.join(elements)})"
        elif isinstance(node, ast.Dict):
            pairs = []
            for key, value in zip(node.keys, node.values, strict=False):
                key_str = self._format_default_value(key) if key else "None"
                value_str = self._format_default_value(value)
                pairs.append(f"{key_str}: {value_str}")
            return f"{{{', '.join(pairs)}}}"
        elif isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name):
                return f"{node.value.id}.{node.attr}"
            else:
                return f"{self._format_default_value(node.value)}.{node.attr}"
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return f"-{self._format_default_value(node.operand)}"
        else:
            # Fallback for complex expressions
            return "<complex>"

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

            # Check constructor calls like MyClass(x="A")
            elif isinstance(node, ast.Call):
                self._check_constructor_parameter_types(node, lines)

    def _check_constructor_parameter_types(self, node: ast.Call, lines: list[str]):
        """Check for type errors in constructor parameter calls like MyClass(x="A")."""
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

        # Check each keyword argument passed to the constructor
        for keyword in node.keywords:
            if keyword.arg is None:  # Skip **kwargs
                continue

            param_name = keyword.arg
            param_value = keyword.value

            # Get the expected parameter type
            param_type = self._get_parameter_type_from_class(class_name, param_name)
            if not param_type:
                continue  # Skip if parameter not found (could be inherited or not a param)

            # Check if None is allowed for this parameter
            inferred_type = self._infer_value_type(param_value)
            if inferred_type is type(None):  # None value
                allow_none = self._get_parameter_allow_none(class_name, param_name)
                if allow_none:
                    continue  # None is allowed, skip further validation
                # If allow_None is False or not specified, continue with normal type checking

            # Check if assigned value matches expected type
            if param_type in self.param_type_map:
                expected_types = self.param_type_map[param_type]
                if not isinstance(expected_types, tuple):
                    expected_types = (expected_types,)

                # inferred_type was already computed above

                # Special handling for Boolean parameters - they should only accept actual bool values
                if param_type == "Boolean" and inferred_type and inferred_type is not bool:
                    if not (
                        isinstance(param_value, ast.Constant)
                        and isinstance(param_value.value, bool)
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
                                "message": f"Cannot assign {inferred_type.__name__} to Boolean parameter '{param_name}' in {class_name}() constructor (expects True/False)",
                                "severity": "error",
                                "code": "constructor-boolean-type-mismatch",
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
                            "end_line": node.end_lineno - 1
                            if node.end_lineno
                            else node.lineno - 1,
                            "end_col": node.end_col_offset
                            if node.end_col_offset
                            else node.col_offset,
                            "message": f"Cannot assign {inferred_type.__name__} to parameter '{param_name}' of type {param_type} in {class_name}() constructor (expects {self._format_expected_types(expected_types)})",
                            "severity": "error",
                            "code": "constructor-type-mismatch",
                        }
                    )

            # Check bounds for numeric parameters in constructor calls
            self._check_constructor_bounds(node, class_name, param_name, param_type, param_value)

    def _check_constructor_bounds(
        self,
        node: ast.Call,
        class_name: str,
        param_name: str,
        param_type: str,
        param_value: ast.expr,
    ):
        """Check if constructor parameter value is within parameter bounds."""
        # Only check bounds for numeric types
        if param_type not in ["Number", "Integer"]:
            return

        # Get bounds for this parameter
        bounds = self._get_parameter_bounds(class_name, param_name)
        if not bounds:
            return

        # Extract numeric value from parameter value
        assigned_numeric = self._extract_numeric_value(param_value)
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
        # Handle None bounds (unbounded)
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
            # Format bounds description with proper None handling
            min_str = str(min_val) if min_val is not None else "-∞"
            max_str = str(max_val) if max_val is not None else "∞"
            bound_description = f"{'[' if left_inclusive else '('}{min_str}, {max_str}{']' if right_inclusive else ')'}"
            self.type_errors.append(
                {
                    "line": node.lineno - 1,
                    "col": node.col_offset,
                    "end_line": node.end_lineno - 1 if node.end_lineno else node.lineno - 1,
                    "end_col": node.end_col_offset if node.end_col_offset else node.col_offset,
                    "message": f"Value {assigned_numeric} for parameter '{param_name}' in {class_name}() constructor is outside bounds {bound_description}",
                    "severity": "error",
                    "code": "constructor-bounds-violation",
                }
            )

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

        # Get default value and allow_None from keyword arguments
        default_value = None
        allow_none = None
        for keyword in node.value.keywords:
            if keyword.arg == "default":
                default_value = keyword.value
            elif keyword.arg == "allow_None":
                allow_none = self._extract_boolean_value(keyword.value)

        # Param automatically sets allow_None=True when default=None
        if default_value is not None and self._is_none_value(default_value):
            allow_none = True

        if param_type and default_value and param_type in self.param_type_map:
            expected_types = self.param_type_map[param_type]
            if not isinstance(expected_types, tuple):
                expected_types = (expected_types,)

            inferred_type = self._infer_value_type(default_value)

            # Check if None is allowed for this parameter
            if allow_none and inferred_type is type(None):
                return  # None is allowed, skip further validation
                # If allow_None is False or not specified, continue with normal type checking

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
            # First check local param classes
            for class_name in self.param_classes:
                if param_name in self.param_parameters.get(class_name, []):
                    instance_class = class_name
                    break

            # If not found in local classes, check external param classes
            if not instance_class:
                for class_name, class_info in self.external_param_classes.items():
                    if class_info and param_name in class_info.get("parameters", []):
                        instance_class = class_name
                        break

        if not instance_class:
            return

        # Check if this is a valid param class (local or external)
        is_valid_param_class = instance_class in self.param_classes or (
            instance_class in self.external_param_classes
            and self.external_param_classes[instance_class]
        )

        if not is_valid_param_class:
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

            # Check if None is allowed for this parameter
            if inferred_type is type(None):  # None value
                allow_none = self._get_parameter_allow_none(instance_class, param_name)
                if allow_none:
                    return  # None is allowed, skip further validation
                # If allow_None is False or not specified, continue with normal type checking

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
        # Handle None bounds (unbounded)
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

        # Format bounds description with proper None handling
        min_str = str(min_val) if min_val is not None else "-∞"
        max_str = str(max_val) if max_val is not None else "∞"
        bound_description = f"{'[' if left_inclusive else '('}{min_str}, {max_str}{']' if right_inclusive else ')'}"

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
        # Check local classes first
        if class_name in self.param_parameter_bounds:
            return self.param_parameter_bounds[class_name].get(param_name)

        # Check external classes
        external_class_info = self.external_param_classes.get(class_name)
        if external_class_info:
            return external_class_info["parameter_bounds"].get(param_name)

        return None

    def _get_instance_class(self, call_node: ast.Call) -> str | None:
        """Get the class name from an instance creation call."""
        if isinstance(call_node.func, ast.Name):
            return call_node.func.id
        elif isinstance(call_node.func, ast.Attribute):
            # Try to resolve the full class path for external classes
            full_class_path = self._resolve_full_class_path(call_node.func)
            if full_class_path:
                # Check if this is an external Parameterized class
                class_info = self._analyze_external_class_ast(full_class_path)
                if class_info:
                    # Return the full path as the class identifier for external classes
                    return full_class_path
            # Fallback to just the attribute name for local classes
            return call_node.func.attr
        return None

    def _resolve_full_class_path(self, attr_node: ast.Attribute) -> str | None:
        """Resolve the full class path from an attribute node like pn.widgets.IntSlider."""
        path_parts = []

        # Walk up the attribute chain
        current = attr_node
        while isinstance(current, ast.Attribute):
            path_parts.append(current.attr)
            current = current.value

        if isinstance(current, ast.Name):
            path_parts.append(current.id)
            path_parts.reverse()

            # Resolve the root module through imports
            root_alias = path_parts[0]
            if root_alias in self.imports:
                full_module_name = self.imports[root_alias]
                # Replace the alias with the full module name
                path_parts[0] = full_module_name
                return ".".join(path_parts)
            else:
                # Use the alias directly if no import mapping found
                return ".".join(path_parts)

        return None

    def _get_parameter_type_from_class(self, class_name: str, param_name: str) -> str | None:
        """Get the parameter type from a class definition."""
        # Check local classes first
        if class_name in self.param_parameter_types:
            return self.param_parameter_types[class_name].get(param_name)

        # Check external classes
        external_class_info = self.external_param_classes.get(class_name)
        if external_class_info:
            return external_class_info["parameter_types"].get(param_name)

        return None

    def _get_parameter_allow_none(self, class_name: str, param_name: str) -> bool:
        """Get the allow_None setting for a parameter from a class definition."""
        # Check local classes first
        if class_name in self.param_parameter_allow_none:
            return self.param_parameter_allow_none[class_name].get(param_name, False)

        # Check external classes
        external_class_info = self.external_param_classes.get(class_name)
        if external_class_info:
            return external_class_info["parameter_allow_none"].get(param_name, False)

        return False

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
    ) -> dict[str, Any]:
        """Analyze an imported module and cache the results."""
        # Check cache first
        if module_name in self.module_cache:
            return self.module_cache[module_name]

        # Resolve module path
        module_path = self._resolve_module_path(module_name, current_file_path)
        if not module_path:
            return {}

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
            return {}

    def _get_imported_param_class_info(
        self, class_name: str, import_name: str, current_file_path: str | None = None
    ) -> dict[str, Any] | None:
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
        param_classes = module_analysis.get("param_classes", set())
        if imported_class_name not in param_classes:
            return None

        # Return parameter information for the imported class
        return {
            "parameters": module_analysis.get("param_parameters", {}).get(imported_class_name, []),
            "parameter_types": module_analysis.get("param_parameter_types", {}).get(
                imported_class_name, {}
            ),
            "parameter_bounds": module_analysis.get("param_parameter_bounds", {}).get(
                imported_class_name, {}
            ),
            "parameter_docs": module_analysis.get("param_parameter_docs", {}).get(
                imported_class_name, {}
            ),
            "parameter_allow_none": module_analysis.get("param_parameter_allow_none", {}).get(
                imported_class_name, {}
            ),
            "parameter_defaults": module_analysis.get("param_parameter_defaults", {}).get(
                imported_class_name, {}
            ),
        }

    def _extract_numeric_value(self, node: ast.expr) -> float | int | None:
        """Extract numeric value from AST node."""
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            elif node.value is None:
                return None  # Explicitly handle None
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            # Handle negative numbers
            val = self._extract_numeric_value(node.operand)
            return -val if val is not None else None
        return None

    def _analyze_external_class_ast(self, full_class_path: str) -> dict[str, Any] | None:
        """Analyze external classes using runtime introspection for allowed libraries."""
        if full_class_path in self.external_param_classes:
            return self.external_param_classes[full_class_path]

        # Check if this library is allowed for runtime introspection
        root_module = full_class_path.split(".")[0]
        if root_module in ALLOWED_EXTERNAL_LIBRARIES:
            class_info = self._introspect_external_class_runtime(full_class_path)
            self.external_param_classes[full_class_path] = class_info
        else:
            # For non-allowed libraries, mark as unknown
            self.external_param_classes[full_class_path] = None
            class_info = None

        return class_info

    def _try_fix_incomplete_syntax(self, lines: list[str]) -> str:
        """Try to fix common incomplete syntax patterns."""
        fixed_lines = []

        for line in lines:
            fixed_line = line

            # Fix incomplete imports like "from param" -> "import param"
            if line.strip().startswith("from param") and " import " not in line:
                fixed_line = "import param"

            # Fix incomplete @param.depends( by adding closing parenthesis and quotes
            elif "@param.depends(" in line and ")" not in line:
                # Handle unclosed quotes in @param.depends
                if '"' in line and line.count('"') % 2 == 1:
                    # Unclosed double quote
                    fixed_line = line + '")'
                elif "'" in line and line.count("'") % 2 == 1:
                    # Unclosed single quote
                    fixed_line = line + "')"
                else:
                    # No quotes or balanced quotes, just add closing parenthesis
                    fixed_line = line + ")"

            # Fix incomplete function definitions after @param.depends
            elif line.strip().startswith("def ") and line.endswith(": ..."):
                # Make it a proper function definition
                fixed_line = line.replace(": ...", ":\n        pass")

            fixed_lines.append(fixed_line)

        return "\n".join(fixed_lines)

    def _introspect_external_class_runtime(self, full_class_path: str) -> dict[str, Any] | None:
        """Introspect an external class using runtime imports for allowed libraries."""

        # Get the root library name for cache lookup
        root_library = full_class_path.split(".")[0]

        # Check cache first
        cached_result = external_library_cache.get(root_library, full_class_path)
        if cached_result is not None:
            logger.debug(f"Using cached result for {full_class_path}")
            return cached_result

        try:
            # Parse the full class path (e.g., "panel.widgets.IntSlider")
            module_path, class_name = full_class_path.rsplit(".", 1)

            # Import the module and get the class
            try:
                module = importlib.import_module(module_path)
                if not hasattr(module, class_name):
                    return None

                cls = getattr(module, class_name)
            except ImportError as e:
                logger.debug(f"Could not import {module_path}: {e}")
                return None

            # Check if it inherits from param.Parameterized
            try:
                if not issubclass(cls, param.Parameterized):
                    return None
            except TypeError:
                # cls is not a class
                return None

            # Extract parameter information using param's introspection
            parameters = []
            parameter_types = {}
            parameter_bounds = {}
            parameter_docs = {}
            parameter_allow_none = {}
            parameter_defaults = {}

            if hasattr(cls, "param"):
                for param_name, param_obj in cls.param.objects().items():
                    # Skip the 'name' parameter as it's rarely set in constructors
                    if param_name == "name":
                        continue
                    parameters.append(param_name)

                    if param_obj:
                        # Get parameter type
                        param_type_name = type(param_obj).__name__
                        parameter_types[param_name] = param_type_name

                        # Get bounds if present
                        if hasattr(param_obj, "bounds") and param_obj.bounds is not None:
                            bounds = param_obj.bounds
                            # Handle inclusive bounds
                            if hasattr(param_obj, "inclusive_bounds"):
                                inclusive_bounds = param_obj.inclusive_bounds
                                parameter_bounds[param_name] = (*bounds, *inclusive_bounds)
                            else:
                                parameter_bounds[param_name] = bounds

                        # Get doc string
                        if hasattr(param_obj, "doc") and param_obj.doc:
                            parameter_docs[param_name] = param_obj.doc

                        # Get allow_None
                        if hasattr(param_obj, "allow_None"):
                            parameter_allow_none[param_name] = param_obj.allow_None

                        # Get default value
                        if hasattr(param_obj, "default"):
                            parameter_defaults[param_name] = str(param_obj.default)

            result = {
                "parameters": parameters,
                "parameter_types": parameter_types,
                "parameter_bounds": parameter_bounds,
                "parameter_docs": parameter_docs,
                "parameter_allow_none": parameter_allow_none,
                "parameter_defaults": parameter_defaults,
            }

            # Cache the result for future use
            external_library_cache.set(root_library, full_class_path, result)
            logger.debug(f"Cached introspection result for {full_class_path}")

            return result

        except Exception as e:
            logger.debug(f"Failed to introspect external class {full_class_path}: {e}")
            return None

    def _extract_imports_from_ast(self, tree: ast.AST) -> dict[str, str]:
        """Extract import mappings from an AST."""
        imports = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports[alias.asname or alias.name] = alias.name
            elif isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    imported_name = alias.asname or alias.name
                    full_name = f"{node.module}.{alias.name}"
                    imports[imported_name] = full_name
        return imports

    def _inherits_from_parameterized_ast(
        self, class_node: ast.ClassDef, imports: dict[str, str]
    ) -> bool:
        """Check if a class inherits from param.Parameterized using AST analysis."""
        for base in class_node.bases:
            if isinstance(base, ast.Name):
                # Direct inheritance from Parameterized
                if base.id == "Parameterized":
                    imported_class = imports.get(base.id, "")
                    if "param.Parameterized" in imported_class:
                        return True
            elif isinstance(base, ast.Attribute) and isinstance(base.value, ast.Name):
                # Module.Parameterized style inheritance
                module = base.value.id
                if base.attr == "Parameterized":
                    imported_module = imports.get(module, "")
                    if "param" in imported_module:
                        return True
        return False

    def _find_class_in_ast(self, tree: ast.AST, class_name: str) -> ast.ClassDef | None:
        """Find a class definition in an AST."""
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                return node
        return None

    def _discover_external_param_classes_ast(self, tree: ast.AST):
        """Pre-pass to discover all external Parameterized classes using AST analysis."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                # Look for calls like pn.widgets.IntSlider()
                full_class_path = self._resolve_full_class_path(node.func)
                if full_class_path:
                    self._analyze_external_class_ast(full_class_path)

    def _populate_external_library_cache(self):
        """Populate the external library cache with all param.Parameterized classes on startup."""
        # Check if cache already has data to avoid unnecessary repopulation
        cache_files = list(external_library_cache.cache_dir.glob("*.json"))
        if cache_files:
            logger.debug(
                f"External library cache already populated ({len(cache_files)} files), skipping"
            )
            return

        logger.info("Populating external library cache...")

        # Import available libraries first to avoid try-except in loop
        available_libraries = []
        for library_name in ALLOWED_EXTERNAL_LIBRARIES:
            try:
                library = importlib.import_module(library_name)
                available_libraries.append((library_name, library))
            except ImportError:
                logger.debug(f"Library {library_name} not available, skipping cache population")

        # Process available libraries
        for library_name, library in available_libraries:
            logger.info(f"Discovering param.Parameterized classes in {library_name}...")
            classes_found = self._discover_param_classes_in_library(library, library_name)
            logger.info(f"Found {classes_found} param.Parameterized classes in {library_name}")

        logger.info("External library cache population complete")

    def _discover_param_classes_in_library(self, library, library_name: str) -> int:
        """Discover and cache all param.Parameterized classes in a library."""
        classes_cached = 0

        # Get all classes in the library
        all_classes = self._get_all_classes_in_module(library)

        for cls in all_classes:
            try:
                # Check if it's a subclass of param.Parameterized
                if issubclass(cls, param.Parameterized) and cls != param.Parameterized:
                    module_name = getattr(cls, "__module__", "unknown")
                    class_name = getattr(cls, "__name__", "unknown")
                    full_path = f"{module_name}.{class_name}"

                    # Check if already cached to avoid unnecessary work
                    existing = external_library_cache.get(library_name, full_path)
                    if existing:
                        continue

                    # Introspect and cache the class
                    cache_data = self._introspect_param_class_for_cache(cls)
                    if cache_data:
                        external_library_cache.set(library_name, full_path, cache_data)
                        classes_cached += 1

            except (TypeError, AttributeError):
                # Skip classes that can't be processed
                continue

        return classes_cached

    def _get_all_classes_in_module(
        self, module, visited_modules: set[str] | None = None
    ) -> list[type]:
        """Recursively get all classes in a module and its submodules."""
        if visited_modules is None:
            visited_modules = set()

        module_name = getattr(module, "__name__", str(module))
        if module_name in visited_modules:
            return []
        visited_modules.add(module_name)

        classes = []

        # Get all attributes in the module
        for name in dir(module):
            if name.startswith("_"):
                continue

            try:
                attr = getattr(module, name)

                # Check if it's a class
                if isinstance(attr, type):
                    classes.append(attr)

                # Check if it's a submodule
                elif hasattr(attr, "__name__") and hasattr(attr, "__file__"):
                    attr_module_name = attr.__name__
                    # Only recurse into submodules of the current module
                    if attr_module_name.startswith(module_name + "."):
                        classes.extend(self._get_all_classes_in_module(attr, visited_modules))

            except (ImportError, AttributeError, TypeError):
                # Skip attributes that can't be imported or accessed
                continue

        return classes

    def _introspect_param_class_for_cache(self, cls) -> dict[str, Any] | None:
        """Introspect a param.Parameterized class and return cache-ready data."""
        try:
            # Extract parameter information using param's introspection
            parameters = []
            parameter_types = {}
            parameter_bounds = {}
            parameter_docs = {}
            parameter_allow_none = {}
            parameter_defaults = {}

            if hasattr(cls, "param"):
                for param_name, param_obj in cls.param.objects().items():
                    # Skip the 'name' parameter as it's rarely set in constructors
                    if param_name == "name":
                        continue
                    parameters.append(param_name)

                    if param_obj:
                        # Get parameter type
                        param_type_name = type(param_obj).__name__
                        parameter_types[param_name] = param_type_name

                        # Get bounds if present
                        if hasattr(param_obj, "bounds") and param_obj.bounds is not None:
                            bounds = param_obj.bounds
                            # Handle inclusive bounds
                            if hasattr(param_obj, "inclusive_bounds"):
                                inclusive_bounds = param_obj.inclusive_bounds
                                parameter_bounds[param_name] = (*bounds, *inclusive_bounds)
                            else:
                                parameter_bounds[param_name] = bounds

                        # Get doc string
                        if hasattr(param_obj, "doc") and param_obj.doc:
                            parameter_docs[param_name] = param_obj.doc

                        # Get allow_None
                        if hasattr(param_obj, "allow_None"):
                            parameter_allow_none[param_name] = param_obj.allow_None

                        # Get default value
                        if hasattr(param_obj, "default"):
                            parameter_defaults[param_name] = str(param_obj.default)

            return {
                "parameters": parameters,
                "parameter_types": parameter_types,
                "parameter_bounds": parameter_bounds,
                "parameter_docs": parameter_docs,
                "parameter_allow_none": parameter_allow_none,
                "parameter_defaults": parameter_defaults,
            }

        except Exception:
            return None
