"""
Unit tests for the LLMFactory class.
"""
import os
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from services.llm_factory import LLMFactory
from constants.llm_configs import ModelProvider, Models, TemperatureSettings

# Create test directory
TEST_PROMPTS_DIR = Path("tests/fixtures/prompts")
TEST_PROMPTS_DIR.mkdir(parents=True, exist_ok=True)

# Create a test prompt file
TEST_PROMPT_FILE = TEST_PROMPTS_DIR / "test_prompt.txt"
TEST_PROMPT_CONTENT = "This is a test prompt for {var1} and {var2}."
with open(TEST_PROMPT_FILE, "w") as f:
    f.write(TEST_PROMPT_CONTENT)

@pytest.fixture
def llm_factory():
    """Fixture for creating an LLMFactory instance."""
    # Override prompts_dir to use test directory
    with patch.object(LLMFactory, "__init__", return_value=None) as mock_init:
        factory = LLMFactory()
        factory.prompts_dir = TEST_PROMPTS_DIR
        factory.prompt_cache = {}
        factory.config = {
            "provider": ModelProvider.OPENAI,
            "model": Models.GPT_4O_MINI,
            "temperature": TemperatureSettings.DEFAULT,
            "max_input_tokens": 8000,
            "max_output_tokens": 2000,
        }
        factory.api_keys = {
            ModelProvider.OPENAI: "test-openai-key",
            ModelProvider.ANTHROPIC: "test-anthropic-key",
            ModelProvider.COHERE: "test-cohere-key",
        }
        return factory

def test_init_with_config_override():
    """Test initialization with config override."""
    config_override = {
        "model": Models.GPT_4O,
        "temperature": 0.5,
    }
    
    # Mock config.get to return test values
    with patch("services.llm_factory.config") as mock_config:
        mock_config.get.return_value = "test-key"
        
        factory = LLMFactory(config_override=config_override)
        
        assert factory.config["model"] == Models.GPT_4O
        assert factory.config["temperature"] == 0.5

def test_load_prompt_template(llm_factory):
    """Test loading a prompt template from a file."""
    template = llm_factory.load_prompt_template("test_prompt")
    assert template == TEST_PROMPT_CONTENT
    
    # Test caching
    assert "test_prompt" in llm_factory.prompt_cache
    assert llm_factory.prompt_cache["test_prompt"] == TEST_PROMPT_CONTENT

def test_load_prompt_template_not_found(llm_factory):
    """Test loading a non-existent prompt template."""
    with pytest.raises(ValueError):
        llm_factory.load_prompt_template("non_existent_prompt")

def test_get_task_config(llm_factory):
    """Test getting task-specific configurations."""
    # Mock TASK_LLM_CONFIGS
    task_configs = {
        "test_task": {
            "model": Models.GPT_4O,
            "temperature": 0.7,
        }
    }
    
    with patch("services.llm_factory.TASK_LLM_CONFIGS", task_configs):
        config = llm_factory.get_task_config("test_task")
        
        # The base config should be updated with task config
        assert config["model"] == Models.GPT_4O
        assert config["temperature"] == 0.7
        
        # Default values should be preserved
        assert config["provider"] == ModelProvider.OPENAI
        assert config["max_input_tokens"] == 8000

def test_create_openai_instance(llm_factory):
    """Test creating an OpenAI instance."""
    mock_openai = MagicMock()
    
    with patch("services.llm_factory.OpenAI", return_value=mock_openai) as mock_openai_class:
        client = llm_factory._create_openai_instance(llm_factory.config)
        
        mock_openai_class.assert_called_once_with(api_key="test-openai-key")
        assert client == mock_openai

def test_generate_completion_openai(llm_factory):
    """Test generating a completion with OpenAI."""
    # Mock OpenAI client and response
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Test completion"
    mock_client.chat.completions.create.return_value = mock_response
    
    with patch.object(llm_factory, "_create_openai_instance", return_value=mock_client):
        result = llm_factory.generate_completion(
            prompt="Test prompt",
            task_name=None,
            config_override=None
        )
        
        assert result == "Test completion"
        mock_client.chat.completions.create.assert_called_once_with(
            model=Models.GPT_4O_MINI,
            messages=[{"role": "user", "content": "Test prompt"}],
            temperature=TemperatureSettings.DEFAULT,
            max_tokens=2000
        )

def test_get_completion_with_template(llm_factory):
    """Test getting a completion with a template."""
    # Mock load_prompt_template and generate_completion
    with patch.object(llm_factory, "load_prompt_template", return_value=TEST_PROMPT_CONTENT) as mock_load:
        with patch.object(llm_factory, "generate_completion", return_value="Test completion") as mock_generate:
            result = llm_factory.get_completion_with_template(
                template_name="test_prompt",
                template_vars={"var1": "value1", "var2": "value2"},
                task_name="test_task",
                config_override={"temperature": 0.8}
            )
            
            mock_load.assert_called_once_with("test_prompt")
            mock_generate.assert_called_once_with(
                "This is a test prompt for value1 and value2.",
                "test_task",
                {"temperature": 0.8}
            )
            assert result == "Test completion"

def test_track_usage(llm_factory):
    """Test tracking usage information."""
    prompt = "This is a test prompt"
    completion = "This is a test completion"
    model_name = Models.GPT_4O_MINI
    
    usage_info = llm_factory.track_usage(prompt, completion, model_name)
    
    assert usage_info["model"] == model_name
    assert usage_info["prompt_tokens"] > 0
    assert usage_info["completion_tokens"] > 0
    assert usage_info["total_tokens"] == usage_info["prompt_tokens"] + usage_info["completion_tokens"]
    assert usage_info["estimated_cost_usd"] >= 0 