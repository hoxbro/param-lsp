"""Colored logging configuration for param-lsp."""

from __future__ import annotations

import logging
import sys
from typing import ClassVar


class ContextLogger(logging.LoggerAdapter):
    """Logger adapter that prepends module context to messages."""

    def process(self, msg, kwargs):
        """Prepend context to the log message."""
        if self.extra:
            return f"{self.extra['context']} | {msg}", kwargs
        return msg, kwargs


def get_logger(name: str, context: str) -> ContextLogger:
    """Get a logger with module context.

    Args:
        name: The logger name (typically __name__)
        context: The module context to prepend to messages (e.g., "server", "cache", "analyzer")

    Returns:
        A ContextLogger that prepends the context to all log messages

    Example:
        >>> logger = get_logger(__name__, "server")
        >>> logger.info("Starting server")
        # Output: [I 2025-10-14 10:00:00.000 param-lsp] server | Starting server
    """
    base_logger = logging.getLogger(name)
    return ContextLogger(base_logger, {"context": context})


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

        # Determine app name based on logger name
        # Use the root module name (e.g., "param_lsp" -> "param-lsp", "pygls" -> "pygls")
        logger_root = record.name.split(".")[0]
        app_name = "param-lsp" if logger_root == "param_lsp" else logger_root

        # Build the formatted message in JupyterLab style
        # Module context is added by ContextLogger via get_logger()
        prefix = f"{color}[{level_code} {timestamp} {app_name}]{self.RESET}"
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

        # Determine app name based on logger name
        # Use the root module name (e.g., "param_lsp" -> "param-lsp", "pygls" -> "pygls")
        logger_root = record.name.split(".")[0]
        app_name = "param-lsp" if logger_root == "param_lsp" else logger_root

        # Build the formatted message in JupyterLab style
        # Module context is added by ContextLogger via get_logger()
        message = f"[{level_code} {timestamp} {app_name}] {record.getMessage()}"

        # Add exception info if present
        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)

        return message


def setup_colored_logging(level: int = logging.INFO) -> None:
    """Configure colored logging for param-lsp in JupyterLab style.

    Applies formatting to all loggers (param_lsp, pygls, etc.) with appropriate app names.

    Args:
        level: The logging level to use (e.g., logging.INFO, logging.DEBUG)
    """
    # Check if we're in a terminal that supports colors
    supports_color = hasattr(sys.stderr, "isatty") and sys.stderr.isatty()

    # Create formatter (use colored if terminal supports it, otherwise plain)
    formatter = ColoredFormatter() if supports_color else PlainFormatter()

    # Configure root logger to apply formatting to all logs
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add new handler with colored formatter
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    logging.getLogger("param_lsp").setLevel(level)
    logging.getLogger("pygls").setLevel(logging.WARNING)
