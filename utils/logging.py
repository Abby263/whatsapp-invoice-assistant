"""Centralized logging configuration for the WhatsApp Invoice Assistant."""

import logging
import sys
from typing import Optional, Union
from pathlib import Path

from .config import config


class CustomFormatter(logging.Formatter):
    """Custom formatter with ANSI colors for console output."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[41m",  # Red background
        "RESET": "\033[0m",  # Reset
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with colors for console output."""
        log_message = super().format(record)
        if hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
            level_name = record.levelname
            if level_name in self.COLORS:
                return f"{self.COLORS[level_name]}{log_message}{self.COLORS['RESET']}"
        return log_message


def setup_logger(
    name: str,
    level: Optional[Union[str, int]] = None,
    log_file: Optional[str] = None,
    log_format: Optional[str] = None,
    date_format: Optional[str] = None,
) -> logging.Logger:
    """
    Set up a logger with the specified configuration.

    Args:
        name: The name of the logger.
        level: The logging level (defaults to config value or INFO).
        log_file: Optional file path to write logs to.
        log_format: Optional format string for log messages.
        date_format: Optional format string for dates in log messages.

    Returns:
        The configured logger.
    """
    # Get configuration from env.yaml if available
    try:
        log_config = config.get("logging")
        default_level = log_config.get("level", "INFO")
        default_format = log_config.get(
            "format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        default_date_format = log_config.get("date_format", "%Y-%m-%d %H:%M:%S")
    except Exception:
        default_level = "INFO"
        default_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        default_date_format = "%Y-%m-%d %H:%M:%S"

    # Use provided values or defaults
    level = level or default_level
    log_format = log_format or default_format
    date_format = date_format or default_date_format

    # Convert string level to integer if needed
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Console handler with colored output
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_formatter = CustomFormatter(log_format, date_format)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler if requested
    if log_file:
        # Ensure log directory exists
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(log_format, date_format)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


# Create a default app-wide logger
app_logger = setup_logger("whatsapp_invoice_assistant")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a specific module.

    Args:
        name: The name of the module (typically __name__).

    Returns:
        A configured logger.
    """
    return setup_logger(f"whatsapp_invoice_assistant.{name}")
