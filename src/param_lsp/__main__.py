from __future__ import annotations

import argparse
import logging

from . import __version__
from ._server.server import server

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for the language server."""
    parser = argparse.ArgumentParser(description="HoloViz Param Language Server", prog="param-lsp")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--tcp", action="store_true", help="Use TCP instead of stdio")
    parser.add_argument(
        "--port", type=int, default=8080, help="TCP port to listen on (default: %(default)s)"
    )

    args = parser.parse_args()

    if args.tcp:
        logger.info(f"Starting Param LSP server ({__version__}) on TCP port {args.port}")
        server.start_tcp("localhost", args.port)
    else:
        logger.info(f"Starting Param LSP server ({__version__}) on stdio")
        server.start_io()
