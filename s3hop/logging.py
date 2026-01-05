"""Structured logging configuration for s3hop.

This module provides logging setup with support for:
- Console and file handlers
- Configurable log levels
- Structured log format
- Color output for terminals
"""

from __future__ import annotations

import logging
import sys
from typing import TextIO


class ColoredFormatter(logging.Formatter):
    """Formatter that adds color codes for terminal output."""

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def __init__(self, fmt: str | None = None, use_colors: bool = True) -> None:
        super().__init__(fmt)
        self.use_colors = use_colors

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        if self.use_colors and record.levelname in self.COLORS:
            return f"{self.COLORS[record.levelname]}{message}{self.RESET}"
        return message


def setup_logging(
    verbose: bool = False,
    quiet: bool = False,
    log_file: str | None = None,
    stream: TextIO | None = None,
) -> logging.Logger:
    """Configure logging for s3hop.

    Args:
        verbose: If True, set log level to DEBUG.
        quiet: If True, set log level to WARNING (overrides verbose).
        log_file: Optional path to log file.
        stream: Optional stream for console handler (default: stderr).

    Returns:
        Configured logger instance.
    """
    # Determine log level
    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    # Create logger
    logger = logging.getLogger("s3hop")
    logger.setLevel(level)

    # Remove any existing handlers
    logger.handlers.clear()

    # Console handler
    console_format = "%(message)s"
    if verbose:
        console_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    stream = stream or sys.stderr
    use_colors = hasattr(stream, "isatty") and stream.isatty()

    console_handler = logging.StreamHandler(stream)
    console_handler.setLevel(level)
    console_handler.setFormatter(ColoredFormatter(console_format, use_colors=use_colors))
    logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        file_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)  # Always log everything to file
        file_handler.setFormatter(logging.Formatter(file_format))
        logger.addHandler(file_handler)

    # Reduce noise from boto3/botocore
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Get a logger instance.

    Args:
        name: Optional name suffix for the logger.

    Returns:
        Logger instance.
    """
    if name:
        return logging.getLogger(f"s3hop.{name}")
    return logging.getLogger("s3hop")
