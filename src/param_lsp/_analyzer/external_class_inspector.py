"""
External class introspection utilities.
Handles runtime introspection of external Param classes from libraries like Panel, HoloViews, etc.
"""

from __future__ import annotations

import importlib
import inspect
import logging
from typing import TYPE_CHECKING, Any

import param

from param_lsp.cache import external_library_cache
from param_lsp.constants import ALLOWED_EXTERNAL_LIBRARIES, SELECTOR_PARAM_TYPES
from param_lsp.models import ParameterInfo, ParameterizedInfo

if TYPE_CHECKING:
    import types

logger = logging.getLogger(__name__)


class ExternalClassInspector:
    """Runtime introspection and analysis of external Parameterized classes.

    This class provides comprehensive analysis of Parameterized classes from
    external libraries like Panel, HoloViews, Bokeh, and others. It uses
    runtime introspection to discover parameter definitions, inheritance
    hierarchies, and parameter metadata.

    Key capabilities:
    - Discovers all Parameterized classes in external libraries
    - Extracts parameter definitions with types, bounds, defaults
    - Caches results for performance
    - Handles complex inheritance hierarchies
    - Provides source location information when available

    The inspector maintains a cache of analyzed classes to avoid
    repeated expensive introspection operations.

    Attributes:
        external_param_classes: Cache of analyzed external classes
    """

    def __init__(self):
        self.external_param_classes: dict[str, ParameterizedInfo | None] = {}

    def populate_external_library_cache(self) -> None:
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

    def analyze_external_class_ast(self, full_class_path: str) -> ParameterizedInfo | None:
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

                        # Get objects for Selector parameters
                        objects = None
                        if (
                            cls_name in SELECTOR_PARAM_TYPES
                            and hasattr(param_obj, "objects")
                            and param_obj.objects is not None
                        ):
                            # Convert objects to string list
                            objects = [str(obj) for obj in param_obj.objects]

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

                        # Extract container constraints for List/Tuple parameters
                        item_type = None
                        length = None
                        if cls_name == "List" and hasattr(param_obj, "item_type"):
                            item_type = param_obj.item_type
                        elif cls_name == "Tuple" and hasattr(param_obj, "length"):
                            length = param_obj.length

                        # Create ParameterInfo object
                        param_info = ParameterInfo(
                            name=param_name,
                            cls=cls_name,
                            bounds=bounds,
                            doc=doc,
                            allow_None=allow_None,
                            default=default,
                            location=location,
                            objects=objects,
                            item_type=item_type,
                            length=length,
                        )
                        class_info.add_parameter(param_info)

            # Cache the class info directly
            external_library_cache.set(root_library, full_class_path, class_info)
            logger.debug(f"Cached introspection result for {full_class_path}")

            return class_info

        except Exception as e:
            logger.debug(f"Failed to introspect external class {full_class_path}: {e}")
            return None

    def _discover_param_classes_in_library(
        self, library: types.ModuleType, library_name: str
    ) -> int:
        """Discover and cache all param.Parameterized classes in a library."""
        if library is None:
            return 0

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
        self, module: types.ModuleType | None, visited_modules: set[str] | None = None
    ) -> list[type]:
        """Recursively get all classes in a module and its submodules."""
        if module is None:
            return []
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

    def _introspect_param_class_for_cache(self, cls: type | None) -> ParameterizedInfo | None:
        """Introspect a param.Parameterized class and return ParameterizedInfo."""
        try:
            # Check for invalid input
            if cls is None or not isinstance(cls, type):
                return None

            # Check if it's a built-in type
            if cls.__module__ == "builtins":
                return None

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

                        # Get objects for Selector parameters
                        objects = None
                        if (
                            cls_name in SELECTOR_PARAM_TYPES
                            and hasattr(param_obj, "objects")
                            and param_obj.objects is not None
                        ):
                            # Convert objects to string list
                            objects = [str(obj) for obj in param_obj.objects]

                        # Extract container constraints for List/Tuple parameters
                        item_type = None
                        length = None
                        if cls_name == "List" and hasattr(param_obj, "item_type"):
                            item_type = param_obj.item_type
                        elif cls_name == "Tuple" and hasattr(param_obj, "length"):
                            length = param_obj.length

                        # Create ParameterInfo object
                        param_info = ParameterInfo(
                            name=param_name,
                            cls=cls_name,
                            bounds=bounds,
                            doc=doc,
                            allow_None=allow_None,
                            default=default,
                            location=None,  # No location for external classes
                            objects=objects,
                            item_type=item_type,
                            length=length,
                        )
                        param_class_info.add_parameter(param_info)

            return param_class_info

        except Exception:
            return None

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
                return {"source": source_definition}
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

        # If we can't find the defining class and this is not a param class, return None
        if not hasattr(cls, "param"):
            return None

        # If we can't find the defining class but it is a param class, return the original class
        return cls

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
