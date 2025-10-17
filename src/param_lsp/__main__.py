from __future__ import annotations

import argparse
import logging

from .__version import __version__
from ._logging import get_logger, setup_colored_logging

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
        epilog="Use param-lsp with your editor's LSP client for the best experience.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--tcp", action="store_true", help="Use TCP instead of stdio")
    parser.add_argument(
        "--port", type=int, default=8080, help="TCP port to listen on (default: %(default)s)"
    )
    parser.add_argument("--stdio", action="store_true", help="Use stdio (default)")
    parser.add_argument(
        "--cache-dir",
        action="store_true",
        help="Print the cache directory path and exit",
    )
    parser.add_argument(
        "--generate-cache",
        action="store_true",
        help="Generate cache for supported libraries and exit",
    )
    parser.add_argument(
        "--regenerate-cache",
        action="store_true",
        help="Clear existing cache and regenerate for supported libraries",
    )
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

    args = parser.parse_args()

    # Configure colored logging
    log_level = getattr(logging, args.log_level)
    setup_colored_logging(level=log_level)

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

    # Handle --cache-dir flag
    if args.cache_dir:
        from .cache import CACHE_VERSION, external_library_cache

        cache_version_str = ".".join(map(str, CACHE_VERSION))
        print(f"{external_library_cache.cache_dir}::{cache_version_str}")
        return

    # Handle --regenerate-cache flag
    if args.regenerate_cache:
        from ._analyzer.static_external_analyzer import ExternalClassInspector
        from .cache import external_library_cache
        from .constants import ALLOWED_EXTERNAL_LIBRARIES

        external_library_cache.clear()

        inspector = ExternalClassInspector(python_env=python_env)
        total_cached = 0
        for library in ALLOWED_EXTERNAL_LIBRARIES:
            count = inspector.populate_library_cache(library)
        return

    # Handle --generate-cache flag
    if args.generate_cache:
        from ._analyzer.static_external_analyzer import ExternalClassInspector
        from .constants import ALLOWED_EXTERNAL_LIBRARIES

        inspector = ExternalClassInspector(python_env=python_env)
        total_cached = 0
        for library in sorted(ALLOWED_EXTERNAL_LIBRARIES):
            count = inspector.populate_library_cache(library)
            total_cached += count
        return

    # Check for mutually exclusive options
    if args.tcp and args.stdio:
        parser.error("--tcp and --stdio are mutually exclusive")

    # Import server only when actually needed to avoid loading during --help/--version
    from .server import create_server

    server = create_server(python_env=python_env)

    if args.tcp:
        logger.info(f"Starting Param LSP server ({__version__}) on TCP port {args.port}")
        server.start_tcp("localhost", args.port)
    else:
        logger.info(f"Starting Param LSP server ({__version__}) on stdio")
        server.start_io()


if __name__ == "__main__":
    main()
