"""Colored logging configuration for param-lsp."""

from __future__ import annotations

import logging
import sys
from typing import ClassVar


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds color to log messages based on level.

    Formats log messages in JupyterLab style:
    [LEVEL YYYY-MM-DD HH:MM:SS.mmm ModuleName] message
    """

    # ANSI color codes
    COLORS: ClassVar[dict[str, str]] = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET: ClassVar[str] = "\033[0m"

    # Map full level names to single-letter codes like JupyterLab
    LEVEL_CODES: ClassVar[dict[str, str]] = {
        "DEBUG": "D",
        "INFO": "I",
        "WARNING": "W",
        "ERROR": "E",
        "CRITICAL": "C",
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with color in JupyterLab style."""
        # Get the color for this log level
        color = self.COLORS.get(record.levelname, self.RESET)

        # Get single-letter level code
        level_code = self.LEVEL_CODES.get(record.levelname, record.levelname[0])

        # Format timestamp with milliseconds
        ct = self.converter(record.created)
        timestamp = f"{ct.tm_year:04d}-{ct.tm_mon:02d}-{ct.tm_mday:02d} {ct.tm_hour:02d}:{ct.tm_min:02d}:{ct.tm_sec:02d}.{int(record.msecs):03d}"

        # Simplify module name (remove param_lsp prefix for cleaner output)
        module_name = record.name
        if module_name.startswith("param_lsp."):
            module_name = module_name[10:]  # Remove "param_lsp." prefix
        elif module_name == "param_lsp":
            module_name = "ParamLSP"

        # Build the formatted message in JupyterLab style
        prefix = f"{color}[{level_code} {timestamp} {module_name}]{self.RESET}"
        message = f"{prefix} {record.getMessage()}"

        # Add exception info if present
        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)

        return message


class PlainFormatter(logging.Formatter):
    """Plain formatter without colors, but same JupyterLab style format."""

    # Map full level names to single-letter codes like JupyterLab
    LEVEL_CODES: ClassVar[dict[str, str]] = {
        "DEBUG": "D",
        "INFO": "I",
        "WARNING": "W",
        "ERROR": "E",
        "CRITICAL": "C",
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record in JupyterLab style without colors."""
        # Get single-letter level code
        level_code = self.LEVEL_CODES.get(record.levelname, record.levelname[0])

        # Format timestamp with milliseconds
        ct = self.converter(record.created)
        timestamp = f"{ct.tm_year:04d}-{ct.tm_mon:02d}-{ct.tm_mday:02d} {ct.tm_hour:02d}:{ct.tm_min:02d}:{ct.tm_sec:02d}.{int(record.msecs):03d}"

        # Simplify module name (remove param_lsp prefix for cleaner output)
        module_name = record.name
        if module_name.startswith("param_lsp."):
            module_name = module_name[10:]  # Remove "param_lsp." prefix
        elif module_name == "param_lsp":
            module_name = "ParamLSP"

        # Build the formatted message in JupyterLab style
        message = f"[{level_code} {timestamp} {module_name}] {record.getMessage()}"

        # Add exception info if present
        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)

        return message


def setup_colored_logging(level: int = logging.INFO) -> None:
    """Configure colored logging for param-lsp in JupyterLab style.

    Args:
        level: The logging level to use (e.g., logging.INFO, logging.DEBUG)
    """
    # Check if we're in a terminal that supports colors
    supports_color = hasattr(sys.stderr, "isatty") and sys.stderr.isatty()

    # Create formatter (use colored if terminal supports it, otherwise plain)
    formatter = ColoredFormatter() if supports_color else PlainFormatter()

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
