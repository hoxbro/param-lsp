from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from .__version import __version__
from ._logging import get_logger, setup_colored_logging

if TYPE_CHECKING:
    from ._types import TypeErrorDict

logger = get_logger(__name__, "main")

_DESCRIPTION = """\
param-lsp: Language Server Protocol implementation for HoloViz Param

Provides IDE support for Python codebases using Param with:
• Autocompletion for Param class constructors and parameter definitions
• Type checking and validation with real-time error diagnostics
• Hover documentation with parameter types, bounds, and descriptions
• Cross-file analysis for parameter inheritance tracking

Found a Bug or Have a Feature Request?
Open an issue at: https://github.com/hoxbro/param-lsp/issues

Need Help?
See the documentation at: https://param-lsp.readthedocs.io"""


def main():
    """Main entry point for the language server."""
    parser = argparse.ArgumentParser(
        description=_DESCRIPTION,
        prog="param-lsp",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default: %(default)s)",
    )
    parser.add_argument(
        "--python-path",
        type=str,
        help="Path to Python executable for analyzing external libraries (e.g., /path/to/venv/bin/python)",
    )
    parser.add_argument(
        "--extra-libraries",
        type=str,
        help="Comma-separated list of additional external libraries to analyze (e.g., geoviews,datashader)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Server subcommand
    server_parser = subparsers.add_parser(
        "server",
        help="Start the LSP server (default)",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    server_parser.add_argument("--tcp", action="store_true", help="Use TCP instead of stdio")
    server_parser.add_argument(
        "--port", type=int, default=8080, help="TCP port to listen on (default: %(default)s)"
    )
    server_parser.add_argument("--stdio", action="store_true", help="Use stdio (default)")

    # Check subcommand
    check_parser = subparsers.add_parser(
        "check",
        help="Check Python files for Param-related errors and warnings",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    check_parser.add_argument(
        "files",
        nargs="+",
        type=str,
        help="Python files or directories to check (directories are searched recursively, excluding .venv, .pixi, and node_modules)",
    )

    # Cache subcommand
    cache_parser = subparsers.add_parser(
        "cache",
        help="Manage the external library cache",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    cache_group = cache_parser.add_mutually_exclusive_group(required=True)
    cache_group.add_argument(
        "--show",
        action="store_true",
        help="Print the cache directory path",
    )
    cache_group.add_argument(
        "--generate",
        action="store_true",
        help="Generate cache for supported libraries",
    )
    cache_group.add_argument(
        "--regenerate",
        action="store_true",
        help="Clear existing cache and regenerate for supported libraries",
    )

    args = parser.parse_args()

    # Require explicit subcommand
    if args.command is None:
        parser.error(
            "A subcommand is required. Use 'param-lsp server' to start the LSP server.\n"
            "See 'param-lsp --help' for available commands."
        )

    # Configure colored logging
    log_level = getattr(logging, args.log_level)
    setup_colored_logging(level=log_level)

    # Parse extra libraries
    extra_libraries: set[str] = set()
    if args.extra_libraries:
        extra_libraries = {lib.strip() for lib in args.extra_libraries.split(",") if lib.strip()}

    # Configure Python environment for external library analysis
    # Priority: CLI argument > environment variables > current environment
    from ._analyzer.python_environment import PythonEnvironment

    if args.python_path:
        # Use explicitly specified Python path
        try:
            python_env = PythonEnvironment.from_path(args.python_path)
            logger.info(f"Using Python environment: {args.python_path}")
        except ValueError as e:
            parser.error(f"Invalid Python environment configuration: {e}")
    else:
        # Try to detect environment from environment variables, fall back to current
        python_env = PythonEnvironment.from_environment_variables()
        if python_env is None:
            # No environment variables set, use current Python environment
            python_env = PythonEnvironment.from_current()
            logger.info("Using current Python environment")

    # Handle subcommands
    if args.command == "cache":
        from ._analyzer.static_external_analyzer import ExternalClassInspector
        from .cache import CACHE_VERSION, external_library_cache
        from .constants import ALLOWED_EXTERNAL_LIBRARIES

        if args.show:
            cache_version_str = ".".join(map(str, CACHE_VERSION))
            print(f"{external_library_cache.cache_dir}::{cache_version_str}")
            return

        inspector = ExternalClassInspector(python_env=python_env, extra_libraries=extra_libraries)
        all_libraries = ALLOWED_EXTERNAL_LIBRARIES | extra_libraries

        if args.regenerate:
            external_library_cache.clear()
            for library in all_libraries:
                inspector.populate_library_cache(library)
            return

        if args.generate:
            for library in sorted(all_libraries):
                inspector.populate_library_cache(library)
            return

    elif args.command == "check":
        _run_check(args.files, python_env)
        return

    elif args.command == "server":
        # Check for mutually exclusive options
        if args.tcp and args.stdio:
            parser.error("--tcp and --stdio are mutually exclusive")

        # Import server only when actually needed
        from .server import create_server

        server = create_server(python_env=python_env, extra_libraries=extra_libraries)

        if args.tcp:
            logger.info(f"Starting Param LSP server ({__version__}) on TCP port {args.port}")
            server.start_tcp("localhost", args.port)
        else:
            logger.info(f"Starting Param LSP server ({__version__}) on stdio")
            server.start_io()


def _expand_paths(paths: list[str]) -> list[Path]:
    """
    Expand file/directory paths to a list of Python files.

    Directories are recursively searched for .py files, excluding
    .venv, .pixi, and node_modules directories.

    Args:
        paths: List of file or directory paths to expand

    Returns:
        List of Path objects pointing to Python files
    """
    EXCLUDED_DIRS = {".venv", ".pixi", "node_modules"}
    python_files: list[Path] = []

    for path_str in paths:
        path = Path(path_str)
        if not path.exists():
            print(f"Error: Path not found: {path_str}", file=sys.stderr)
            sys.exit(1)

        if path.is_file():
            if path.suffix == ".py":
                python_files.append(path)
            else:
                print(f"Error: Not a Python file: {path_str}", file=sys.stderr)
                sys.exit(1)
        elif path.is_dir():
            # Recursively find all .py files, excluding certain directories
            python_files.extend(
                py_file
                for py_file in path.rglob("*.py")
                if not any(parent.name in EXCLUDED_DIRS for parent in py_file.parents)
            )
        else:
            print(f"Error: Invalid path: {path_str}", file=sys.stderr)
            sys.exit(1)

    return python_files


def _run_check(files: list[str], python_env) -> None:
    """Run check command on the provided files."""
    from .analyzer import ParamAnalyzer

    # Expand directories to Python files
    python_files = _expand_paths(files)

    if not python_files:
        print("No Python files found to check", file=sys.stderr)
        sys.exit(1)

    analyzer = ParamAnalyzer(python_env=python_env)
    total_errors = 0
    total_warnings = 0
    all_diagnostics: list[tuple[str, TypeErrorDict]] = []

    # Analyze all files
    for path in python_files:
        try:
            content = path.read_text()
        except Exception as e:
            print(f"Error reading {path}: {e}", file=sys.stderr)
            sys.exit(1)

        # Analyze the file
        result = analyzer.analyze_file(content, str(path.absolute()))
        type_errors = result.get("type_errors", [])

        # Collect diagnostics
        for error in type_errors:
            all_diagnostics.append((str(path), error))
            if error.get("severity") == "error":
                total_errors += 1
            else:
                total_warnings += 1

    # Print diagnostics
    if all_diagnostics:
        for file_path, diagnostic in all_diagnostics:
            _print_diagnostic(file_path, diagnostic)

        # Print summary
        print()
        print(
            f"Found {total_errors} error(s) and {total_warnings} warning(s) in {len(python_files)} file(s)"
        )
        sys.exit(1 if total_errors > 0 else 0)
    else:
        print(f"No issues found in {len(python_files)} file(s)")
        sys.exit(0)


def _print_diagnostic(file_path: str, diagnostic: TypeErrorDict) -> None:
    """Print a single diagnostic in a readable format."""
    line = diagnostic["line"] + 1  # Convert to 1-indexed
    col = diagnostic["col"] + 1
    severity = diagnostic.get("severity", "error").upper()
    message = diagnostic["message"]
    code = diagnostic.get("code", "")

    # Color codes
    color = "\033[91m" if severity == "ERROR" else "\033[93m"  # Red or Yellow
    reset = "\033[0m"

    # Format: file:line:col: severity: message [code]
    location = f"{file_path}:{line}:{col}"
    code_str = f" [{code}]" if code else ""
    print(f"{location}: {color}{severity}{reset}: {message}{code_str}")


if __name__ == "__main__":
    main()
