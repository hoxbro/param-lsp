"""
HoloViz Param Language Server Protocol implementation.
Provides IDE support for Param-based Python code including autocompletion,
hover information, and diagnostics.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import re
from pathlib import Path
from typing import Any

import param
import parso

from .cache import external_library_cache
from .constants import ALLOWED_EXTERNAL_LIBRARIES, PARAM_TYPE_MAP, PARAM_TYPES
from .models import ParameterInfo, ParameterizedInfo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ParamAnalyzer:
    """Analyzes Python code for Param usage patterns."""

    def __init__(self, workspace_root: str | None = None):
        self.param_classes: dict[str, ParameterizedInfo] = {}
        self.imports: dict[str, str] = {}
        # Store file content for source line lookup
        self._current_file_content: str | None = None
        self.type_errors: list[dict[str, Any]] = []
        self.param_type_map = PARAM_TYPE_MAP

        # Workspace-wide analysis
        self.workspace_root = Path(workspace_root) if workspace_root else None
        self.module_cache: dict[str, dict[str, Any]] = {}  # module_name -> analysis_result
        self.file_cache: dict[str, dict[str, Any]] = {}  # file_path -> analysis_result

        # Cache for external Parameterized classes (AST-based detection)
        self.external_param_classes: dict[
            str, ParameterizedInfo | None
        ] = {}  # full_class_path -> class_info

        # Populate external library cache on initialization
        self._populate_external_library_cache()

    def analyze_file(self, content: str, file_path: str | None = None) -> dict[str, Any]:
        """Analyze a Python file for Param usage."""
        try:
            # Use parso with error recovery enabled for better handling of incomplete syntax
            grammar = parso.load_grammar()
            tree = grammar.parse(content, error_recovery=True)
            self._reset_analysis()
            self._current_file_path = file_path
            self._current_file_content = content

            # Log any syntax errors found by parso (but continue processing)
            errors = list(grammar.iter_errors(tree))
            if errors:
                logger.debug(
                    f"Found {len(errors)} syntax errors, but continuing with error recovery"
                )
                for error in errors:
                    logger.debug(f"Syntax error at {error.start_pos}: {error.message}")
        except Exception as e:
            # If parso completely fails, log and return empty result
            logger.error(f"Failed to parse file: {e}")
            return {}

        # First pass: collect imports
        for node in self._walk_tree(tree):
            if node.type == "import_name":
                self._handle_import(node)
            elif node.type == "import_from":
                self._handle_import_from(node)

        # Second pass: collect class definitions in order, respecting inheritance
        class_nodes = [node for node in self._walk_tree(tree) if node.type == "classdef"]

        # Process classes in dependency order (parents before children)
        processed_classes = set()
        while len(processed_classes) < len(class_nodes):
            progress_made = False
            for node in class_nodes:
                class_name = self._get_class_name(node)
                if not class_name or class_name in processed_classes:
                    continue

                # Check if all parent classes are processed or are external param classes
                can_process = True
                bases = self._get_class_bases(node)
                for base in bases:
                    if base.type == "name":
                        parent_name = base.value
                        # If it's a class defined in this file and not processed yet, wait
                        if (
                            any(
                                self._get_class_name(cn) == parent_name for cn in class_nodes
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
                    class_name = self._get_class_name(node)
                    if class_name and class_name not in processed_classes:
                        self._handle_class_def(node)
                        processed_classes.add(class_name)
                break

        # Pre-pass: discover all external Parameterized classes using parso
        self._discover_external_param_classes(tree)

        # Perform type inference after parsing
        self._check_parameter_types(tree, content.split("\n"))

        return {
            "param_classes": self.param_classes,
            "imports": self.imports,
            "type_errors": self.type_errors,
        }

    def _reset_analysis(self):
        """Reset analysis state."""
        self.param_classes.clear()
        self.imports.clear()
        self.type_errors.clear()

    def _walk_tree(self, node):
        """Walk a parso tree recursively, yielding all nodes."""
        yield node
        if hasattr(node, "children"):
            for child in node.children:
                yield from self._walk_tree(child)

    def _get_class_name(self, class_node):
        """Extract class name from parso classdef node."""
        for child in class_node.children:
            if child.type == "name":
                return child.value
        return None

    def _get_class_bases(self, class_node):
        """Extract base classes from parso classdef node."""
        bases = []
        # Look for bases between parentheses in class definition
        in_parentheses = False
        for child in class_node.children:
            if child.type == "operator" and child.value == "(":
                in_parentheses = True
            elif child.type == "operator" and child.value == ")":
                in_parentheses = False
            elif in_parentheses:
                if child.type == "name":
                    bases.append(child)
                elif child.type in ("atom_expr", "power"):
                    # Handle dotted names like module.Class or param.Parameterized
                    bases.append(child)
                elif child.type == "arglist":
                    # Multiple bases in argument list
                    for arg_child in child.children:
                        if arg_child.type == "name":
                            bases.append(arg_child)
                        elif arg_child.type in ("atom_expr", "power"):
                            bases.append(arg_child)
        return bases

    def _is_assignment_stmt(self, node):
        """Check if a parso node is an assignment statement."""
        # Look for assignment operator '=' in the children
        return any(child.type == "operator" and child.value == "=" for child in node.children)

    def _get_assignment_target_name(self, node):
        """Get the target name from an assignment statement."""
        # The target is typically the first child before the '=' operator
        for child in node.children:
            if child.type == "name":
                return child.value
            elif child.type == "operator" and child.value == "=":
                break
        return None

    def _is_parameter_assignment(self, node):
        """Check if a parso assignment statement looks like a parameter definition."""
        # Find the right-hand side of the assignment (after '=')
        found_equals = False
        for child in node.children:
            if child.type == "operator" and child.value == "=":
                found_equals = True
            elif found_equals and child.type in ("power", "atom_expr"):
                # Check if it's a parameter type call
                return self._is_parameter_call(child)
        return False

    def _is_parameter_call(self, node):
        """Check if a parso power/atom_expr node represents a parameter type call."""
        # Extract the function name and check if it's a param type
        func_name = None

        # Look through children to find the actual function being called
        for child in node.children:
            if child.type == "name":
                # This might be the module name (e.g., "param")
                continue
            elif child.type == "trailer":
                # Handle dotted calls like param.Integer
                for trailer_child in child.children:
                    if trailer_child.type == "name":
                        func_name = trailer_child.value
                        break
                # If we found a function name in a trailer, that's likely the param type
                if func_name:
                    break

        if func_name:
            return func_name in PARAM_TYPES
        return False

    def _has_attribute_target(self, node):
        """Check if assignment has an attribute target (like obj.attr = value)."""
        for child in node.children:
            if child.type == "power":
                # Check if this power node has attribute access (trailer with '.')
                for power_child in child.children:
                    if (
                        power_child.type == "trailer"
                        and power_child.children
                        and power_child.children[0].value == "."
                    ):
                        return True
            elif child.type == "operator" and child.value == "=":
                break
        return False

    def _is_function_call(self, node):
        """Check if a parso power node represents a function call."""
        return any(
            child.type == "trailer" and child.children and child.children[0].value == "("
            for child in node.children
        )

    def _handle_import(self, node):
        """Handle 'import' statements (parso node)."""
        # For parso import_name nodes, parse the import statement
        for child in node.children:
            if child.type == "name":
                # Simple case: "import module"
                module_name = child.value
                self.imports[module_name] = module_name
            elif child.type == "dotted_as_names":
                for name_child in child.children:
                    if name_child.type == "dotted_as_name":
                        # Handle "import module as alias"
                        parts = []
                        alias_name = None
                        for part in name_child.children:
                            if part.type == "dotted_name":
                                parts.append(part.value)
                            elif part.type == "name" and parts:
                                alias_name = part.value
                        if parts:
                            module_name = parts[0]
                            self.imports[alias_name or module_name] = module_name
                    elif name_child.type == "dotted_name":
                        # Handle "import module"
                        module_name = name_child.value
                        self.imports[module_name] = module_name

    def _handle_import_from(self, node):
        """Handle 'from ... import ...' statements (parso node)."""
        # For parso import_from nodes, parse the from...import statement
        module_name = None

        for child in node.children:
            if child.type == "dotted_name" and module_name is None:
                module_name = child.value
            elif child.type == "import_as_names":
                for name_child in child.children:
                    if name_child.type == "import_as_name":
                        # Handle "from module import name as alias"
                        import_name = None
                        alias_name = None
                        for part in name_child.children:
                            if part.type == "name":
                                if import_name is None:
                                    import_name = part.value
                                else:
                                    alias_name = part.value
                        if import_name and module_name:
                            full_name = f"{module_name}.{import_name}"
                            self.imports[alias_name or import_name] = full_name
                    elif name_child.type == "name":
                        # Handle "from module import name"
                        import_name = name_child.value
                        if module_name:
                            full_name = f"{module_name}.{import_name}"
                            self.imports[import_name] = full_name

    def _handle_class_def(self, node):
        """Handle class definitions that might inherit from param.Parameterized (parso node)."""
        # Check if class inherits from param.Parameterized (directly or indirectly)
        is_param_class = False
        bases = self._get_class_bases(node)
        for base in bases:
            if self._is_param_base(base):
                is_param_class = True
                break

        if is_param_class:
            class_name = self._get_class_name(node)
            class_info = ParameterizedInfo(name=class_name)

            # Get inherited parameters from parent classes first
            inherited_parameters = self._collect_inherited_parameters(
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
            return base.value
        elif base.type == "power":
            # Handle dotted names like module.Class
            parts = []
            for child in base.children:
                if child.type == "name":
                    parts.append(child.value)
                elif child.type == "trailer":
                    for trailer_child in child.children:
                        if trailer_child.type == "name":
                            parts.append(trailer_child.value)
            return ".".join(parts)
        return str(base.type)

    def _is_param_base(self, base) -> bool:
        """Check if a base class is param.Parameterized or similar (parso node)."""
        if base.type == "name":
            base_name = base.value
            # Check if it's a direct param.Parameterized import
            if (
                base_name in ["Parameterized"]
                and base_name in self.imports
                and "param.Parameterized" in self.imports[base_name]
            ):
                return True
            # Check if it's a known param class (from inheritance)
            if base_name in self.param_classes:
                return True
            # Check if it's an imported param class
            imported_class_info = self._get_imported_param_class_info(
                base_name, base_name, getattr(self, "_current_file_path", None)
            )
            if imported_class_info:
                return True
        elif base.type in ("power", "atom_expr"):
            # Handle dotted names like param.Parameterized or pn.widgets.IntSlider
            parts = []
            for child in base.children:
                if child.type == "name":
                    parts.append(child.value)
                elif child.type == "trailer":
                    for trailer_child in child.children:
                        if trailer_child.type == "name":
                            parts.append(trailer_child.value)

            if len(parts) >= 2:
                # Handle simple case: param.Parameterized
                if len(parts) == 2:
                    module, class_name = parts
                    if (module == "param" and class_name == "Parameterized") or (
                        module in self.imports
                        and self.imports[module].endswith("param")
                        and class_name == "Parameterized"
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
        self, node, current_file_path: str | None = None
    ) -> dict[str, ParameterInfo]:
        """Collect parameters from parent classes in inheritance hierarchy (parso node)."""
        inherited_parameters = {}  # Last wins

        bases = self._get_class_bases(node)
        for base in bases:
            if base.type == "name":
                parent_class_name = base.value

                # First check if it's a local class in the same file
                if parent_class_name in self.param_classes:
                    # Get parameters from the parent class
                    parent_class_info = self.param_classes[parent_class_name]
                    for param_name, param_info in parent_class_info.parameters.items():
                        inherited_parameters[param_name] = param_info  # noqa: PERF403

                # If not found locally, check if it's an imported class
                else:
                    # Check if this class was imported
                    imported_class_info = self._get_imported_param_class_info(
                        parent_class_name, parent_class_name, current_file_path
                    )

                    if imported_class_info:
                        for param_name, param_info in imported_class_info.parameters.items():
                            inherited_parameters[param_name] = param_info  # noqa: PERF403

            elif base.type in ("atom_expr", "power"):
                # Handle complex attribute access like pn.widgets.IntSlider
                full_class_path = self._resolve_full_class_path(base)
                if full_class_path:
                    # Check if this external class is a Parameterized class
                    class_info = self._analyze_external_class_ast(full_class_path)
                    if class_info:
                        for param_name, param_info in class_info.parameters.items():
                            inherited_parameters[param_name] = param_info  # noqa: PERF403

        return inherited_parameters

    def _extract_parameters(self, node) -> list[ParameterInfo]:
        """Extract parameter definitions from a Param class (parso node)."""
        parameters = []

        # Find the suite (class body) in the class definition
        for child in node.children:
            if child.type == "suite":
                for item in child.children:
                    if item.type == "expr_stmt" and self._is_assignment_stmt(item):
                        target_name = self._get_assignment_target_name(item)
                        if target_name and self._is_parameter_assignment(item):
                            # Extract parameter information
                            param_info = self._extract_parameter_info_from_assignment(item, target_name)
                            if param_info:
                                parameters.append(param_info)
                    elif item.type == "simple_stmt":
                        # Also check within simple statements for other formats
                        for stmt_child in item.children:
                            if stmt_child.type == "expr_stmt" and self._is_assignment_stmt(stmt_child):
                                target_name = self._get_assignment_target_name(stmt_child)
                                if target_name and self._is_parameter_assignment(stmt_child):
                                    # Extract parameter information
                                    param_info = self._extract_parameter_info_from_assignment(stmt_child, target_name)
                                    if param_info:
                                        parameters.append(param_info)

        return parameters

    def _extract_parameter_info_from_assignment(self, assignment_node, param_name: str) -> ParameterInfo | None:
        """Extract parameter info from a parso assignment statement."""
        # Initialize parameter info
        cls = ""
        bounds = None
        doc = None
        allow_None = False
        default = None
        location = None

        # Get the parameter call (right-hand side of assignment)
        param_call = None
        found_equals = False
        for child in assignment_node.children:
            if child.type == "operator" and child.value == "=":
                found_equals = True
            elif found_equals and child.type in ("power", "atom_expr"):
                param_call = child
                break

        if param_call:
            # Get parameter type from the function call
            param_class_info = self._resolve_parameter_class(param_call)
            if param_class_info:
                cls = param_class_info["type"]

            # Extract parameter arguments (bounds, doc, default, etc.) from the whole param_call
            bounds = self._extract_bounds_from_call(param_call)
            doc = self._extract_doc_from_call(param_call)
            allow_None_value = self._extract_allow_None_from_call(param_call)
            default_value = self._extract_default_from_call(param_call)

            # Store default value as a string representation
            if default_value is not None:
                default = self._format_default_value(default_value)

            # Param automatically sets allow_None=True when default=None
            if default_value is not None and self._is_none_value(default_value):
                allow_None = True
            elif allow_None_value is not None:
                allow_None = allow_None_value

        # Create ParameterInfo object
        return ParameterInfo(
            name=param_name,
            cls=cls or "Unknown",
            bounds=bounds,
            doc=doc,
            allow_None=allow_None,
            default=default,
            location=location,
        )

    def _resolve_parameter_class(self, param_call):
        """Resolve parameter class from a parso power node like param.Integer()."""
        # Extract the function name from the call
        func_name = None
        module_name = None

        for child in param_call.children:
            if child.type == "name":
                # Simple case: Integer()
                func_name = child.value
                break
            elif child.type == "trailer":
                # Handle dotted calls like param.Integer
                for trailer_child in child.children:
                    if trailer_child.type == "name":
                        if module_name is None:
                            module_name = func_name  # Previous name becomes module
                        func_name = trailer_child.value

        if func_name:
            return PARAM_TYPE_MAP.get(func_name)
        return None

    def _extract_bounds_from_call(self, call_trailer):
        """Extract bounds from parameter call trailer (parso node)."""
        # Look for bounds=(...) in the argument list
        # Implementation depends on parsing the arguments within the trailer
        return None

    def _extract_doc_from_call(self, call_trailer):
        """Extract doc from parameter call trailer (parso node)."""
        # Look for doc="..." in the argument list
        return None

    def _extract_allow_None_from_call(self, call_trailer):
        """Extract allow_None from parameter call trailer (parso node)."""
        # Look for allow_None=True/False in the argument list
        return None

    def _extract_default_from_call(self, call_trailer):
        """Extract default from parameter call trailer (parso node)."""
        # Look for default=value in the argument list
        return None

    def _format_default_value(self, default_value):
        """Format default value from parso node."""
        # Convert parso node to string representation
        if hasattr(default_value, 'get_code'):
            return default_value.get_code()
        return str(default_value)

    def _is_none_value(self, value):
        """Check if parso node represents None value."""
        return (hasattr(value, 'type') and value.type == 'name' and
                hasattr(value, 'value') and value.value == 'None')

    def _get_keyword_arguments(self, call_node) -> dict[str, Any]:
        """Extract keyword arguments from a parso function call node."""
        kwargs = {}

        # Find the arglist in the function call
        for child in call_node.children:
            if child.type == "trailer" and child.children and child.children[0].value == "(":
                # Look for arglist within this trailer
                for trailer_child in child.children:
                    if trailer_child.type == "arglist":
                        # Parse arguments in the arglist
                        for arg_child in trailer_child.children:
                            if arg_child.type == "argument":
                                # This is a keyword argument (name=value)
                                if len(arg_child.children) >= 3:
                                    name_node = arg_child.children[0]
                                    equals_node = arg_child.children[1]
                                    value_node = arg_child.children[2]

                                    if (name_node.type == "name" and
                                        equals_node.type == "operator" and equals_node.value == "="):
                                        kwargs[name_node.value] = value_node

        return kwargs

    def _extract_bounds_from_call(self, call_node) -> tuple | None:
        """Extract bounds from a parameter call (parso version)."""
        bounds_info = None
        inclusive_bounds = (True, True)  # Default to inclusive

        kwargs = self._get_keyword_arguments(call_node)

        if "bounds" in kwargs:
            bounds_node = kwargs["bounds"]
            # Check if it's a tuple/parentheses with 2 elements
            if bounds_node.type == "atom" and bounds_node.children:
                # Look for (min, max) pattern
                for child in bounds_node.children:
                    if child.type == "testlist_comp":
                        elements = [c for c in child.children if c.type in ("number", "name")]
                        if len(elements) >= 2:
                            min_val = self._extract_numeric_value(elements[0])
                            max_val = self._extract_numeric_value(elements[1])
                            # Accept bounds even if one side is None (unbounded)
                            if min_val is not None or max_val is not None:
                                bounds_info = (min_val, max_val)

        if "inclusive_bounds" in kwargs:
            inclusive_bounds_node = kwargs["inclusive_bounds"]
            # Similar logic for inclusive bounds tuple
            if inclusive_bounds_node.type == "atom" and inclusive_bounds_node.children:
                for child in inclusive_bounds_node.children:
                    if child.type == "testlist_comp":
                        elements = [c for c in child.children if c.type in ("name",)]
                        if len(elements) >= 2:
                            left_inclusive = self._extract_boolean_value(elements[0])
                            right_inclusive = self._extract_boolean_value(elements[1])
                            if left_inclusive is not None and right_inclusive is not None:
                                inclusive_bounds = (left_inclusive, right_inclusive)

        if bounds_info:
            # Return (min, max, left_inclusive, right_inclusive)
            return (*bounds_info, *inclusive_bounds)
        return None

    def _extract_doc_from_call(self, call_node) -> str | None:
        """Extract doc string from a parameter call (parso version)."""
        kwargs = self._get_keyword_arguments(call_node)
        if "doc" in kwargs:
            return self._extract_string_value(kwargs["doc"])
        return None

    def _extract_allow_None_from_call(self, call_node) -> bool | None:
        """Extract allow_None from a parameter call (parso version)."""
        kwargs = self._get_keyword_arguments(call_node)
        if "allow_None" in kwargs:
            return self._extract_boolean_value(kwargs["allow_None"])
        return None

    def _extract_default_from_call(self, call_node):
        """Extract default value from a parameter call (parso version)."""
        kwargs = self._get_keyword_arguments(call_node)
        if "default" in kwargs:
            return kwargs["default"]
        return None

    def _is_none_value(self, node) -> bool:
        """Check if a parso node represents None."""
        return (hasattr(node, 'type') and node.type == 'name' and
                hasattr(node, 'value') and node.value == 'None')

    def _extract_string_value(self, node) -> str | None:
        """Extract string value from parso node."""
        if hasattr(node, 'type') and node.type == 'string':
            # Remove quotes from string value
            value = node.value
            if value.startswith('"') and value.endswith('"'):
                return value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                return value[1:-1]
            return value
        return None

    def _extract_boolean_value(self, node) -> bool | None:
        """Extract boolean value from parso node."""
        if hasattr(node, 'type') and node.type == 'name':
            if node.value == 'True':
                return True
            elif node.value == 'False':
                return False
        return None

    def _format_default_value(self, node) -> str:
        """Format a parso node as a string representation for display."""
        # For parso nodes, use the get_code() method to get the original source
        if hasattr(node, 'get_code'):
            return node.get_code().strip()
        elif hasattr(node, 'value'):
            return str(node.value)
        else:
            return "<complex>"


    def _check_parameter_types(self, tree, lines: list[str]):
        """Check for type errors in parameter assignments."""
        for node in self._walk_tree(tree):
            if node.type == "classdef":
                class_name = self._get_class_name(node)
                if class_name and class_name in self.param_classes:
                    # Find the suite (class body) in the class definition
                    for child in node.children:
                        if child.type == "suite":
                            for item in child.children:
                                if item.type == "simple_stmt":
                                    # Look for assignments within simple statements
                                    for stmt_child in item.children:
                                        if (
                                            stmt_child.type == "expr_stmt"
                                            and self._is_assignment_stmt(stmt_child)
                                        ):
                                            target_name = self._get_assignment_target_name(
                                                stmt_child
                                            )
                                            if target_name and self._is_parameter_assignment(
                                                stmt_child
                                            ):
                                                self._check_parameter_default_type(
                                                    stmt_child, target_name, lines
                                                )

            # Check runtime parameter assignments like obj.param = value
            elif node.type == "expr_stmt" and self._is_assignment_stmt(node):
                if self._has_attribute_target(node):
                    self._check_runtime_parameter_assignment(node, None, lines)

            # Check constructor calls like MyClass(x="A")
            elif node.type == "power" and self._is_function_call(node):
                self._check_constructor_parameter_types(node, lines)

    def _check_constructor_parameter_types(self, node, lines: list[str]):
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
        kwargs = self._get_keyword_arguments(node)

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
                    if not (
                        isinstance(param_value, ast.Constant)
                        and isinstance(param_value.value, bool)
                    ):
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
        node: ast.Call,
        class_name: str,
        param_name: str,
        cls: str,
        param_value: ast.expr,
    ):
        """Check if constructor parameter value is within parameter bounds."""
        # Only check bounds for numeric types
        if cls not in ["Number", "Integer"]:
            return

        # Get bounds for this parameter
        bounds = self._get_parameter_bounds(class_name, param_name)
        if not bounds:
            return

        # Extract numeric value from parameter value
        assigned_numeric = self._extract_numeric_value(param_value)
        if assigned_numeric is None:
            return

        # Handle bounds format (min, max) or (min, max, left_inclusive, right_inclusive)
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
            message = f"Value {assigned_numeric} for parameter '{param_name}' in {class_name}() constructor is outside bounds {bound_description}"
            self._create_type_error(node, message, "constructor-bounds-violation")

    def _check_parameter_default_type(self, node, param_name: str, lines: list[str]):
        """Check if parameter default value matches declared type (parso version)."""
        # Find the parameter call on the right side of the assignment
        param_call = None
        for child in node.children:
            if child.type in ("power", "atom_expr"):
                param_call = child
                break

        if not param_call:
            return

        # Resolve the actual parameter class type
        param_class_info = self._resolve_parameter_class(param_call)
        if not param_class_info:
            return

        cls = param_class_info["type"]

        # Get default value and allow_None from keyword arguments
        kwargs = self._get_keyword_arguments(param_call)
        default_value = kwargs.get("default")
        allow_None = self._extract_boolean_value(kwargs.get("allow_None")) if "allow_None" in kwargs else None

        # Param automatically sets allow_None=True when default=None
        if default_value is not None and self._is_none_value(default_value):
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
                if not (default_value.type == "name" and default_value.value in ("True", "False")):
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

        # Check if this is a valid param class (local or external)
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
                # If allow_None is False or not specified, continue with normal type checking

            # Special handling for Boolean parameters - they should only accept actual bool values
            if cls == "Boolean" and inferred_type and inferred_type is not bool:
                # For Boolean parameters, only accept actual boolean values
                if not (
                    isinstance(assigned_value, ast.Constant)
                    and isinstance(assigned_value.value, bool)
                ):
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
        self._check_runtime_bounds(node, instance_class, param_name, cls, assigned_value)

    def _check_runtime_bounds(
        self,
        node: ast.Assign,
        instance_class: str,
        param_name: str,
        cls: str,
        assigned_value: ast.expr,
    ):
        """Check if assigned value is within parameter bounds."""
        # Only check bounds for numeric types
        if cls not in ["Number", "Integer"]:
            return

        # Get bounds for this parameter
        bounds = self._get_parameter_bounds(instance_class, param_name)
        if not bounds:
            return

        # Extract numeric value from assigned value
        assigned_numeric = self._extract_numeric_value(assigned_value)
        if assigned_numeric is None:
            return

        # Handle bounds format (min, max) or (min, max, left_inclusive, right_inclusive)
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
            # Look for the function name in the node children
            for child in call_node.children:
                if child.type == "name":
                    # Simple case: MyClass()
                    return child.value
                elif child.type == "trailer" and len(child.children) >= 2:
                    # Could be module.Class case - need to construct full path
                    # For now, just return the class name from the last trailer
                    if child.children[1].type == "name":
                        # Try to resolve the full class path for external classes
                        full_class_path = self._resolve_full_class_path(call_node)
                        if full_class_path:
                            # Check if this is an external Parameterized class
                            class_info = self._analyze_external_class_ast(full_class_path)
                            if class_info:
                                # Return the full path as the class identifier for external classes
                                return full_class_path
                        # Fallback to just the class name
                        return child.children[1].value
        return None

    def _resolve_full_class_path(self, base) -> str | None:
        """Resolve the full class path from a parso power/atom_expr node like pn.widgets.IntSlider."""
        parts = []
        for child in base.children:
            if child.type == "name":
                parts.append(child.value)
            elif child.type == "trailer":
                for trailer_child in child.children:
                    if trailer_child.type == "name":
                        parts.append(trailer_child.value)

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

    def _create_type_error(
        self, node: ast.Call | ast.Assign, message: str, code: str, severity: str = "error"
    ) -> None:
        """Helper function to create and append a type error."""
        self.type_errors.append(
            {
                "line": node.lineno - 1,  # Convert to 0-based
                "col": node.col_offset,
                "end_line": node.end_lineno - 1 if node.end_lineno else node.lineno - 1,
                "end_col": node.end_col_offset if node.end_col_offset else node.col_offset,
                "message": message,
                "severity": severity,
                "code": code,
            }
        )

    def _infer_value_type(self, node) -> type | None:
        """Infer Python type from parso node."""
        if hasattr(node, 'type'):
            if node.type == 'number':
                # Check if it's a float or int
                if '.' in node.value:
                    return float
                else:
                    return int
            elif node.type == 'string':
                return str
            elif node.type == 'name':
                if node.value == 'True' or node.value == 'False':
                    return bool
                elif node.value == 'None':
                    return type(None)
                # Could be a variable - would need more sophisticated analysis
                return None
            elif node.type == 'atom':
                # Check for list, dict, tuple
                if node.children and node.children[0].value == '[':
                    return list
                elif node.children and node.children[0].value == '{':
                    return dict
                elif node.children and node.children[0].value == '(':
                    return tuple
        return None

    def _check_parameter_constraints(self, node, param_name: str, lines: list[str]):
        """Check for parameter-specific constraints (parso version)."""
        # Find the parameter call on the right side of the assignment
        param_call = None
        for child in node.children:
            if child.type in ("power", "atom_expr"):
                param_call = child
                break

        if not param_call:
            return

        # Resolve the actual parameter class type for constraint checking
        param_class_info = self._resolve_parameter_class(param_call)
        if not param_class_info:
            return

        resolved_cls = param_class_info["type"]

        # Get keyword arguments
        kwargs = self._get_keyword_arguments(param_call)

        # Check bounds for Number/Integer parameters
        if resolved_cls in ["Number", "Integer"]:
            bounds_node = kwargs.get("bounds")
            inclusive_bounds_node = kwargs.get("inclusive_bounds")
            default_value = kwargs.get("default")

            inclusive_bounds = (True, True)  # Default to inclusive

            # Parse inclusive_bounds if present
            if inclusive_bounds_node and inclusive_bounds_node.type == "atom":
                # Parse (True, False) pattern
                for child in inclusive_bounds_node.children:
                    if child.type == "testlist_comp":
                        elements = [c for c in child.children if c.type == "name"]
                        if len(elements) >= 2:
                            left_inclusive = self._extract_boolean_value(elements[0])
                            right_inclusive = self._extract_boolean_value(elements[1])
                            if left_inclusive is not None and right_inclusive is not None:
                                inclusive_bounds = (left_inclusive, right_inclusive)

            # Parse bounds if present
            if bounds_node and bounds_node.type == "atom":
                # Parse (min, max) pattern
                for child in bounds_node.children:
                    if child.type == "testlist_comp":
                        elements = [c for c in child.children if c.type in ("number", "name")]
                        if len(elements) >= 2:
                            try:
                                min_val = self._extract_numeric_value(elements[0])
                                max_val = self._extract_numeric_value(elements[1])

                                if min_val is not None and max_val is not None and min_val >= max_val:
                                    message = f"Parameter '{param_name}' has invalid bounds: min ({min_val}) >= max ({max_val})"
                                    self._create_type_error(node, message, "invalid-bounds")

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
                                            message = f"Default value {default_numeric} for parameter '{param_name}' is outside bounds {bound_description}"
                                            self._create_type_error(node, message, "default-bounds-violation")

                            except (ValueError, TypeError):
                                pass

        # Check for empty lists/tuples with List/Tuple parameters
        elif resolved_cls in ["List", "Tuple"]:
            default_value = kwargs.get("default")
            if default_value and default_value.type == "atom":
                # Check if it's an empty list or tuple
                for child in default_value.children:
                    if child.type in ("testlist_comp",) and not child.children:
                        # Empty list/tuple - check if bounds are specified
                        if "bounds" in kwargs:
                            message = (
                                f"Parameter '{param_name}' has empty default but bounds specified"
                            )
                            self._create_type_error(
                                node, message, "empty-default-with-bounds", "warning"
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

    def _extract_numeric_value(self, node) -> float | int | None:
        """Extract numeric value from parso node."""
        if hasattr(node, 'type') and node.type == 'number':
            try:
                # Try to parse as int first, then float
                if '.' in node.value:
                    return float(node.value)
                else:
                    return int(node.value)
            except ValueError:
                return None
        elif hasattr(node, 'type') and node.type == 'name' and node.value == 'None':
            return None  # Explicitly handle None
        # TODO: Handle negative numbers (unary minus)
        return None

    def _analyze_external_class_ast(self, full_class_path: str) -> ParameterizedInfo | None:
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

    def _introspect_external_class_runtime(self, full_class_path: str) -> ParameterizedInfo | None:
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
            class_info = ParameterizedInfo(name=full_class_path.split(".")[-1])

            if hasattr(cls, "param"):
                for param_name, param_obj in cls.param.objects().items():
                    # Skip the 'name' parameter as it's rarely set in constructors
                    if param_name == "name":
                        continue

                    if param_obj:
                        # Get parameter type
                        cls_name = type(param_obj).__name__

                        # Get bounds if present
                        bounds = None
                        if hasattr(param_obj, "bounds") and param_obj.bounds is not None:
                            bounds_tuple = param_obj.bounds
                            # Handle inclusive bounds
                            if hasattr(param_obj, "inclusive_bounds"):
                                inclusive_bounds = param_obj.inclusive_bounds
                                bounds = (*bounds_tuple, *inclusive_bounds)
                            else:
                                bounds = bounds_tuple

                        # Get doc string
                        doc = (
                            param_obj.doc if hasattr(param_obj, "doc") and param_obj.doc else None
                        )

                        # Get allow_None
                        allow_None = (
                            param_obj.allow_None if hasattr(param_obj, "allow_None") else False
                        )

                        # Get default value
                        default = str(param_obj.default) if hasattr(param_obj, "default") else None

                        # Try to get source file location for the parameter
                        location = None
                        try:
                            source_location = self._get_parameter_source_location(
                                param_obj, cls, param_name
                            )
                            if source_location:
                                location = source_location
                        except Exception as e:
                            # If we can't get source location, just continue without it
                            logger.debug(f"Could not get source location for {param_name}: {e}")

                        # Create ParameterInfo object
                        param_info = ParameterInfo(
                            name=param_name,
                            cls=cls_name,
                            bounds=bounds,
                            doc=doc,
                            allow_None=allow_None,
                            default=default,
                            location=location,
                        )
                        class_info.add_parameter(param_info)

            # Cache the class info directly
            external_library_cache.set(root_library, full_class_path, class_info)
            logger.debug(f"Cached introspection result for {full_class_path}")

            return class_info

        except Exception as e:
            logger.debug(f"Failed to introspect external class {full_class_path}: {e}")
            return None

    def _get_parameter_source_location(
        self, param_obj: Any, cls: type, param_name: str
    ) -> dict[str, Any] | None:
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

    def _discover_external_param_classes(self, tree):
        """Pre-pass to discover all external Parameterized classes using parso analysis."""
        for node in self._walk_tree(tree):
            if node.type == "power":
                # Look for calls like pn.widgets.IntSlider()
                # Check if this is a function call with parentheses
                has_call = any(
                    child.type == "trailer" and child.children and child.children[0].value == "("
                    for child in node.children
                )
                if has_call:
                    full_class_path = self._resolve_full_class_path(node)
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
                    class_info = self._introspect_param_class_for_cache(cls)
                    if class_info:
                        external_library_cache.set(library_name, full_path, class_info)
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

    def _introspect_param_class_for_cache(self, cls) -> ParameterizedInfo | None:
        """Introspect a param.Parameterized class and return ParameterizedInfo."""
        try:
            class_name = getattr(cls, "__name__", "Unknown")
            param_class_info = ParameterizedInfo(name=class_name)

            if hasattr(cls, "param"):
                for param_name, param_obj in cls.param.objects().items():
                    # Skip the 'name' parameter as it's rarely set in constructors
                    if param_name == "name":
                        continue

                    if param_obj:
                        # Get parameter type
                        cls_name = type(param_obj).__name__

                        # Get bounds if present
                        bounds = None
                        if hasattr(param_obj, "bounds") and param_obj.bounds is not None:
                            bounds_tuple = param_obj.bounds
                            # Handle inclusive bounds
                            if hasattr(param_obj, "inclusive_bounds"):
                                inclusive_bounds = param_obj.inclusive_bounds
                                bounds = (*bounds_tuple, *inclusive_bounds)
                            else:
                                bounds = bounds_tuple

                        # Get doc string
                        doc = (
                            param_obj.doc if hasattr(param_obj, "doc") and param_obj.doc else None
                        )

                        # Get allow_None
                        allow_None = (
                            param_obj.allow_None if hasattr(param_obj, "allow_None") else False
                        )

                        # Get default value
                        default = str(param_obj.default) if hasattr(param_obj, "default") else None

                        # Create ParameterInfo object
                        param_info = ParameterInfo(
                            name=param_name,
                            cls=cls_name,
                            bounds=bounds,
                            doc=doc,
                            allow_None=allow_None,
                            default=default,
                            location=None,  # No location for external classes
                        )
                        param_class_info.add_parameter(param_info)

            return param_class_info

        except Exception:
            return None

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
