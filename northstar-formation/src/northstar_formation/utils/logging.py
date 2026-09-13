"""Logging configuration for Northstar Formation.

This module provides logging setup and logger retrieval utilities
for consistent logging across the Northstar Formation package.
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from typing import TextIO


def setup_logging(
    debug: bool = False,
    log_file: str | None = None,
    stream: TextIO | None = None,
) -> None:
    """Configure logging for the application.

    Sets up console and optional file logging with appropriate formatting.
    Uses Rich for enhanced console output when available.

    Args:
        debug: Enable debug level logging. If False, uses INFO level.
        log_file: Optional file path for log output.
        stream: Stream for console output (default: stderr).

    Example:
        >>> setup_logging(debug=True)
        >>> setup_logging(log_file="/var/log/northstar-formation.log")
    """
    level = logging.DEBUG if debug else logging.INFO
    stream = stream or sys.stderr

    # Root logger for northstar_formation
    root_logger = logging.getLogger("northstar_formation")
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Try to use Rich for enhanced console output
    try:
        from rich.logging import RichHandler

        console_handler: logging.Handler = RichHandler(
            rich_tracebacks=True,
            tracebacks_show_locals=debug,
            show_time=False,
            show_path=debug,
        )
        console_format = "%(message)s" if not debug else "[%(name)s] %(message)s"
    except ImportError:
        # Fall back to standard handler if Rich is not available
        console_handler = logging.StreamHandler(stream)
        console_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(console_format))
    root_logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)  # Always log debug to file
        file_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        file_handler.setFormatter(logging.Formatter(fmt=file_format, datefmt="%Y-%m-%d %H:%M:%S"))
        root_logger.addHandler(file_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("yaml").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a module.

    Creates a child logger under the northstar_formation namespace for consistent
    log formatting and level control.

    Args:
        name: Logger name, typically __name__ of the calling module.

    Returns:
        Configured logger instance.

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Processing model: %s", model_name)
    """
    # Extract just the module name if a full path is provided
    module_name = name.split(".")[-1]
    return logging.getLogger(f"northstar_formation.{module_name}")
