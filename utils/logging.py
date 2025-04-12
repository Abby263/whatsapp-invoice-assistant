"""Centralized logging configuration for the WhatsApp Invoice Assistant."""

import logging
import sys
import os
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


def get_logs_directory() -> Path:
    """
    Get the path to the logs directory.
    
    Returns:
        Path to the logs directory
    """
    # Get the project root directory (parent of utils)
    project_dir = Path(__file__).parent.parent
    logs_dir = project_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def get_default_log_file(name: str) -> str:
    """
    Get the default log file path for a given logger name.
    
    Args:
        name: Logger name
        
    Returns:
        Path to log file
    """
    sanitized_name = name.replace(".", "_").lower()
    logs_dir = get_logs_directory()
    return str(logs_dir / f"{sanitized_name}.log")


def setup_logger(
    name: str,
    level: Optional[Union[str, int]] = None,
    log_file: Optional[str] = None,
    log_format: Optional[str] = None,
    date_format: Optional[str] = None,
    use_file_handler: bool = True,
) -> logging.Logger:
    """
    Set up a logger with the specified configuration.

    Args:
        name: The name of the logger.
        level: The logging level (defaults to config value or INFO).
        log_file: Optional file path to write logs to.
        log_format: Optional format string for log messages.
        date_format: Optional format string for dates in log messages.
        use_file_handler: Whether to use a file handler. If True and log_file is None,
                         a default log file in the logs directory will be used.

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
        default_log_file = log_config.get("file")
    except Exception:
        default_level = "INFO"
        default_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        default_date_format = "%Y-%m-%d %H:%M:%S"
        default_log_file = None

    # Use provided values or defaults
    level = level or default_level
    log_format = log_format or default_format
    date_format = date_format or default_date_format

    # Determine log file path
    if use_file_handler:
        if log_file is None:
            # If specific log file not provided, use default from config or generate one
            log_file = default_log_file or get_default_log_file(name)
        else:
            # If log file is provided but doesn't include directory, put it in logs dir
            log_path = Path(log_file)
            if not log_path.is_absolute() and str(log_path.parent) == ".":
                logs_dir = get_logs_directory()
                log_file = str(logs_dir / log_path)

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
    if use_file_handler and log_file:
        # Ensure log directory exists
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(log_format, date_format)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        logger.info(f"Logging to file: {log_file}")

    return logger


# Create a default app-wide logger
app_logger = setup_logger("whatsapp_invoice_assistant")


def get_logger(name: str, use_file_handler: bool = True) -> logging.Logger:
    """
    Get a logger for a specific module.

    Args:
        name: The name of the module (typically __name__).
        use_file_handler: Whether to use a file handler.

    Returns:
        A configured logger.
    """
    module_name = name.split(".")[-1]
    full_name = f"whatsapp_invoice_assistant.{module_name}"
    return setup_logger(full_name, use_file_handler=use_file_handler)
