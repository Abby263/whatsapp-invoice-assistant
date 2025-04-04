"""
Unit tests for the OpenAI service.
"""
import pytest
from unittest.mock import patch, MagicMock

from services.openai_service import OpenAIService
from constants.llm_configs import Models, TemperatureSettings

@pytest.fixture
def openai_service():
    """Fixture for creating an OpenAIService instance."""
    with patch("services.openai_service.OpenAI") as mock_openai:
        with patch("services.openai_service.config") as mock_config:
            # Configure mock to return a test API key
            mock_config.get.return_value = "test-api-key"
            
            # Create a service with the mocked config
            service = OpenAIService()
            
            # Verify the client was created with the correct API key
            mock_openai.assert_called_once_with(api_key="test-api-key")
            
            return service

def test_init_with_api_key():
    """Test initialization with explicit API key."""
    with patch("services.openai_service.OpenAI") as mock_openai:
        service = OpenAIService(api_key="explicit-test-key")
        
        # Verify the client was created with the explicit API key
        mock_openai.assert_called_once_with(api_key="explicit-test-key")
        
        # Verify the default configuration
        assert service.default_model == Models.GPT_4O_MINI
        assert service.default_temperature == TemperatureSettings.DEFAULT

def test_init_no_api_key():
    """Test initialization with no API key."""
    with patch("services.openai_service.config") as mock_config:
        # Configure mock to return None for API key
        mock_config.get.return_value = None
        
        # Should raise ValueError due to missing API key
        with pytest.raises(ValueError):
            OpenAIService()

def test_generate_chat_completion(openai_service):
    """Test generating a chat completion."""
    # Create a mock response
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Test completion"
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 5
    mock_response.usage.total_tokens = 15
    
    # Configure the mock client to return the mock response
    openai_service.client.chat.completions.create.return_value = mock_response
    
    # Test generating a chat completion
    messages = [{"role": "user", "content": "Test prompt"}]
    response = openai_service.generate_chat_completion(
        messages=messages,
        model="test-model",
        temperature=0.7,
        max_tokens=100
    )
    
    # Verify the client was called with the correct arguments
    openai_service.client.chat.completions.create.assert_called_once_with(
        model="test-model",
        messages=messages,
        temperature=0.7,
        max_tokens=100,
        stream=False
    )
    
    # Verify the response is correct
    assert response == mock_response

def test_generate_text(openai_service):
    """Test generating text from a prompt."""
    # Mock generate_chat_completion
    with patch.object(openai_service, "generate_chat_completion") as mock_generate:
        # Configure the mock to return a mock response
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Test completion"
        mock_generate.return_value = mock_response
        
        # Test generating text
        result = openai_service.generate_text(
            prompt="Test prompt",
            model="test-model",
            temperature=0.7,
            max_tokens=100
        )
        
        # Verify generate_chat_completion was called with the correct arguments
        mock_generate.assert_called_once_with(
            messages=[{"role": "user", "content": "Test prompt"}],
            model="test-model",
            temperature=0.7,
            max_tokens=100
        )
        
        # Verify the result is correct
        assert result == "Test completion"

def test_classify_text(openai_service):
    """Test classifying text."""
    # Mock generate_text
    with patch.object(openai_service, "generate_text") as mock_generate:
        # Configure the mock to return a category
        mock_generate.return_value = "Category1"
        
        # Test classifying text
        result = openai_service.classify_text(
            text="Test text",
            categories=["Category1", "Category2", "Category3"],
            model="test-model"
        )
        
        # Verify generate_text was called with appropriate arguments
        mock_generate.assert_called_once()
        call_args = mock_generate.call_args[1]
        assert "Test text" in call_args["prompt"]
        assert "Category1, Category2, Category3" in call_args["prompt"]
        assert call_args["model"] == "test-model"
        assert call_args["temperature"] == TemperatureSettings.CLASSIFICATION
        
        # Verify the result is correct
        assert result == "Category1"

def test_classify_text_invalid_category(openai_service):
    """Test classifying text with an invalid category response."""
    # Mock generate_text
    with patch.object(openai_service, "generate_text") as mock_generate:
        # Configure the mock to return an invalid category
        mock_generate.return_value = "InvalidCategory"
        
        # Test classifying text
        result = openai_service.classify_text(
            text="Test text",
            categories=["Category1", "Category2", "Category3"],
            model="test-model"
        )
        
        # Verify the result defaults to the first category
        assert result == "Category1"

def test_extract_entities(openai_service):
    """Test extracting entities from text."""
    # Mock generate_text
    with patch.object(openai_service, "generate_text") as mock_generate:
        # Configure the mock to return a JSON string
        mock_generate.return_value = '{"entity1": "value1", "entity2": "value2"}'
        
        # Test extracting entities
        schema = {"type": "object", "properties": {"entity1": {"type": "string"}}}
        result = openai_service.extract_entities(
            text="Test text",
            entity_schema=schema,
            model="test-model"
        )
        
        # Verify generate_text was called with appropriate arguments
        mock_generate.assert_called_once()
        call_args = mock_generate.call_args[1]
        assert "Test text" in call_args["prompt"]
        assert call_args["model"] == "test-model"
        assert call_args["temperature"] == TemperatureSettings.ENTITY_EXTRACTION
        
        # Verify the result is correct
        assert result == {"entity1": "value1", "entity2": "value2"}

def test_extract_entities_json_embedded(openai_service):
    """Test extracting entities from text with embedded JSON."""
    # Mock generate_text
    with patch.object(openai_service, "generate_text") as mock_generate:
        # Configure the mock to return text with embedded JSON
        mock_generate.return_value = 'Here are the entities: {"entity1": "value1", "entity2": "value2"} End of response.'
        
        # Test extracting entities
        schema = {"type": "object", "properties": {"entity1": {"type": "string"}}}
        result = openai_service.extract_entities(
            text="Test text",
            entity_schema=schema,
            model="test-model"
        )
        
        # Verify the result is correct
        assert result == {"entity1": "value1", "entity2": "value2"}

def test_extract_entities_json_error(openai_service):
    """Test extracting entities with JSON parsing error."""
    # Mock generate_text
    with patch.object(openai_service, "generate_text") as mock_generate:
        # Configure the mock to return invalid JSON
        mock_generate.return_value = 'This is not valid JSON'
        
        # Test extracting entities
        schema = {"type": "object", "properties": {"entity1": {"type": "string"}}}
        result = openai_service.extract_entities(
            text="Test text",
            entity_schema=schema,
            model="test-model"
        )
        
        # Verify the result is an empty dict on error
        assert result == {}

def test_track_usage(openai_service):
    """Test tracking usage information."""
    # Create a mock usage object
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 10
    mock_usage.completion_tokens = 5
    mock_usage.total_tokens = 15
    
    # Mock logger.info to capture logging
    with patch("services.openai_service.logger.info") as mock_logger:
        # Call _track_usage
        openai_service._track_usage(mock_usage, "test-model")
        
        # Verify logger.info was called with the correct message
        mock_logger.assert_called_once()
        log_message = mock_logger.call_args[0][0]
        assert "test-model" in log_message
        assert "prompt_tokens=10" in log_message
        assert "completion_tokens=5" in log_message
        assert "total_tokens=15" in log_message 