from __future__ import annotations

import argparse
import logging

from .__version import __version__

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

    args = parser.parse_args()

    # Import server only when actually needed to avoid loading during --help/--version
    from ._server.server import server

    if args.tcp:
        logger.info(f"Starting Param LSP server ({__version__}) on TCP port {args.port}")
        server.start_tcp("localhost", args.port)
    else:
        logger.info(f"Starting Param LSP server ({__version__}) on stdio")
        server.start_io()


if __name__ == "__main__":
    main()
