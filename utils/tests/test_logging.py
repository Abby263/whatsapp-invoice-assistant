"""Test module for logging utilities."""

import logging
from pathlib import Path
from utils import logging as app_logging


def test_setup_logger() -> None:
    """Test that setup_logger creates a logger with the specified configuration."""
    logger = app_logging.setup_logger("test_logger", level="DEBUG")

    # Verify the logger has the right name
    assert logger.name == "test_logger"

    # Verify the logger level
    assert logger.level == logging.DEBUG

    # Verify the logger has at least one handler (console handler)
    assert len(logger.handlers) >= 1

    # Verify at least one handler is a StreamHandler
    assert any(isinstance(handler, logging.StreamHandler) for handler in logger.handlers)


def test_get_logger() -> None:
    """Test that get_logger creates a properly prefixed logger."""
    logger = app_logging.get_logger("test_module")

    # Verify the logger has the right name with app prefix
    assert logger.name == "whatsapp_invoice_assistant.test_module"


def test_logger_with_file(tmp_path: Path) -> None:
    """Test that setup_logger creates a file handler when a log file is specified."""
    log_file = tmp_path / "test.log"
    logger = app_logging.setup_logger("test_file_logger", level="INFO", log_file=str(log_file))

    # Verify the logger has at least two handlers (console and file)
    assert len(logger.handlers) >= 2

    # Verify one handler is a FileHandler
    assert any(isinstance(handler, logging.FileHandler) for handler in logger.handlers)

    # Verify the log file was created
    logger.info("Test log message")
    assert log_file.exists()

    # Verify the message was written to the file
    log_content = log_file.read_text()
    assert "Test log message" in log_content
