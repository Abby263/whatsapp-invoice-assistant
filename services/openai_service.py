"""
OpenAI service for integrating with the OpenAI API.

This module provides a service class for interacting with OpenAI models,
specifically optimized for the WhatsApp Invoice Assistant application.
"""
import os
import json
import logging
from typing import Dict, Any, Optional, List, Union
from pathlib import Path

from openai import OpenAI
from openai.types.chat import ChatCompletion
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from utils.config import config
from constants.llm_configs import Models, TemperatureSettings, TokenLimits

logger = logging.getLogger(__name__)

class OpenAIService:
    """
    Service for interacting with OpenAI models.
    
    This class provides methods for:
    - Text completion using chat models
    - Tracking token usage and costs
    - Error handling and retry logic
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the OpenAI service.
        
        Args:
            api_key: Optional API key for OpenAI
        """
        # Get API key from config or environment variable
        self.api_key = api_key or config.get(
            "openai", "api_key", default=os.environ.get("OPENAI_API_KEY")
        )
        
        if not self.api_key:
            logger.error("OpenAI API key not found. Please set OPENAI_API_KEY environment variable.")
            raise ValueError("OpenAI API key not found")
            
        # Initialize OpenAI client
        self.client = OpenAI(api_key=self.api_key)
        
        # Default configuration
        self.default_model = Models.GPT_4O_MINI
        self.default_temperature = TemperatureSettings.DEFAULT
        self.default_max_tokens = TokenLimits.DEFAULT_MAX_OUTPUT_TOKENS
        
        logger.debug("OpenAI service initialized")
        
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((TimeoutError, ConnectionError)),
        reraise=True
    )
    def generate_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> ChatCompletion:
        """
        Generate a chat completion using OpenAI's chat models.
        
        Args:
            messages: List of message dictionaries with role and content
            model: Optional model to use
            temperature: Optional temperature parameter
            max_tokens: Optional max tokens parameter
            stream: Whether to stream the response
            
        Returns:
            OpenAI ChatCompletion object
        """
        try:
            # Use provided parameters or defaults
            _model = model or self.default_model
            _temperature = temperature or self.default_temperature
            _max_tokens = max_tokens or self.default_max_tokens
            
            # Log the request details at debug level
            logger.debug(
                f"Generating chat completion with model={_model}, "
                f"temperature={_temperature}, max_tokens={_max_tokens}"
            )
            
            # Make the API call
            response = self.client.chat.completions.create(
                model=_model,
                messages=messages,
                temperature=_temperature,
                max_tokens=_max_tokens,
                stream=stream
            )
            
            # Track usage if not streaming
            if not stream and hasattr(response, 'usage'):
                self._track_usage(response.usage, _model)
                
            return response
            
        except Exception as e:
            logger.error(f"Error generating OpenAI chat completion: {str(e)}")
            raise
    
    def generate_text(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Generate text from a single prompt.
        
        Args:
            prompt: The prompt text
            model: Optional model to use
            temperature: Optional temperature parameter
            max_tokens: Optional max tokens parameter
            
        Returns:
            Generated text as a string
        """
        messages = [{"role": "user", "content": prompt}]
        
        response = self.generate_chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        return response.choices[0].message.content
    
    def classify_text(
        self,
        text: str,
        categories: List[str],
        model: Optional[str] = None
    ) -> str:
        """
        Classify text into one of the provided categories.
        
        Args:
            text: The text to classify
            categories: List of possible categories
            model: Optional model to use
            
        Returns:
            The selected category
        """
        # Create a prompt for classification
        categories_str = ", ".join(categories)
        prompt = (
            f"Classify the following text into one of these categories: {categories_str}.\n\n"
            f"Text: \"{text}\"\n\n"
            f"Classification (return only the category name):"
        )
        
        # Use a low temperature for more deterministic results
        response = self.generate_text(
            prompt=prompt,
            model=model,
            temperature=TemperatureSettings.CLASSIFICATION,
            max_tokens=10  # Very short response for classification
        )
        
        # Clean and validate the response
        response = response.strip()
        
        # Ensure the response is one of the valid categories
        if response.lower() not in [c.lower() for c in categories]:
            logger.warning(f"Classification returned invalid category: {response}")
            # Default to the first category if the response is invalid
            return categories[0]
            
        # Find the correctly cased category
        for category in categories:
            if category.lower() == response.lower():
                return category
                
        # This should not happen, but just in case
        return response
    
    def extract_entities(
        self,
        text: str,
        entity_schema: Dict[str, Any],
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract structured entities from text according to a schema.
        
        Args:
            text: The text to extract entities from
            entity_schema: Schema defining the entities to extract
            model: Optional model to use
            
        Returns:
            Dictionary of extracted entities
        """
        # Create a prompt for entity extraction
        schema_str = json.dumps(entity_schema, indent=2)
        prompt = (
            f"Extract the following entities from the text according to this schema:\n"
            f"{schema_str}\n\n"
            f"Text: \"{text}\"\n\n"
            f"Extracted entities (JSON format):"
        )
        
        # Use a low temperature for more deterministic results
        response = self.generate_text(
            prompt=prompt,
            model=model,
            temperature=TemperatureSettings.ENTITY_EXTRACTION
        )
        
        # Extract the JSON response
        try:
            # Find JSON content in the response
            json_start = response.find("{")
            json_end = response.rfind("}")
            
            if json_start >= 0 and json_end >= 0:
                json_str = response[json_start:json_end+1]
                result = json.loads(json_str)
            else:
                # If no JSON found, try to parse the entire response
                result = json.loads(response)
                
            return result
            
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON from entity extraction response: {response}")
            return {}
    
    def _track_usage(self, usage: Any, model: str) -> None:
        """
        Track usage information from an API response.
        
        Args:
            usage: Usage information from the API response
            model: The model used
        """
        if not usage:
            return
            
        # Log usage information
        logger.info(
            f"OpenAI API usage: model={model}, "
            f"prompt_tokens={usage.prompt_tokens}, "
            f"completion_tokens={usage.completion_tokens}, "
            f"total_tokens={usage.total_tokens}"
        )
        
        # In a real implementation, you would store this in a database
        # to track usage and costs over time 