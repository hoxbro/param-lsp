from __future__ import annotations

import logging
import sys

from . import __version__
from .server import server

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for the language server."""

    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("HoloViz Param Language Server")
        print("Usage: python param_lsp.py [--tcp] [--port PORT]")
        print("\nOptions:")
        print("  --tcp          Use TCP instead of stdio")
        print("  --port PORT    TCP port to listen on (default: 8080)")
        print("  --help         Show this help message")
        return

    # Check for TCP mode
    if "--tcp" in sys.argv:
        port_idx = sys.argv.index("--port") + 1 if "--port" in sys.argv else None
        port = int(sys.argv[port_idx]) if port_idx and port_idx < len(sys.argv) else 8080

        logger.info(f"Starting Param LSP server ({__version__}) on TCP port {port}")
        server.start_tcp("localhost", port)
    else:
        logger.info(f"Starting Param LSP server ({__version__}) on stdio")
        server.start_io()
