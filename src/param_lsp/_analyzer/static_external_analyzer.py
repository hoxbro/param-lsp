"""
Static external class analyzer for param-lsp.

This module provides static analysis of external Parameterized classes without
runtime module loading. It uses AST parsing to extract parameter information
from source files directly.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

from param_lsp import _treesitter
from param_lsp._logging import get_logger
from param_lsp._treesitter.queries import find_classes, find_imports
from param_lsp.cache import external_library_cache
from param_lsp.constants import ALLOWED_EXTERNAL_LIBRARIES
from param_lsp.models import ParameterInfo, ParameterizedInfo

from .ast_navigator import ImportHandler, ParameterDetector
from .parameter_extractor import extract_parameter_info_from_assignment
from .python_environment import PythonEnvironment

if TYPE_CHECKING:
    from pathlib import Path

    from tree_sitter import Node


logger = get_logger(__name__, "cache")

_STDLIB_MODULES = tuple(f"{c}." for c in ("__future__", *sys.stdlib_module_names))


class ExternalClassInspector:
    """Static analyzer for external Parameterized classes.

    Analyzes external libraries using pure AST parsing without runtime imports.
    Discovers source files and extracts parameter information statically.

    Can analyze libraries from different Python environments by providing a
    PythonEnvironment instance.
    """

    def __init__(self, python_env: PythonEnvironment | None = None):
        """
        Initialize the external class inspector.

        Args:
            python_env: Python environment to analyze. If None, uses current environment.
        """
        self.library_source_paths: dict[str, list[Path]] = {}
        self.parsed_classes: dict[str, ParameterizedInfo | None] = {}
        self.analyzed_files: dict[Path, dict[str, Any]] = {}
        # Store source lines for parameter extraction
        self.file_source_cache: dict[Path, list[str]] = {}
        # Cache all class AST nodes for inheritance resolution
        self.class_ast_cache: dict[str, tuple[Node, dict[str, str]]] = {}
        # Multi-file analysis queue
        self.analysis_queue: list[tuple[Path, str]] = []  # (file_path, reason)
        self.currently_analyzing: set[Path] = set()  # Prevent circular analysis
        self.current_file_context: Path | None = None  # Track current file for import resolution
        # Track which libraries have been pre-populated in this session
        self.populated_libraries: set[str] = set()

        # Python environment for analysis
        if python_env is None:
            python_env = PythonEnvironment.from_current()
        self.python_env = python_env

    def _get_library_version(self, library_name: str) -> str | None:
        """Query library version from the external Python environment.

        Args:
            library_name: Name of the library

        Returns:
            Version string or None if unable to determine
        """
        import subprocess

        try:
            result = subprocess.run(  # noqa: S603
                [
                    str(self.python_env.python),
                    "-c",
                    f"import importlib.metadata; print(importlib.metadata.version('{library_name}'))",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                logger.debug(f"Got version {version} for {library_name}")
                return version
            else:
                logger.debug(f"Failed to get version for {library_name}: {result.stderr}")
                return None
        except Exception as e:
            logger.debug(f"Error getting version for {library_name}: {e}")
            return None

    def _get_library_dependencies(self, library_name: str) -> list[str]:
        """Get dependencies of a library that are also in ALLOWED_EXTERNAL_LIBRARIES.

        Args:
            library_name: Name of the library to check

        Returns:
            List of dependency library names that are allowed external libraries
        """
        dependencies = []
        try:
            # Query metadata from the custom python environment, not the current one
            import json
            import subprocess

            result = subprocess.run(  # noqa: S603
                [
                    str(self.python_env.python),
                    "-c",
                    f"import importlib.metadata, json; "
                    f"m = importlib.metadata.metadata('{library_name}'); "
                    f"print(json.dumps(list(m.get_all('Requires-Dist') or [])))",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                requires = json.loads(result.stdout.strip())
                for req in requires:
                    # Parse requirement string (e.g., "panel>=1.0" -> "panel")
                    dep_name = (
                        req.split(";")[0].split(">=")[0].split("==")[0].split("<")[0].strip()
                    )

                    # Only include if it's in our allowed list
                    if dep_name in ALLOWED_EXTERNAL_LIBRARIES and dep_name != library_name:
                        dependencies.append(dep_name)
                        logger.debug(f"Found dependency: {library_name} -> {dep_name}")
            else:
                logger.debug(f"Failed to query metadata for {library_name}: {result.stderr}")

        except Exception as e:
            logger.debug(f"Could not get dependencies for {library_name}: {e}")

        return dependencies

    def _build_reexport_map(
        self,
        library_name: str,
        file_data: dict[Path, tuple[Any, dict[str, str], list[str]]],
    ) -> dict[str, str]:
        """Build a map of re-exported class paths from __init__.py files.

        Parses __init__.py files to understand re-exports like:
            from .input import TextInput
        And builds aliases:
            panel.widgets.TextInput -> panel.widgets.input.TextInput

        Args:
            library_name: Name of the library (e.g., "panel")
            file_data: Dictionary mapping file paths to (tree, imports, source_lines)

        Returns:
            Dictionary mapping short paths (re-exported) to full paths (actual definition)
        """
        reexport_map: dict[str, str] = {}  # short_path -> full_path

        # Find all __init__.py files in file_data
        init_files = [p for p in file_data if p.name == "__init__.py"]

        logger.debug(f"Building re-export map from {len(init_files)} __init__.py files")

        for init_file in init_files:
            try:
                tree, _, _ = file_data[init_file]

                # Extract the module path for this __init__.py
                # e.g., /path/to/panel/widgets/__init__.py -> panel.widgets
                search_dirs = list(self.python_env.site_packages)
                if self.python_env.user_site:
                    search_dirs.append(self.python_env.user_site)

                module_path = None
                for site_dir in search_dirs:
                    library_path = site_dir / library_name
                    if library_path.exists() and init_file.is_relative_to(library_path):
                        relative_path = init_file.relative_to(library_path)
                        parts = list(relative_path.parts[:-1])  # Exclude __init__.py
                        module_path = ".".join([library_name, *parts]) if parts else library_name
                        break

                if not module_path:
                    logger.debug(f"Could not determine module path for {init_file}")
                    continue

                # Parse import statements from already-parsed tree using optimized queries
                for node, _captures in find_imports(tree.root_node):
                    if node.type == "import_from_statement":
                        # Extract "from .module import Name1, Name2"
                        self._process_import_from_for_reexport(
                            node, module_path, library_name, reexport_map
                        )

            except Exception as e:
                logger.debug(f"Error processing {init_file} for re-exports: {e}")
                continue

        logger.debug(f"Built re-export map with {len(reexport_map)} entries")
        return reexport_map

    def _process_import_from_for_reexport(
        self,
        import_node: Node,
        current_module: str,
        library_name: str,
        reexport_map: dict[str, str],
    ) -> None:
        """Process a 'from ... import ...' statement to extract re-exports.

        Args:
            import_node: AST node of import_from statement
            current_module: Current module path (e.g., "panel.widgets")
            library_name: Root library name (e.g., "panel")
            reexport_map: Map to populate with re-export entries
        """
        # Extract source module and imported names using tree-sitter structure
        # Tree-sitter import_from_statement has:
        # - module_name field: the module being imported from
        # - name field or aliased_import nodes: the names being imported

        # Get the module name (e.g., ".input" in "from .input import TextInput")
        module_name_node = import_node.child_by_field_name("module_name")
        if not module_name_node:
            # Check for dotted_name or relative_import nodes
            for child in _treesitter.get_children(import_node):
                if child.type in ("dotted_name", "relative_import", "identifier"):
                    module_name_node = child
                    break

        if not module_name_node:
            return

        source_module = _treesitter.get_value(module_name_node)
        if not source_module:
            return

        # Get the imported names
        # Track if we've seen the 'import' keyword to distinguish module name from imported names
        seen_import_keyword = False
        imported_names = []
        for child in _treesitter.get_children(import_node):
            if child.type == "import":
                seen_import_keyword = True
                continue

            # After the 'import' keyword, these are imported names
            if seen_import_keyword:
                if child.type == "identifier":
                    # Single import: from .input import TextInput
                    name = _treesitter.get_value(child)
                    if name and name not in ("from", "import"):
                        imported_names.append(name)
                elif child.type == "dotted_name":
                    # Multi-line import names: from .parameterized import (Parameterized, ParameterizedFunction, ...)
                    name = _treesitter.get_value(child)
                    if name:
                        imported_names.append(name)
                elif child.type == "aliased_import":
                    # Import with alias: from .input import TextInput as TI
                    # Get the original name (before "as")
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        name = _treesitter.get_value(name_node)
                        if name:
                            imported_names.append(name)

        if not imported_names:
            return

        # Resolve relative imports like ".input" to "panel.widgets.input"
        full_source_module = self._resolve_relative_module_path(
            source_module, current_module, library_name
        )
        if not full_source_module:
            return

        # Build re-export entries for each imported name
        for name in imported_names:
            # Short path: panel.widgets.TextInput
            short_path = f"{current_module}.{name}"
            # Full path: panel.widgets.input.TextInput
            full_path = f"{full_source_module}.{name}"

            reexport_map[short_path] = full_path
            logger.debug(f"Re-export: {short_path} -> {full_path}")

    def _resolve_relative_module_path(
        self, relative_module: str, current_module: str, library_name: str
    ) -> str | None:
        """Resolve a relative module path to an absolute module path.

        Args:
            relative_module: Relative module like ".input" or "..base"
            current_module: Current module path like "panel.widgets"
            library_name: Root library name like "panel"

        Returns:
            Absolute module path like "panel.widgets.input" or None if cannot resolve
        """
        if not relative_module.startswith("."):
            # Already absolute
            return relative_module

        # Count leading dots
        level = 0
        for char in relative_module:
            if char == ".":
                level += 1
            else:
                break

        # Get the remaining module path after dots
        remaining = relative_module[level:]

        # Split current module into parts
        current_parts = current_module.split(".")

        # Go up 'level-1' directories (level=1 means same directory)
        if level > len(current_parts):
            logger.debug(
                f"Too many dots in relative import: {relative_module} from {current_module}"
            )
            return None

        # Navigate up the hierarchy
        base_parts = (
            current_parts[: len(current_parts) - (level - 1)] if level > 1 else current_parts
        )

        # Add the remaining module path
        result = ".".join([*base_parts, remaining]) if remaining else ".".join(base_parts)
        return result

    def populate_library_cache(self, library_name: str) -> int:
        """Pre-populate cache with all Parameterized classes from a library.

        Uses iterative inheritance resolution to find all classes that transitively
        inherit from param.Parameterized, including through intermediate base classes.

        Also populates dependencies first to ensure transitive inheritance through
        dependency classes is captured correctly.

        Args:
            library_name: Name of the library (e.g., "panel", "holoviews")

        Returns:
            Number of classes cached
        """
        if library_name not in ALLOWED_EXTERNAL_LIBRARIES:
            logger.debug(f"Library {library_name} not in allowed list")
            return 0

        # Check if we've already populated this library in this session
        if library_name in self.populated_libraries:
            logger.debug(f"Already populated {library_name} in this session")
            return 0

        # Mark as populated to avoid re-running
        self.populated_libraries.add(library_name)

        # Query library version from external environment
        version = self._get_library_version(library_name)
        if not version:
            return 0

        # Check if cache already has content for this library
        if external_library_cache.has_library_cache(library_name, version):
            logger.debug(f"Cache already exists for {library_name} version {version}")
            return 0

        # Populate dependencies first to ensure we can resolve inheritance
        # from classes in dependent libraries
        dependencies = self._get_library_dependencies(library_name)
        for dep in dependencies:
            if dep not in self.populated_libraries:
                logger.debug(f"Pre-populating dependency {dep} for {library_name}")
                self.populate_library_cache(dep)

        logger.debug(f"Pre-populating cache for {library_name} using iterative resolution")

        # Discover all source files for the library
        source_paths = self._discover_library_sources(library_name)
        if not source_paths:
            logger.debug(f"No source files found for {library_name}")
            return 0

        # Phase 0: Parse all files once and extract imports, classes, and re-exports in a single pass
        logger.debug("Phase 0: Parsing all source files and extracting classes")
        file_data: dict[
            Path, tuple[Any, dict[str, str], list[str]]
        ] = {}  # path -> (tree, imports, source_lines)
        inheritance_map: dict[str, list[str]] = {}  # full_class_path -> [base_class_paths]
        class_ast_nodes: dict[
            str, tuple[Node, dict[str, str], Path]
        ] = {}  # full_class_path -> (ast_node, imports, source_file)
        reexport_map: dict[str, str] = {}  # short_path -> full_path

        # Pre-compute site directories and library root path for module path resolution
        search_dirs = list(self.python_env.site_packages)
        if self.python_env.user_site:
            search_dirs.append(self.python_env.user_site)

        # Cache library root path to avoid repeated exists() and is_relative_to() checks
        library_root_path = None
        for site_dir in search_dirs:
            lib_path = site_dir / library_name
            if lib_path.exists():
                library_root_path = lib_path
                break

        if not library_root_path:
            logger.debug(f"Could not find library root path for {library_name}")
            return 0

        for source_path in source_paths:
            try:
                source_code = source_path.read_text(encoding="utf-8")
                tree = _treesitter.parser.parse(source_code)
                source_lines = source_code.split("\n")

                # Extract imports, classes, and re-exports using optimized queries
                file_imports: dict[str, str] = {}
                import_handler = ImportHandler(file_imports)

                # Check if this is an __init__.py for re-export processing
                is_init_file = source_path.name == "__init__.py"
                module_path = None
                if is_init_file and source_path.is_relative_to(library_root_path):
                    # Pre-compute module path for this __init__.py using cached library root
                    relative_path = source_path.relative_to(library_root_path)
                    parts = list(relative_path.parts[:-1])  # Exclude __init__.py
                    module_path = ".".join([library_name, *parts]) if parts else library_name

                # Extract imports using optimized query
                for import_node, _captures in find_imports(tree.root_node):
                    if import_node.type == "import_statement":
                        import_handler.handle_import(import_node)
                    elif import_node.type == "import_from_statement":
                        import_handler.handle_import_from(import_node)
                        # Also process re-exports if this is an __init__.py
                        if is_init_file and module_path:
                            self._process_import_from_for_reexport(
                                import_node, module_path, library_name, reexport_map
                            )

                # First pass: collect all class names in this file
                file_classes: set[str] = set()
                class_data: list[tuple[Node, str, str]] = []  # (node, class_name, full_path)
                for class_node, _captures in find_classes(tree.root_node):
                    class_name = _treesitter.get_class_name(class_node)
                    if class_name:
                        file_classes.add(class_name)
                        # Construct full class path using cached library root
                        full_class_path = self._get_full_class_path_cached(
                            source_path, class_name, library_name, library_root_path
                        )
                        if full_class_path:
                            class_data.append((class_node, class_name, full_class_path))

                # Second pass: resolve base classes with knowledge of local classes
                for class_node, _class_name, full_class_path in class_data:
                    # Get base classes as full paths
                    bases = self._resolve_base_class_paths(
                        class_node, file_imports, library_name, source_path, file_classes
                    )
                    # Store in inheritance map
                    inheritance_map[full_class_path] = bases
                    class_ast_nodes[full_class_path] = (
                        class_node,
                        file_imports,
                        source_path,
                    )

                # Store parsed data
                file_data[source_path] = (tree, file_imports, source_lines)
                # Cache source lines for later parameter extraction
                self.file_source_cache[source_path] = source_lines

            except Exception as e:
                logger.debug(f"Error parsing {source_path}: {e}")
                continue

        logger.debug(
            f"Parsed {len(file_data)} source files, found {len(inheritance_map)} classes, {len(reexport_map)} re-exports"
        )

        # Phase 1: Iterative Parameterized detection
        logger.debug("Phase 1: Iterative Parameterized detection")
        parameterized_classes: set[str] = set()

        # Round 0: Add known Parameterized root classes (classes that ARE Parameterized itself)
        # These are classes named "Parameterized" with no base classes or only metaclass/object as base
        for class_path in inheritance_map:
            # Check if this is the Parameterized class itself
            if self._is_parameterized_base(class_path, library_name):
                parameterized_classes.add(class_path)

        logger.debug(f"Round 0: Found {len(parameterized_classes)} Parameterized root classes")

        # Round 1: Find direct Parameterized subclasses
        for class_path, bases in inheritance_map.items():
            if any(self._is_parameterized_base(base, library_name) for base in bases):
                parameterized_classes.add(class_path)

        logger.debug(
            f"Round 1: Found {len(parameterized_classes)} direct Parameterized subclasses"
        )

        # Round 2+: Propagate iteratively
        round_num = 2
        changed = True
        while changed:
            changed = False
            for class_path, bases in inheritance_map.items():
                if class_path not in parameterized_classes:
                    # Check if any base class is already marked as Parameterized
                    for base in bases:
                        if self._base_matches_parameterized_class(base, parameterized_classes):
                            parameterized_classes.add(class_path)
                            changed = True
                            break

            if changed:
                logger.debug(
                    f"Round {round_num}: Total {len(parameterized_classes)} Parameterized classes"
                )
                round_num += 1

        logger.debug(f"Final: Found {len(parameterized_classes)} total Parameterized classes")

        # Phase 2: Extract parameters for Parameterized classes
        logger.debug("Phase 2: Extracting parameters")
        count = 0
        for class_path in parameterized_classes:
            try:
                class_node, file_imports, source_path = class_ast_nodes[class_path]
                class_info = self._convert_ast_to_class_info(
                    class_node,
                    file_imports,
                    class_path,
                    source_path,
                    inheritance_map,
                    class_ast_nodes,
                )
                if class_info:
                    # Cache under the full path
                    external_library_cache.set(library_name, class_path, class_info, version)
                    count += 1

                    # Register any re-export aliases for this class
                    for short_path, full_path in reexport_map.items():
                        if full_path == class_path:
                            try:
                                external_library_cache.set_alias(
                                    library_name, short_path, full_path, version
                                )
                                logger.debug(
                                    f"Registered re-export alias: {short_path} -> {full_path}"
                                )
                            except Exception as e:
                                logger.debug(
                                    f"Failed to register re-export alias {short_path}: {e}"
                                )
            except Exception as e:
                logger.debug(f"Failed to cache {class_path}: {e}")

        logger.info(f"Populated {count} classes for {library_name}")
        # Flush all pending cache changes to disk
        external_library_cache.flush(library_name, version)
        # Clean up AST caches after population
        self._cleanup_ast_caches()
        return count

    def analyze_external_class(self, full_class_path: str) -> ParameterizedInfo | None:
        """Analyze an external class using static analysis.

        Args:
            full_class_path: Full path like "panel.widgets.IntSlider"

        Returns:
            ParameterizedInfo if successful, None otherwise
        """
        # Quick check for core param types that are not Parameterized classes
        if full_class_path.startswith("param."):
            # These are parameter types, not Parameterized classes - cache and return None
            self.parsed_classes[full_class_path] = None
            return None

        if full_class_path in self.parsed_classes:
            return self.parsed_classes[full_class_path]

        # Check if this library is allowed
        root_module = full_class_path.split(".")[0]
        if root_module not in ALLOWED_EXTERNAL_LIBRARIES:
            logger.debug(f"Library {root_module} not in allowed list")
            self.parsed_classes[full_class_path] = None
            return None

        # Try to populate cache if not already done
        self.populate_library_cache(root_module)

        # Query library version from external environment
        version = self._get_library_version(root_module)
        if not version:
            logger.debug(f"Could not determine version for {root_module}")
            self.parsed_classes[full_class_path] = None
            return None

        try:
            # Try to get from cache (which may contain pre-populated data including re-export aliases)
            class_info = external_library_cache.get(root_module, full_class_path, version)
            if class_info:
                logger.debug(f"Found cached metadata for {full_class_path}")
                self.parsed_classes[full_class_path] = class_info
                return class_info

            # Fallback to dynamic AST analysis if not in cache
            logger.debug(f"No cached metadata found for {full_class_path}, trying AST analysis")
            class_info = self._analyze_class_from_source(full_class_path)
            self.parsed_classes[full_class_path] = class_info

            # Store successful analysis in global cache for persistence
            if class_info:
                try:
                    external_library_cache.set(root_module, full_class_path, class_info, version)
                    external_library_cache.flush(root_module, version)
                    logger.debug(f"Stored {full_class_path} in cache")
                except Exception as e:
                    logger.debug(f"Failed to store {full_class_path} in cache: {e}")

            return class_info
        except Exception as e:
            logger.debug(f"Failed to analyze {full_class_path}: {e}")
            self.parsed_classes[full_class_path] = None
            return None

    def _analyze_class_from_source(self, full_class_path: str) -> ParameterizedInfo | None:
        """Analyze a class by finding and parsing its source file.

        Args:
            full_class_path: Full class path like "panel.widgets.IntSlider"

        Returns:
            ParameterizedInfo if found and analyzed successfully
        """
        # Parse the class path
        parts = full_class_path.split(".")
        root_module = parts[0]
        class_name = parts[-1]

        # Find source files for this library
        source_paths = self._discover_library_sources(root_module)
        if not source_paths:
            logger.debug(f"No source files found for {root_module}")
            return None

        # Search for the class in source files using queue-based analysis
        for source_path in source_paths:
            try:
                # Queue the initial file for analysis
                self._queue_file_for_analysis(source_path, f"searching for {class_name}")

                # Process the analysis queue
                self._process_analysis_queue()

                # Check if we found the class
                class_info = self._find_class_definition(class_name)
                if class_info:
                    class_definition, class_imports = class_info
                    # Verify this is actually a Parameterized class
                    if self._inherits_from_parameterized(class_definition, class_imports):
                        # Convert AST node to ParameterizedInfo
                        result = self._convert_ast_to_class_info(
                            class_definition, class_imports, full_class_path, source_path
                        )
                        # Clean up AST caches after successful conversion
                        self._cleanup_ast_caches()
                        return result

            except Exception as e:
                logger.debug(f"Error analyzing {source_path}: {e}")
                continue

        logger.debug(f"Class {full_class_path} not found in source files")
        # Clean up AST caches when class not found
        self._cleanup_ast_caches()
        return None

    def _get_full_class_path_cached(
        self, source_path: Path, class_name: str, library_name: str, library_root_path: Path
    ) -> str | None:
        """Construct full class path from source file path and class name using cached library root.

        Args:
            source_path: Path to the source file
            class_name: Name of the class
            library_name: Root library name (e.g., "panel")
            library_root_path: Pre-resolved library root path

        Returns:
            Full class path like "panel.widgets.IntSlider" or None if unable to construct
        """
        try:
            if source_path.is_relative_to(library_root_path):
                # Get relative path from library root
                relative_path = source_path.relative_to(library_root_path)
                # Convert path to module notation
                parts = list(relative_path.parts[:-1])  # Exclude filename
                if relative_path.stem != "__init__":
                    parts.append(relative_path.stem)
                # Construct full path: library.module.submodule.ClassName
                module_path = ".".join([library_name, *parts])
                return f"{module_path}.{class_name}"

            return None
        except Exception as e:
            logger.debug(
                f"Failed to construct full class path for {class_name} in {source_path}: {e}"
            )
            return None

    def _get_full_class_path(
        self, source_path: Path, class_name: str, library_name: str
    ) -> str | None:
        """Construct full class path from source file path and class name.

        Args:
            source_path: Path to the source file
            class_name: Name of the class
            library_name: Root library name (e.g., "panel")

        Returns:
            Full class path like "panel.widgets.IntSlider" or None if unable to construct
        """
        try:
            # Find the library root directory in Python environment's site-packages
            search_dirs = list(self.python_env.site_packages)
            if self.python_env.user_site:
                search_dirs.append(self.python_env.user_site)

            for site_dir in search_dirs:
                library_path = site_dir / library_name
                if library_path.exists() and source_path.is_relative_to(library_path):
                    # Get relative path from library root
                    relative_path = source_path.relative_to(library_path)
                    # Convert path to module notation
                    parts = list(relative_path.parts[:-1])  # Exclude filename
                    if relative_path.stem != "__init__":
                        parts.append(relative_path.stem)
                    # Construct full path: library.module.submodule.ClassName
                    module_path = ".".join([library_name, *parts])
                    return f"{module_path}.{class_name}"

            return None
        except Exception as e:
            logger.debug(
                f"Failed to construct full class path for {class_name} in {source_path}: {e}"
            )
            return None

    def _discover_library_sources(self, library_name: str) -> list[Path]:
        """Discover source files for a given library.

        Args:
            library_name: Name of the library (e.g., "panel")

        Returns:
            List of Python source file paths
        """
        if library_name in self.library_source_paths:
            return self.library_source_paths[library_name]

        source_paths = []

        logger.debug(f"Searching for {library_name} in environment: {self.python_env.python}")
        logger.debug(f"Site-packages: {self.python_env.site_packages}")
        logger.debug(f"User site: {self.python_env.user_site}")

        # Search in Python environment's site-packages directories
        for site_dir in self.python_env.site_packages:
            library_path = site_dir / library_name
            logger.debug(f"Checking: {library_path} (exists={library_path.exists()})")
            if library_path.exists():
                files = self._collect_python_files(library_path)
                logger.debug(f"Found {len(files)} Python files in {library_path}")
                source_paths.extend(files)

        # Search in user site-packages if available
        if self.python_env.user_site:
            library_path = self.python_env.user_site / library_name
            logger.debug(f"Checking user site: {library_path} (exists={library_path.exists()})")
            if library_path.exists():
                files = self._collect_python_files(library_path)
                logger.debug(f"Found {len(files)} Python files in user site {library_path}")
                source_paths.extend(files)

        # Remove duplicates while preserving order, and cache
        seen = set()
        unique_paths = []
        for path in source_paths:
            if path not in seen:
                seen.add(path)
                unique_paths.append(path)
        self.library_source_paths[library_name] = unique_paths

        logger.info(
            f"Total: Found {len(unique_paths)} source files for {library_name!r} in {str(self.python_env.python)!r}"
        )
        return unique_paths

    def _collect_python_files(self, directory: Path) -> list[Path]:
        """Recursively collect Python files from a directory.

        Args:
            directory: Directory to search

        Returns:
            List of Python file paths
        """
        python_files = []
        try:
            if directory.is_file() and directory.suffix == ".py":
                python_files.append(directory)
            elif directory.is_dir():
                python_files.extend(
                    path
                    for path in directory.rglob("*.py")
                    if path.is_file() and not any(part in ("test", "tests") for part in path.parts)
                )
        except (OSError, PermissionError) as e:
            logger.debug(f"Error accessing {directory}: {e}")

        return python_files

    def _analyze_file_ast(
        self, tree: Node, source_code: str
    ) -> dict[str, ParameterizedInfo | None]:
        """Analyze a parsed AST to find Parameterized classes.

        Args:
            tree: Parsed AST tree
            source_code: Original source code

        Returns:
            Dictionary mapping class names to ParameterizedInfo
        """
        imports: dict[str, str] = {}
        classes: dict[str, ParameterizedInfo | None] = {}

        # Parse imports first
        import_handler = ImportHandler(imports)
        self._walk_ast_for_imports(tree, import_handler)

        # Cache all class AST nodes for inheritance resolution
        self._cache_all_class_nodes(tree, imports)

        # Find and analyze classes
        self._walk_ast_for_classes(tree, imports, classes, source_code.split("\n"))

        return classes

    def _cache_all_class_nodes(self, node: Node, imports: dict[str, str]) -> None:
        """Cache all class AST nodes for later inheritance resolution.

        Args:
            node: AST node to search
            imports: Import mappings for this file
        """
        if hasattr(node, "type") and node.type == "class_definition":
            class_name = self._get_class_name(node)
            if class_name:
                # Store the class node and its imports context
                self.class_ast_cache[class_name] = (node, imports.copy())

        # Recursively cache children
        for child in _treesitter.get_children(node):
            self._cache_all_class_nodes(child, imports)

    def _walk_ast_for_imports(self, node: Node, import_handler: ImportHandler) -> None:
        """Walk AST to find and parse import statements.

        Args:
            node: Current AST node
            import_handler: Handler for processing imports
        """
        if hasattr(node, "type"):
            if node.type == "import_statement":
                import_handler.handle_import(node)
            elif node.type == "import_from_statement":
                import_handler.handle_import_from(node)

        # Recursively walk children
        for child in _treesitter.get_children(node):
            self._walk_ast_for_imports(child, import_handler)

    def _walk_ast_for_classes(
        self,
        node: Node,
        imports: dict[str, str],
        classes: dict[str, ParameterizedInfo | None],
        source_lines: list[str],
    ) -> None:
        """Walk AST to find and analyze class definitions.

        Args:
            node: Current AST node
            imports: Import mappings
            classes: Dictionary to store found classes
            source_lines: Source code lines for parameter extraction
        """
        if hasattr(node, "type") and node.type == "class_definition":
            class_info = self._analyze_class_definition(node, imports, source_lines)
            if class_info:
                classes[class_info.name] = class_info

        # Recursively walk children
        for child in _treesitter.get_children(node):
            self._walk_ast_for_classes(child, imports, classes, source_lines)

    def _analyze_class_definition(
        self, class_node: Node, imports: dict[str, str], source_lines: list[str]
    ) -> ParameterizedInfo | None:
        """Analyze a class definition to extract parameter information.

        Args:
            class_node: AST node representing class definition
            imports: Import mappings
            source_lines: Source code lines

        Returns:
            ParameterizedInfo if class is Parameterized, None otherwise
        """
        # Get class name
        class_name = self._get_class_name(class_node)
        if not class_name:
            return None

        # Check if class inherits from param.Parameterized
        if not self._inherits_from_parameterized(class_node, imports):
            return None

        # Create class info
        class_info = ParameterizedInfo(name=class_name)

        # Find parameter assignments in class body
        parameter_detector = ParameterDetector(imports)
        self._extract_class_parameters(
            class_node, parameter_detector, class_info, source_lines, imports
        )

        return class_info if class_info.parameters else None

    def _get_class_name(self, class_node: Node) -> str | None:
        """Extract class name from class definition node.

        Args:
            class_node: Class definition AST node

        Returns:
            Class name or None if not found
        """
        # Use ts_utils helper function
        return _treesitter.get_class_name(class_node)

    def _inherits_from_parameterized(self, class_node: Node, imports: dict[str, str]) -> bool:
        """Check if a class inherits from param.Parameterized.

        Args:
            class_node: Class definition AST node
            imports: Import mappings

        Returns:
            True if class inherits from param.Parameterized
        """
        # First check direct inheritance
        base_classes = self._get_base_classes(class_node)

        for base_class in base_classes:
            if self._is_parameterized_base_class_name(base_class, imports):
                return True

            # For indirect inheritance, we need to resolve the base class
            # This would require deeper analysis across files, which is complex
            # For now, check some common patterns that we know inherit from Parameterized
            if self._is_known_parameterized_pattern(base_class, imports):
                return True

        return False

    def _get_base_classes(self, class_node: Node) -> list[str]:
        """Extract base class names from class definition.

        Args:
            class_node: Class definition AST node

        Returns:
            List of base class names
        """
        # Use ts_utils helper to get base nodes
        base_nodes = _treesitter.get_class_bases(class_node)
        base_classes = []

        for base_node in base_nodes:
            base_class_name = self._resolve_base_class_name(base_node)
            if base_class_name:
                base_classes.append(base_class_name)

        return base_classes

    def _is_known_parameterized_pattern(self, base_class: str, imports: dict[str, str]) -> bool:
        """Check if a base class is a known pattern that inherits from Parameterized.

        This checks if the base class is already cached from the current file analysis,
        and if so, recursively checks its inheritance.

        Args:
            base_class: Base class name to check
            imports: Import mappings

        Returns:
            True if base class is known to inherit from Parameterized
        """
        # Avoid infinite recursion
        if not hasattr(self, "_inheritance_check_visited"):
            self._inheritance_check_visited = set()

        if base_class in self._inheritance_check_visited:
            return False

        self._inheritance_check_visited.add(base_class)

        try:
            # First check if this base class is already in our AST cache
            # (meaning it was found in the same file we're currently analyzing)
            class_info = self._find_class_definition(base_class)
            if class_info:
                class_definition, class_imports = class_info
                result = self._inherits_from_parameterized(class_definition, class_imports)
                return result

            # If not found in current file, try to resolve through imports
            if base_class in imports:
                import_path = imports[base_class]
                result = self._resolve_imported_class_inheritance(base_class, import_path, imports)
                return result

            return False
        finally:
            self._inheritance_check_visited.discard(base_class)

    def _find_class_definition(self, class_name: str) -> tuple[Node, dict[str, str]] | None:
        """Find the AST node for a class definition.

        Args:
            class_name: Name of the class to find

        Returns:
            Tuple of (AST node, imports) of the class definition if found, None otherwise
        """
        # Check the AST cache first
        if class_name in self.class_ast_cache:
            return self.class_ast_cache[class_name]

        return None

    def _resolve_import_to_file_path(
        self, import_path: str, current_file_path: Path
    ) -> Path | None:
        """Resolve an import path to an actual file path.

        Args:
            import_path: Import path like "base.Widget" or "panel.widgets.base.Widget"
            current_file_path: Path of the file containing the import

        Returns:
            Absolute file path if found, None otherwise
        """
        if "." not in import_path:
            return None

        # Split import path into module and class
        parts = import_path.split(".")
        if len(parts) < 2:
            return None

        # The last part is the class name, everything else is the module path
        module_parts = parts[:-1]

        # For imports like "base.Widget", treat "base" as a relative import
        # since it's likely from the same directory
        if len(module_parts) == 1 and not module_parts[0].startswith(
            tuple(ALLOWED_EXTERNAL_LIBRARIES)
        ):
            return self._resolve_relative_import(module_parts, current_file_path)

        # Handle absolute imports within the same library
        return self._resolve_absolute_import(module_parts, current_file_path)

    def _resolve_relative_import(
        self, module_parts: list[str], current_file_path: Path
    ) -> Path | None:
        """Resolve a relative import like ['base'] from current file location.

        Args:
            module_parts: Module parts like ['base'] or ['..', 'core']
            current_file_path: Current file path

        Returns:
            Resolved file path or None
        """
        # Start from the directory containing the current file
        base_dir = current_file_path.parent

        # Handle relative import levels
        for part in module_parts:
            if part == "..":
                base_dir = base_dir.parent
            elif part == ".":
                continue  # Stay in current directory
            else:
                # This is the actual module name
                potential_file = base_dir / f"{part}.py"
                if potential_file.exists():
                    return potential_file

                # Try as a package
                potential_package = base_dir / part / "__init__.py"
                if potential_package.exists():
                    return potential_package

        return None

    def _resolve_absolute_import(
        self, module_parts: list[str], current_file_path: Path
    ) -> Path | None:
        """Resolve an absolute import within the same library.

        Args:
            module_parts: Module parts like ['panel', 'widgets', 'base']
            current_file_path: Current file path for context

        Returns:
            Resolved file path or None
        """
        # Find the library root by examining the current file path
        library_root = self._find_library_root(current_file_path)
        if not library_root:
            return None

        # Build path from library root
        potential_path = library_root
        for part in module_parts[1:]:  # Skip the first part (library name)
            potential_path = potential_path / part

        # Try as a module file
        module_file = potential_path.with_suffix(".py")
        if module_file.exists():
            return module_file

        # Try as a package
        package_file = potential_path / "__init__.py"
        if package_file.exists():
            return package_file

        return None

    def _find_library_root(self, file_path: Path) -> Path | None:
        """Find the root directory of the library containing the given file.

        Args:
            file_path: Path to a file within the library

        Returns:
            Library root directory or None
        """
        # Walk up the directory tree looking for a known library name
        current_dir = file_path.parent
        while current_dir != current_dir.parent:  # Not at filesystem root
            if current_dir.name in ALLOWED_EXTERNAL_LIBRARIES:
                return current_dir
            current_dir = current_dir.parent

        return None

    def _queue_file_for_analysis(self, file_path: Path, reason: str) -> None:
        """Add a file to the analysis queue if not already analyzed.

        Args:
            file_path: Path to the file to analyze
            reason: Reason for analysis (for debugging)
        """
        if file_path not in self.analyzed_files and file_path not in self.currently_analyzing:
            self.analysis_queue.append((file_path, reason))
            logger.debug(f"Queued {file_path} for analysis: {reason}")

    def _process_analysis_queue(self) -> None:
        """Process all files in the analysis queue."""
        while self.analysis_queue:
            file_path, reason = self.analysis_queue.pop(0)

            # Skip if already analyzing (circular dependency protection)
            if file_path in self.currently_analyzing:
                continue

            # Skip if already analyzed
            if file_path in self.analyzed_files:
                continue

            try:
                self.currently_analyzing.add(file_path)
                logger.debug(f"Analyzing {file_path}: {reason}")

                # Read and parse the file
                source_code = file_path.read_text(encoding="utf-8")
                source_lines = source_code.split("\n")
                tree = _treesitter.parser.parse(source_code)

                # Store source lines for parameter extraction
                self.file_source_cache[file_path] = source_lines

                # Analyze the file (this may queue additional files)
                file_analysis = self._analyze_file_ast(tree.root_node, source_code)
                self.analyzed_files[file_path] = file_analysis

                logger.debug(
                    f"Completed analysis of {file_path}, found {len(file_analysis)} classes"
                )

            except Exception as e:
                logger.debug(f"Failed to analyze {file_path}: {e}")
                # Mark as analyzed even if failed to prevent retry loops
                self.analyzed_files[file_path] = {}
            finally:
                self.currently_analyzing.discard(file_path)

    def _cleanup_ast_caches(self) -> None:
        """Clean up AST caches to reduce memory usage and garbage collection delay.

        This method clears the internal caches that hold AST nodes and source code
        after analysis is complete, which helps reduce memory usage and speeds up
        process cleanup by reducing the amount of data that needs to be garbage collected.
        """
        logger.debug(
            f"Cleaning up AST caches: {len(self.class_ast_cache)} AST nodes, "
            f"{len(self.file_source_cache)} source files, "
            f"{len(self.analyzed_files)} analyzed files"
        )

        # Clear the AST cache that holds parsed AST nodes
        self.class_ast_cache.clear()

        # Clear the source file cache
        self.file_source_cache.clear()

        # Clear analyzed files cache
        self.analyzed_files.clear()

        logger.debug("AST cache cleanup completed")

    def _convert_ast_to_class_info(
        self,
        class_node: Node,
        imports: dict[str, str],
        full_class_path: str,
        file_path: Path,
        inheritance_map: dict[str, list[str]] | None = None,
        class_ast_nodes: dict[str, tuple[Node, dict[str, str], Path]] | None = None,
    ) -> ParameterizedInfo:
        """Convert an AST class node to ParameterizedInfo.

        Args:
            class_node: AST node of the class
            imports: Import mappings
            full_class_path: Full path like "panel.widgets.IntSlider"
            file_path: Path to the source file
            inheritance_map: Optional map of full_class_path -> [base_class_paths]
            class_ast_nodes: Optional map of full_class_path -> (ast_node, imports, file_path)

        Returns:
            ParameterizedInfo with extracted parameters
        """
        class_name = self._get_class_name(class_node)
        if not class_name:
            msg = "Could not extract class name from AST node"
            raise ValueError(msg)

        # Create class info
        class_info = ParameterizedInfo(name=class_name)

        # Find parameter assignments in class body
        from param_lsp._analyzer.ast_navigator import ParameterDetector

        parameter_detector = ParameterDetector(imports)

        # Get the actual source lines for parameter extraction
        source_lines = self.file_source_cache.get(file_path)
        if source_lines is None:
            # If not in cache, read the file directly
            try:
                source_code = file_path.read_text(encoding="utf-8")
                source_lines = source_code.split("\n")
                # Cache it for future use
                self.file_source_cache[file_path] = source_lines
            except Exception as e:
                logger.error(f"Failed to read source file {file_path}: {e}")
                source_lines = [""]  # Minimal fallback, not 1000 empty lines

        self._extract_class_parameters(
            class_node, parameter_detector, class_info, source_lines, imports
        )

        # Extract parameters from parent classes using inheritance_map
        if inheritance_map and class_ast_nodes:
            self._extract_inherited_parameters_from_map(
                full_class_path,
                parameter_detector,
                class_info,
                inheritance_map,
                class_ast_nodes,
            )
        else:
            # Fallback to old method for same-file inheritance
            self._extract_inherited_parameters(
                class_node, parameter_detector, class_info, source_lines, imports
            )

        return class_info

    def _extract_inherited_parameters(
        self,
        class_node: Node,
        parameter_detector: ParameterDetector,
        class_info: ParameterizedInfo,
        source_lines: list[str],
        imports: dict[str, str],
    ) -> None:
        """Extract parameters from parent classes within the same file.

        Args:
            class_node: Class definition AST node
            parameter_detector: Detector for parameter assignments
            class_info: Class info to populate with inherited parameters
            source_lines: Source code lines
            imports: Import mappings
        """
        # Get direct parent classes
        base_classes = self._get_base_classes(class_node)

        for base_class in base_classes:
            # Look for parent class definition in the same file (class_ast_cache)
            parent_info = self._find_class_definition(base_class)
            if parent_info:
                parent_node, parent_imports = parent_info

                # Extract parameters from parent class
                parent_class_info = ParameterizedInfo(name=base_class)
                self._extract_class_parameters(
                    parent_node,
                    parameter_detector,
                    parent_class_info,
                    source_lines,
                    parent_imports,
                )

                # Add parent parameters to child (child parameters take precedence)
                for param_name, param_info in parent_class_info.parameters.items():
                    if param_name not in class_info.parameters:
                        class_info.parameters[param_name] = param_info

                # Recursively check parent's parents
                self._extract_inherited_parameters(
                    parent_node, parameter_detector, class_info, source_lines, parent_imports
                )

    def _extract_inherited_parameters_from_map(
        self,
        full_class_path: str,
        parameter_detector: ParameterDetector,
        class_info: ParameterizedInfo,
        inheritance_map: dict[str, list[str]],
        class_ast_nodes: dict[str, tuple[Node, dict[str, str], Path]],
    ) -> None:
        """Extract parameters from parent classes using the inheritance map.

        This method uses the pre-built inheritance map to recursively gather
        parameters from all parent classes, resolving cross-file inheritance.

        Args:
            full_class_path: Full path of the current class
            parameter_detector: Detector for parameter assignments
            class_info: Class info to populate with inherited parameters
            inheritance_map: Map of full_class_path -> [base_class_paths]
            class_ast_nodes: Map of full_class_path -> (ast_node, imports, file_path)
        """
        # Avoid infinite recursion with a visited set
        if not hasattr(self, "_inheritance_extraction_visited"):
            self._inheritance_extraction_visited = set()

        if full_class_path in self._inheritance_extraction_visited:
            return

        self._inheritance_extraction_visited.add(full_class_path)

        try:
            # Get base classes for this class
            base_classes = inheritance_map.get(full_class_path, [])

            for base_class_path in base_classes:
                # Skip param.Parameterized itself
                # Extract library name from full_class_path for context-aware checking
                library_name = full_class_path.split(".")[0]
                if self._is_parameterized_base(base_class_path, library_name):
                    continue

                # Try to find the base class in our AST nodes
                if base_class_path in class_ast_nodes:
                    parent_node, parent_imports, parent_file_path = class_ast_nodes[
                        base_class_path
                    ]

                    # Get source lines for the parent class
                    parent_source_lines = self.file_source_cache.get(parent_file_path)
                    if parent_source_lines is None:
                        try:
                            source_code = parent_file_path.read_text(encoding="utf-8")
                            parent_source_lines = source_code.split("\n")
                            self.file_source_cache[parent_file_path] = parent_source_lines
                        except Exception as e:
                            logger.debug(f"Failed to read source file {parent_file_path}: {e}")
                            continue

                    # Extract parameters from parent class
                    parent_class_info = ParameterizedInfo(name=base_class_path.split(".")[-1])
                    self._extract_class_parameters(
                        parent_node,
                        parameter_detector,
                        parent_class_info,
                        parent_source_lines,
                        parent_imports,
                    )

                    # Add parent parameters to child (child parameters take precedence)
                    for param_name, param_info in parent_class_info.parameters.items():
                        if param_name not in class_info.parameters:
                            class_info.parameters[param_name] = param_info

                    # Recursively extract from parent's parents
                    self._extract_inherited_parameters_from_map(
                        base_class_path,
                        parameter_detector,
                        class_info,
                        inheritance_map,
                        class_ast_nodes,
                    )
                else:
                    # Base class not found in our AST nodes
                    # This might be from an external library or stdlib
                    logger.debug(f"Base class {base_class_path} not found in AST nodes")

        finally:
            self._inheritance_extraction_visited.discard(full_class_path)

    def _resolve_imported_class_inheritance(
        self, class_name: str, import_path: str, context_imports: dict[str, str]
    ) -> bool:
        """Resolve inheritance for an imported class by analyzing its source file.

        Args:
            class_name: Name of the imported class
            import_path: Import path like "base.Widget"
            context_imports: Import context from current file

        Returns:
            True if the imported class inherits from Parameterized
        """
        # First check if it's clearly not a Parameterized class
        if import_path.startswith(_STDLIB_MODULES):
            return False

        # Check if the import is from an external library that's not in our allowed list
        # This prevents errors when trying to resolve bokeh, tornado, etc. base classes
        root_module = import_path.split(".")[0]
        if root_module not in ALLOWED_EXTERNAL_LIBRARIES and root_module != class_name:
            return False

        # Get the current file context (we need this for import resolution)
        current_file = self._get_current_file_from_context()
        if not current_file:
            logger.debug(f"Could not determine current file context for {class_name}")
            return False

        # Resolve the import to a file path
        target_file = self._resolve_import_to_file_path(import_path, current_file)
        if not target_file:
            logger.debug(f"Could not resolve import {import_path} to file path")
            return False

        # Queue the target file for analysis
        self._queue_file_for_analysis(target_file, f"resolving inheritance for {class_name}")

        # Process the queue to analyze the file
        self._process_analysis_queue()

        # Now check if we can find the class and its inheritance
        parsed_class_name = import_path.split(".")[-1]  # Extract actual class name
        class_info = self._find_class_definition(parsed_class_name)
        if class_info:
            class_definition, class_imports = class_info
            result = self._inherits_from_parameterized(class_definition, class_imports)
            return result

        # Could not resolve - this is expected for complex inheritance chains
        return False

    def _get_current_file_from_context(self) -> Path | None:
        """Get the current file being analyzed from context.

        This is a helper method to determine which file we're currently analyzing
        for import resolution purposes.

        Returns:
            Path to current file or None if not determinable
        """
        # Look for the most recently added file to the analysis queue or currently analyzing
        if self.currently_analyzing:
            return next(iter(self.currently_analyzing))

        # If nothing is currently being analyzed, we might be in the initial phase
        # In this case, we'll need to track this differently
        # For now, return None and rely on heuristics
        return None

    def _search_for_class_in_ast(self, node: Node, target_class_name: str) -> Node | None:
        """Recursively search for a class definition in an AST.

        Args:
            node: Current AST node to search
            target_class_name: Name of the class to find

        Returns:
            AST node of the class definition if found, None otherwise
        """
        if hasattr(node, "type") and node.type == "class_definition":
            class_name = self._get_class_name(node)
            if class_name == target_class_name:
                return node

        # Recursively search children
        for child in _treesitter.get_children(node):
            result = self._search_for_class_in_ast(child, target_class_name)
            if result:
                return result

        return None

    def _is_parameterized_base_class_name(
        self, base_class_name: str, imports: dict[str, str]
    ) -> bool:
        """Check if a base class name represents param.Parameterized.

        Args:
            base_class_name: Name of the base class
            imports: Import mappings

        Returns:
            True if base class is param.Parameterized
        """
        # Check direct reference
        if base_class_name == "param.Parameterized":
            return True

        # Check imports
        if base_class_name in imports:
            full_name = imports[base_class_name]
            if full_name == "param.Parameterized":
                return True

        return False

    def _resolve_base_class_name(self, node: Node) -> str | None:
        """Resolve base class name from AST node.

        Args:
            node: AST node representing base class reference

        Returns:
            Resolved base class name
        """
        if node.type == "identifier":
            return _treesitter.get_value(node)
        elif node.type == "attribute":
            # Handle dotted names like param.Parameterized
            return _treesitter.get_value(node)
        return None

    def _extract_class_parameters(
        self,
        class_node: Node,
        parameter_detector: ParameterDetector,
        class_info: ParameterizedInfo,
        source_lines: list[str],
        imports: dict[str, str],
    ) -> None:
        """Extract parameter assignments from class body.

        Args:
            class_node: Class definition AST node
            parameter_detector: Detector for parameter assignments
            class_info: Class info to populate with parameters
            source_lines: Source code lines for extracting definitions
        """
        # Find class block (body) - tree-sitter uses "block" instead of "suite"
        block_node = class_node.child_by_field_name("body")

        if not block_node:
            return

        # Walk through statements in class body
        self._walk_class_body(block_node, parameter_detector, class_info, source_lines, imports)

    def _walk_class_body(
        self,
        block_node: Node,
        parameter_detector: ParameterDetector,
        class_info: ParameterizedInfo,
        source_lines: list[str],
        imports: dict[str, str],
    ) -> None:
        """Walk through class body to find parameter assignments.

        Args:
            block_node: Block AST node containing class body
            parameter_detector: Detector for parameter assignments
            class_info: Class info to populate
            source_lines: Source code lines
            imports: Import mappings
        """
        for child in _treesitter.get_children(block_node):
            # In tree-sitter, assignments can be:
            # - "expression_statement" containing an "assignment"
            # - Direct "assignment" nodes
            if child.type == "expression_statement":
                # Check for assignment statements inside expression_statement
                for stmt_child in _treesitter.get_children(child):
                    if (
                        stmt_child.type == "assignment"
                        and parameter_detector.is_parameter_assignment(stmt_child)
                    ):
                        param_info = self._extract_parameter_info(
                            stmt_child, source_lines, imports
                        )
                        if param_info:
                            class_info.add_parameter(param_info)
            elif child.type == "assignment" and parameter_detector.is_parameter_assignment(child):
                # Direct assignment node
                param_info = self._extract_parameter_info(child, source_lines, imports)
                if param_info:
                    class_info.add_parameter(param_info)
            elif hasattr(child, "type") and child.type not in (
                "function_definition",
                "async_function_definition",
                "class_definition",
            ):
                # Recursively search in nested structures, but skip function/method definitions
                # and nested class definitions to avoid treating method-local variables as parameters
                self._walk_class_body(child, parameter_detector, class_info, source_lines, imports)

    def _extract_parameter_info(
        self, assignment_node: Node, source_lines: list[str], imports: dict[str, str]
    ) -> ParameterInfo | None:
        """Extract parameter information from an assignment statement.

        Args:
            assignment_node: Assignment AST node
            source_lines: Source code lines

        Returns:
            ParameterInfo if extraction successful
        """
        # Get parameter name (left side of assignment)
        param_name = self._get_parameter_name(assignment_node)
        if not param_name:
            return None

        # Use existing parameter extractor with source content
        source_content = "\n".join(source_lines)

        # Use the imports from the file analysis

        return extract_parameter_info_from_assignment(
            assignment_node, param_name, imports, source_content
        )

    def _get_parameter_name(self, assignment_node: Node) -> str | None:
        """Extract parameter name from assignment node.

        Args:
            assignment_node: Assignment AST node

        Returns:
            Parameter name or None
        """
        # Use ts_utils helper function
        return _treesitter.get_assignment_target_name(assignment_node)

    def _resolve_base_class_paths(
        self,
        class_node: Node,
        file_imports: dict[str, str],
        library_name: str,
        source_path: Path | None = None,
        file_classes: set[str] | None = None,
    ) -> list[str]:
        """Resolve base class names to full paths using imports.

        Args:
            class_node: Class definition AST node
            file_imports: Import mappings for this file
            library_name: Name of the library (e.g., "panel")
            source_path: Path to the source file (optional, for resolving same-file classes)
            file_classes: Set of class names defined in the same file (optional)

        Returns:
            List of full base class paths
        """
        base_classes = self._get_base_classes(class_node)
        full_bases = []

        for base in base_classes:
            if "." in base:
                # Already qualified: "panel.layout.ListPanel"
                full_bases.append(base)
            # Check same-file classes BEFORE imports to avoid shadowing
            # (e.g., holoviews.element.raster defines Image class but also imports PIL.Image)
            elif file_classes and base in file_classes:
                # Base class is defined in the same file
                if source_path:
                    full_class_path = self._get_full_class_path(source_path, base, library_name)
                    if full_class_path:
                        full_bases.append(full_class_path)
                    else:
                        # Shouldn't happen, but fall back to simple name
                        full_bases.append(base)
                else:
                    # No source path, use simple name
                    full_bases.append(base)
            elif base in file_imports:
                # Resolve via imports
                full_bases.append(file_imports[base])
            elif source_path:
                # Last resort: try to construct path from source file
                full_class_path = self._get_full_class_path(source_path, base, library_name)
                if full_class_path:
                    full_bases.append(full_class_path)
                else:
                    # Fall back to simple name
                    full_bases.append(base)
            else:
                # No source path provided, use simple name
                full_bases.append(base)

        return full_bases

    def _is_parameterized_base(self, base_path: str, library_name: str | None = None) -> bool:
        """Check if a base class path is param.Parameterized.

        Args:
            base_path: Base class path to check
            library_name: Name of library being analyzed (for context-aware matching)

        Returns:
            True if base class is param.Parameterized
        """
        # Common forms that work across all libraries
        if base_path in (
            "param.Parameterized",
            "param.parameterized.Parameterized",
        ):
            return True

        # Relative import form only valid within param library's own source
        if base_path == ".parameterized.Parameterized":
            return library_name == "param"

        return False

    def _base_matches_parameterized_class(
        self, base_name: str, parameterized_classes: set[str]
    ) -> bool:
        """Check if a base class name matches any known Parameterized class.

        Handles matching both simple names (e.g., 'ListPanel') and full paths
        (e.g., 'panel.layout.base.ListPanel'), as well as relative imports and
        partial qualified paths.

        Args:
            base_name: Base class name to check (may be simple or fully qualified)
            parameterized_classes: Set of full paths to known Parameterized classes

        Returns:
            True if base_name matches a known Parameterized class
        """
        # Direct/exact match: base_name is a full path
        if base_name in parameterized_classes:
            return True

        # Simple name match: base_name has no dots (e.g., 'ListPanel')
        # This handles cases where a class is defined in the same file or imported without qualification
        # Match: 'ListPanel' matches 'panel.layout.base.ListPanel'
        if "." not in base_name:
            return any(full_path.endswith(f".{base_name}") for full_path in parameterized_classes)

        # Handle relative imports (starting with dots)
        if base_name.startswith("."):
            # Extract the class name from the relative import
            # e.g., '..layout.Feed' -> 'Feed'
            # e.g., '.parameterized.Parameterized' -> 'Parameterized'
            parts = base_name.lstrip(".").split(".")
            if parts:
                class_name = parts[-1]
                # Try to match by class name and partial path
                for full_path in parameterized_classes:
                    if full_path.endswith(f".{class_name}"):
                        # Also check if the relative path components match
                        # e.g., '..layout.Feed' should match paths ending with 'layout.feed.Feed'
                        if len(parts) > 1:
                            # Check if the module path components match
                            rel_module_parts = parts[:-1]  # Exclude class name
                            full_parts = full_path.split(".")
                            # Try to find matching suffix
                            for i in range(len(full_parts) - len(parts) + 1):
                                if full_parts[i : i + len(rel_module_parts)] == rel_module_parts:
                                    return True
                        else:
                            # Just class name, already matched
                            return True
            return False

        # Partial qualified path match (e.g., 'layout.Feed' or 'panel.layout.Feed')
        # This handles cases where imports create partial paths like "from panel import layout; layout.Feed"
        base_parts = base_name.split(".")
        base_class = base_parts[-1]

        for full_path in parameterized_classes:
            full_parts = full_path.split(".")

            # Check if the class names match
            if full_parts[-1] != base_class:
                continue

            # Check if base_name components are a suffix of full_path
            # e.g., 'panel.layout.Feed' matches 'panel.layout.feed.Feed'
            if len(base_parts) <= len(full_parts):
                # Try matching from the end (suffix match)
                matches = True
                j = len(full_parts) - 1
                for i in range(len(base_parts) - 1, -1, -1):
                    if base_parts[i] != full_parts[j]:
                        matches = False
                        break
                    j -= 1
                if matches:
                    return True

                # Also try matching as a contiguous substring (for complex import patterns)
                for offset in range(len(full_parts) - len(base_parts) + 1):
                    if full_parts[offset : offset + len(base_parts)] == base_parts:
                        return True

        return False
