"""Test module for configuration utilities."""

import os
import pytest
from pathlib import Path
import tempfile
from typing import Generator
from unittest.mock import patch

from utils.config import ConfigLoader


@pytest.fixture
def sample_config_file() -> Generator[str, None, None]:
    """Create a temporary config file for testing."""
    config_content = """
# Test configuration
database:
  url: ${DATABASE_URL}
  pool_size: 5

openai:
  api_key: ${OPENAI_API_KEY}
  model: "gpt-4o-mini"
  temperature: 0.2
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as temp:
        temp.write(config_content)
        temp_path = temp.name

    yield temp_path

    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def mock_env_vars() -> Generator[None, None, None]:
    """Set up mock environment variables for testing."""
    with patch.dict(
        os.environ,
        {
            "DATABASE_URL": "postgresql://test:test@localhost/testdb",
            "OPENAI_API_KEY": "test-api-key",
        },
    ):
        yield


def test_config_loader_initialization() -> None:
    """Test that ConfigLoader initializes without errors."""
    loader = ConfigLoader()
    assert hasattr(loader, "settings")
    assert hasattr(loader, "config")


def test_get_with_section_and_key(mock_env_vars: None, sample_config_file: str) -> None:
    """Test retrieving a config value by section and key."""
    with patch.object(Path, "exists", return_value=True):
        with patch.object(Path, "open", return_value=open(sample_config_file, "r")):
            loader = ConfigLoader()
            loader._load_yaml_config()

            # Test getting a value
            assert loader.get("openai", "model") == "gpt-4o-mini"
            assert loader.get("database", "pool_size") == 5


def test_get_with_section_only(mock_env_vars: None, sample_config_file: str) -> None:
    """Test retrieving an entire section."""
    with patch.object(Path, "exists", return_value=True):
        with patch.object(Path, "open", return_value=open(sample_config_file, "r")):
            loader = ConfigLoader()
            loader._load_yaml_config()

            # Test getting a section
            openai_section = loader.get("openai")
            assert isinstance(openai_section, dict)
            assert openai_section["model"] == "gpt-4o-mini"
            assert openai_section["temperature"] == 0.2


def test_get_with_invalid_section() -> None:
    """Test that getting an invalid section raises KeyError."""
    loader = ConfigLoader()
    with pytest.raises(KeyError):
        loader.get("invalid_section")


def test_get_with_invalid_key(mock_env_vars: None, sample_config_file: str) -> None:
    """Test that getting an invalid key raises KeyError."""
    with patch.object(Path, "exists", return_value=True):
        with patch.object(Path, "open", return_value=open(sample_config_file, "r")):
            loader = ConfigLoader()
            loader._load_yaml_config()

            with pytest.raises(KeyError):
                loader.get("openai", "invalid_key")


def test_environment_variable_expansion(mock_env_vars: None, sample_config_file: str) -> None:
    """Test that environment variables are expanded in the config."""
    with patch.object(Path, "exists", return_value=True):
        with patch.object(Path, "open", return_value=open(sample_config_file, "r")):
            loader = ConfigLoader()
            loader._load_yaml_config()

            # Test environment variable expansion
            assert loader.get("database", "url") == "postgresql://test:test@localhost/testdb"
            assert loader.get("openai", "api_key") == "test-api-key"
