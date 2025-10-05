"""
Static external class analyzer for param-lsp.

This module provides static analysis of external Parameterized classes without
runtime module loading. It uses AST parsing to extract parameter information
from source files directly.
"""

from __future__ import annotations

import logging
import site
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import parso

from param_lsp.constants import ALLOWED_EXTERNAL_LIBRARIES
from param_lsp.models import ParameterInfo, ParameterizedInfo

from . import parso_utils
from .ast_navigator import ImportHandler, ParameterDetector
from .parameter_extractor import extract_parameter_info_from_assignment

if TYPE_CHECKING:
    from parso.tree import NodeOrLeaf

logger = logging.getLogger(__name__)


class StaticExternalAnalyzer:
    """Static analyzer for external Parameterized classes.

    Analyzes external libraries using pure AST parsing without runtime imports.
    Discovers source files and extracts parameter information statically.
    """

    def __init__(self):
        self.library_source_paths: dict[str, list[Path]] = {}
        self.parsed_classes: dict[str, ParameterizedInfo | None] = {}
        self.analyzed_files: dict[Path, dict[str, Any]] = {}

    def analyze_external_class(self, full_class_path: str) -> ParameterizedInfo | None:
        """Analyze an external class using static analysis.

        Args:
            full_class_path: Full path like "panel.widgets.IntSlider"

        Returns:
            ParameterizedInfo if successful, None otherwise
        """
        if full_class_path in self.parsed_classes:
            return self.parsed_classes[full_class_path]

        # Check if this library is allowed
        root_module = full_class_path.split(".")[0]
        if root_module not in ALLOWED_EXTERNAL_LIBRARIES:
            logger.debug(f"Library {root_module} not in allowed list")
            self.parsed_classes[full_class_path] = None
            return None

        try:
            class_info = self._analyze_class_from_source(full_class_path)
            self.parsed_classes[full_class_path] = class_info
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

        # Search for the class in source files
        for source_path in source_paths:
            try:
                class_info = self._find_class_in_file(source_path, full_class_path, class_name)
                if class_info:
                    return class_info
            except Exception as e:
                logger.debug(f"Error analyzing {source_path}: {e}")
                continue

        logger.debug(f"Class {full_class_path} not found in source files")
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

        # Search in site-packages directories
        for site_dir in [*site.getsitepackages(), site.getusersitepackages()]:
            if site_dir and Path(site_dir).exists():
                library_path = Path(site_dir) / library_name
                if library_path.exists():
                    source_paths.extend(self._collect_python_files(library_path))

        # Search in sys.path
        for sys_path in sys.path:
            if sys_path:
                sys_path_obj = Path(sys_path)
                if sys_path_obj.exists():
                    library_path = sys_path_obj / library_name
                    if library_path.exists():
                        source_paths.extend(self._collect_python_files(library_path))

        # Remove duplicates and cache
        unique_paths = list(set(source_paths))
        self.library_source_paths[library_name] = unique_paths

        logger.debug(f"Found {len(unique_paths)} source files for {library_name}")
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
                python_files.extend(path for path in directory.rglob("*.py") if path.is_file())
        except (OSError, PermissionError) as e:
            logger.debug(f"Error accessing {directory}: {e}")

        return python_files

    def _find_class_in_file(
        self, source_path: Path, full_class_path: str, class_name: str
    ) -> ParameterizedInfo | None:
        """Find and analyze a specific class in a source file.

        Args:
            source_path: Path to Python source file
            full_class_path: Full class path for verification
            class_name: Name of the class to find

        Returns:
            ParameterizedInfo if class found and is Parameterized
        """
        # Check cache first
        if source_path in self.analyzed_files:
            file_classes = self.analyzed_files[source_path]
            if class_name in file_classes:
                return file_classes[class_name]

        try:
            # Read and parse the source file
            source_code = source_path.read_text(encoding="utf-8")
            tree = parso.parse(source_code)

            # Analyze the file
            file_analysis = self._analyze_file_ast(tree, source_code)
            self.analyzed_files[source_path] = file_analysis

            # Return the specific class if found
            return file_analysis.get(class_name)

        except Exception as e:
            logger.debug(f"Error parsing {source_path}: {e}")
            return None

    def _analyze_file_ast(
        self, tree: NodeOrLeaf, source_code: str
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

        # Find and analyze classes
        self._walk_ast_for_classes(tree, imports, classes, source_code.split("\n"))

        return classes

    def _walk_ast_for_imports(self, node: NodeOrLeaf, import_handler: ImportHandler) -> None:
        """Walk AST to find and parse import statements.

        Args:
            node: Current AST node
            import_handler: Handler for processing imports
        """
        if hasattr(node, "type"):
            if node.type == "import_name":
                import_handler.handle_import(node)
            elif node.type == "import_from":
                import_handler.handle_import_from(node)

        # Recursively walk children
        for child in parso_utils.get_children(node):
            self._walk_ast_for_imports(child, import_handler)

    def _walk_ast_for_classes(
        self,
        node: NodeOrLeaf,
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
        if hasattr(node, "type") and node.type == "classdef":
            class_info = self._analyze_class_definition(node, imports, source_lines)
            if class_info:
                classes[class_info.name] = class_info

        # Recursively walk children
        for child in parso_utils.get_children(node):
            self._walk_ast_for_classes(child, imports, classes, source_lines)

    def _analyze_class_definition(
        self, class_node: NodeOrLeaf, imports: dict[str, str], source_lines: list[str]
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

    def _get_class_name(self, class_node: NodeOrLeaf) -> str | None:
        """Extract class name from class definition node.

        Args:
            class_node: Class definition AST node

        Returns:
            Class name or None if not found
        """
        for child in parso_utils.get_children(class_node):
            if child.type == "name":
                return parso_utils.get_value(child)
        return None

    def _inherits_from_parameterized(
        self, class_node: NodeOrLeaf, imports: dict[str, str]
    ) -> bool:
        """Check if a class inherits from param.Parameterized.

        Args:
            class_node: Class definition AST node
            imports: Import mappings

        Returns:
            True if class inherits from param.Parameterized
        """
        # Look for base classes between parentheses
        in_parentheses = False
        for child in parso_utils.get_children(class_node):
            if child.type == "operator" and parso_utils.get_value(child) == "(":
                in_parentheses = True
            elif child.type == "operator" and parso_utils.get_value(child) == ")":
                in_parentheses = False
            elif (
                in_parentheses
                and child.type in ("name", "power", "atom_expr")
                and self._is_parameterized_base_class(child, imports)
            ):
                return True
        return False

    def _is_parameterized_base_class(self, base_node: NodeOrLeaf, imports: dict[str, str]) -> bool:
        """Check if a base class node represents param.Parameterized.

        Args:
            base_node: AST node representing a base class
            imports: Import mappings

        Returns:
            True if base class is param.Parameterized
        """
        base_class_name = self._resolve_base_class_name(base_node)
        if not base_class_name:
            return False

        # Check direct reference
        if base_class_name == "param.Parameterized":
            return True

        # Check imports
        if base_class_name in imports:
            full_name = imports[base_class_name]
            if full_name == "param.Parameterized":
                return True

        return False

    def _resolve_base_class_name(self, node: NodeOrLeaf) -> str | None:
        """Resolve base class name from AST node.

        Args:
            node: AST node representing base class reference

        Returns:
            Resolved base class name
        """
        if node.type == "name":
            return parso_utils.get_value(node)
        elif node.type in ("power", "atom_expr"):
            # Handle dotted names like param.Parameterized
            parts = []
            for child in parso_utils.get_children(node):
                if child.type == "name":
                    parts.append(parso_utils.get_value(child))
                elif child.type == "trailer":
                    parts.extend(
                        parso_utils.get_value(trailer_child)
                        for trailer_child in parso_utils.get_children(child)
                        if trailer_child.type == "name"
                    )
            return ".".join(parts) if parts else None
        return None

    def _extract_class_parameters(
        self,
        class_node: NodeOrLeaf,
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
        # Find class suite (body)
        suite_node = None
        for child in parso_utils.get_children(class_node):
            if child.type == "suite":
                suite_node = child
                break

        if not suite_node:
            return

        # Walk through statements in class body
        self._walk_class_body(suite_node, parameter_detector, class_info, source_lines, imports)

    def _walk_class_body(
        self,
        suite_node: NodeOrLeaf,
        parameter_detector: ParameterDetector,
        class_info: ParameterizedInfo,
        source_lines: list[str],
        imports: dict[str, str],
    ) -> None:
        """Walk through class body to find parameter assignments.

        Args:
            suite_node: Suite AST node containing class body
            parameter_detector: Detector for parameter assignments
            class_info: Class info to populate
            source_lines: Source code lines
        """
        for child in parso_utils.get_children(suite_node):
            if child.type == "simple_stmt":
                # Check for assignment statements
                for stmt_child in parso_utils.get_children(child):
                    if (
                        stmt_child.type == "expr_stmt"
                        and parameter_detector.is_parameter_assignment(stmt_child)
                    ):
                        param_info = self._extract_parameter_info(
                            stmt_child, source_lines, imports
                        )
                        if param_info:
                            class_info.add_parameter(param_info)
            elif hasattr(child, "type"):
                # Recursively search in nested structures
                self._walk_class_body(child, parameter_detector, class_info, source_lines, imports)

    def _extract_parameter_info(
        self, assignment_node: NodeOrLeaf, source_lines: list[str], imports: dict[str, str]
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

    def _get_parameter_name(self, assignment_node: NodeOrLeaf) -> str | None:
        """Extract parameter name from assignment node.

        Args:
            assignment_node: Assignment AST node

        Returns:
            Parameter name or None
        """
        # Find the name before the '=' operator
        for child in parso_utils.get_children(assignment_node):
            if child.type == "name":
                return parso_utils.get_value(child)
            elif child.type == "operator" and parso_utils.get_value(child) == "=":
                break
        return None
