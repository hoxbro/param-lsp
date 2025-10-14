"""Colored logging configuration for param-lsp."""

from __future__ import annotations

import logging
import sys
from typing import ClassVar


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds color to log messages based on level."""

    # ANSI color codes
    COLORS: ClassVar[dict[str, str]] = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET: ClassVar[str] = "\033[0m"
    BOLD: ClassVar[str] = "\033[1m"

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with color."""
        # Get the color for this log level
        color = self.COLORS.get(record.levelname, self.RESET)

        # Save the original levelname
        original_levelname = record.levelname

        # Add color to levelname
        record.levelname = f"{color}{self.BOLD}{record.levelname}{self.RESET}"

        # Format the message
        formatted = super().format(record)

        # Restore original levelname
        record.levelname = original_levelname

        return formatted


def setup_colored_logging(level: int = logging.INFO) -> None:
    """Configure colored logging for param-lsp.

    Args:
        level: The logging level to use (e.g., logging.INFO, logging.DEBUG)
    """
    # Check if we're in a terminal that supports colors
    supports_color = hasattr(sys.stderr, "isatty") and sys.stderr.isatty()

    # Create formatter
    if supports_color:
        formatter = ColoredFormatter(
            fmt="%(levelname)s - %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    else:
        # Fall back to plain formatter if colors not supported
        formatter = logging.Formatter(
            fmt="%(levelname)s - %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add new handler with colored formatter
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
