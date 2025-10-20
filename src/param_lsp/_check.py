"""Check command implementation for validating Python files."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from .constants import EXCLUDED_DIRS

if TYPE_CHECKING:
    from ._types import TypeErrorDict


def expand_paths(paths: list[str]) -> list[Path]:
    """
    Expand file/directory paths to a list of Python files.

    Directories are recursively searched for .py files, excluding
    directories defined in EXCLUDED_DIRS constant.

    Args:
        paths: List of file or directory paths to expand

    Returns:
        Sorted list of Path objects pointing to Python files
    """
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

    # Sort files for consistent output
    return sorted(python_files)


def run_check(files: list[str], python_env) -> None:
    """Run check command on the provided files."""
    from .analyzer import ParamAnalyzer

    # Expand directories to Python files
    python_files = expand_paths(files)

    if not python_files:
        print("No Python files found to check", file=sys.stderr)
        sys.exit(1)

    analyzer = ParamAnalyzer(python_env=python_env)
    total_errors = 0
    total_warnings = 0
    all_diagnostics: list[tuple[str, str, TypeErrorDict]] = []

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

        # Collect diagnostics with file content
        for error in type_errors:
            all_diagnostics.append((str(path), content, error))
            if error.get("severity") == "error":
                total_errors += 1
            else:
                total_warnings += 1

    # Print diagnostics
    if all_diagnostics:
        for file_path, content, diagnostic in all_diagnostics:
            print_diagnostic(file_path, content, diagnostic)

        # Print summary
        print()
        print(
            f"Found {total_errors} error(s) and {total_warnings} warning(s) in {len(python_files)} file(s)"
        )
        sys.exit(1 if total_errors > 0 else 0)
    else:
        print(f"No issues found in {len(python_files)} file(s)")
        sys.exit(0)


def print_diagnostic(file_path: str, content: str, diagnostic: TypeErrorDict) -> None:
    """Print a single diagnostic in ruff-like format."""
    line = diagnostic["line"]  # 0-indexed
    col = diagnostic["col"]  # 0-indexed
    end_line = diagnostic["end_line"]  # 0-indexed
    end_col = diagnostic["end_col"]  # 0-indexed
    message = diagnostic["message"]
    code = diagnostic.get("code", "")
    severity = diagnostic.get("severity", "error")

    # Get all lines
    lines = content.split("\n")

    # Color codes
    red = "\033[91m"
    yellow = "\033[93m"
    cyan = "\033[36m"
    dim = "\033[2m"
    reset = "\033[0m"

    # Choose color based on severity
    error_color = yellow if severity == "warning" else red

    # Format: code: message (like ruff)
    print(f"{error_color}{code}:{reset} {message}")

    # Format location with arrow (like ruff)
    print(f"  {cyan}-->{reset} {file_path}:{line + 1}:{col + 1}")

    # Print separator
    print("   " + cyan + dim + "|" + reset)

    # Show context: 1-2 lines before
    context_before = 2
    for i in range(max(0, line - context_before), line):
        if i < len(lines):
            line_num_str = str(i + 1)
            print(f"{dim}{line_num_str:>2} {cyan}|{reset} {lines[i]}{reset}")

    # Print the error line with line number
    if line < len(lines):
        line_content = lines[line]
        line_num_str = str(line + 1)
        print(f"{line_num_str:>2} {cyan}|{reset} {line_content}")

        # Print underline carets
        # Calculate padding: line number field width (min 2) + 1 space + 1 for | + 1 space
        line_num_field_width = max(2, len(line_num_str))
        padding = line_num_field_width + 3 + col

        # Calculate underline width - use end_col if on same line
        if end_line == line:
            underline_width = max(1, end_col - col)
        else:
            # Multi-line error, underline to end of line
            underline_width = len(line_content[col:].rstrip()) or 1

        print(" " * padding + error_color + "^" * underline_width + reset)

    # Show context: 1-2 lines after
    context_after = 2
    for i in range(line + 1, min(len(lines), line + context_after + 1)):
        line_num_str = str(i + 1)
        print(f"{dim}{line_num_str:>2} {cyan}|{reset} {lines[i]}{reset}")

    # Print closing separator
    print("   " + cyan + dim + "|" + reset)
    print()
