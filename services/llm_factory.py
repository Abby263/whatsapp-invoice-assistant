"""
LLM Factory for creating and managing LLM instances.

This module provides a factory class for creating and managing LLM instances
with different configurations and capabilities.
"""
import os
import json
import logging
import re
from typing import Dict, Any, Optional, List, Union, Callable
from pathlib import Path
from functools import lru_cache
from datetime import datetime, timedelta
from decimal import Decimal
import uuid
import inspect
import time
import importlib.util
import asyncio

from utils.config import config
from constants.llm_configs import (
    ModelProvider, 
    Models, 
    TemperatureSettings,
    TokenLimits,
    DEFAULT_LLM_CONFIG,
    TASK_LLM_CONFIGS,
    LLMProvider, 
    ModelName
)
from constants.prompt_mappings import AgentType, get_prompt_for_agent
from constants.fallback_messages import GENERAL_FALLBACKS, QUERY_FALLBACKS
from constants.invoice_processing_messages import get_invoice_processing_message

logger = logging.getLogger(__name__)

class LLMFactory:
    """
    Factory class for creating and managing LLM instances.
    
    This class handles:
    - Loading prompt templates from files
    - Creating LLM instances with specific configurations
    - Managing caching for prompts and responses
    - Tracking token usage and costs
    """
    
    def __init__(self, config_override: Optional[Dict[str, Any]] = None):
        """
        Initialize the LLM Factory.
        
        Args:
            config_override: Optional configuration override dictionary
        """
        self.prompts_dir = Path("prompts")
        self.prompt_cache = {}
        self.config = DEFAULT_LLM_CONFIG.copy()
        
        if config_override:
            self.config.update(config_override)
            
        # Ensure required directories exist
        if not self.prompts_dir.exists():
            logger.warning(f"Prompts directory not found at {self.prompts_dir}")
            
        # Load API keys from config and fallback to environment variables
        self.api_keys = {}
        
        # OpenAI API key
        try:
            self.api_keys[ModelProvider.OPENAI] = config.get("openai", "api_key")
        except KeyError:
            self.api_keys[ModelProvider.OPENAI] = os.environ.get("OPENAI_API_KEY")
            
        # Anthropic API key
        try:
            self.api_keys[ModelProvider.ANTHROPIC] = config.get("anthropic", "api_key")
        except KeyError:
            self.api_keys[ModelProvider.ANTHROPIC] = os.environ.get("ANTHROPIC_API_KEY")
            
        # Cohere API key
        try:
            self.api_keys[ModelProvider.COHERE] = config.get("cohere", "api_key")
        except KeyError:
            self.api_keys[ModelProvider.COHERE] = os.environ.get("COHERE_API_KEY")
        
        # Validate we have the API key for the configured provider
        provider = self.config.get("provider")
        if not self.api_keys.get(provider):
            logger.error(f"No API key found for provider {provider}")
            
    def load_prompt_template(self, prompt_name: str) -> str:
        """
        Load a prompt template from a file.
        
        Args:
            prompt_name: Name of the prompt template to load
            
        Returns:
            The prompt template text
        """
        # Check cache first
        if prompt_name in self.prompt_cache:
            return self.prompt_cache[prompt_name]
        
        # Determine possible file paths
        file_paths = []
        
        # Try both with and without _prompt suffix
        for name_variant in [prompt_name, f"{prompt_name}_prompt"]:
            file_name = f"{name_variant}.txt"
            if not file_name.endswith(".txt"):
                file_name = f"{file_name}.txt"
                
            file_paths.append(self.prompts_dir / file_name)
        
        # Try to load from any of the possible paths
        for file_path in file_paths:
            try:
                logger.debug(f"Attempting to load prompt from: {file_path}")
                with open(file_path, "r") as f:
                    template = f.read()
                
                # Cache the template
                self.prompt_cache[prompt_name] = template
                logger.debug(f"Successfully loaded prompt from: {file_path}")
                return template
            except FileNotFoundError:
                logger.debug(f"Prompt file not found at: {file_path}")
                continue
        
        # If we get here, all paths failed
        logger.error(f"Prompt template file not found. Tried: {file_paths}")
        raise ValueError(f"Prompt template not found: {prompt_name}")
            
    def get_task_config(self, task_name: str) -> Dict[str, Any]:
        """
        Get configuration for a specific task.
        
        Args:
            task_name: Name of the task
            
        Returns:
            Configuration dictionary for the task
        """
        task_config = self.config.copy()
        
        if task_name in TASK_LLM_CONFIGS:
            task_config.update(TASK_LLM_CONFIGS[task_name])
            
        return task_config
    
    def create_llm_instance(self, task_name: Optional[str] = None) -> Any:
        """
        Create an LLM instance for a specific task.
        
        Args:
            task_name: Optional name of the task
            
        Returns:
            An LLM instance configured for the task
        """
        # Get configuration for the task
        if task_name:
            config = self.get_task_config(task_name)
        else:
            config = self.config.copy()
            
        # Create the LLM instance based on the provider
        provider = config.get("provider")
        
        if provider == ModelProvider.OPENAI:
            return self._create_openai_instance(config)
        elif provider == ModelProvider.ANTHROPIC:
            return self._create_anthropic_instance(config)
        elif provider == ModelProvider.COHERE:
            return self._create_cohere_instance(config)
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")
    
    def _create_openai_instance(self, config: Dict[str, Any]) -> Any:
        """
        Create an OpenAI LLM instance.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            An OpenAI LLM instance
        """
        # Lazy import to avoid dependency issues
        try:
            from openai import OpenAI
        except ImportError:
            logger.error("OpenAI package not installed. Run 'pip install openai'")
            raise ImportError("OpenAI package not installed")
            
        client = OpenAI(api_key=self.api_keys[ModelProvider.OPENAI])
        
        # Return a callable object that can be used to invoke the model
        model_name = config.get("model", Models.DEFAULT)
        temperature = config.get("temperature", TemperatureSettings.DEFAULT)
        max_tokens = config.get("max_output_tokens", TokenLimits.DEFAULT_MAX_OUTPUT_TOKENS)
        
        logger.debug(f"Creating OpenAI instance with model={model_name}, temp={temperature}, max_tokens={max_tokens}")
        
        return client
    
    def _create_anthropic_instance(self, config: Dict[str, Any]) -> Any:
        """
        Create an Anthropic LLM instance.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            An Anthropic LLM instance
        """
        # Lazy import to avoid dependency issues
        try:
            import anthropic
        except ImportError:
            logger.error("Anthropic package not installed. Run 'pip install anthropic'")
            raise ImportError("Anthropic package not installed")
            
        client = anthropic.Anthropic(api_key=self.api_keys[ModelProvider.ANTHROPIC])
        
        # Return the client
        return client
    
    def _create_cohere_instance(self, config: Dict[str, Any]) -> Any:
        """
        Create a Cohere LLM instance.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            A Cohere LLM instance
        """
        # Lazy import to avoid dependency issues
        try:
            import cohere
        except ImportError:
            logger.error("Cohere package not installed. Run 'pip install cohere'")
            raise ImportError("Cohere package not installed")
            
        client = cohere.Client(api_key=self.api_keys[ModelProvider.COHERE])
        
        # Return the client
        return client
    
    def generate_completion(
        self, 
        prompt: str, 
        task_name: Optional[str] = None,
        config_override: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate a completion for a prompt using the appropriate LLM.
        
        Args:
            prompt: The prompt text
            task_name: Optional name of the task
            config_override: Optional configuration override
            
        Returns:
            The generated completion text
        """
        # Get configuration
        config = self.get_task_config(task_name) if task_name else self.config.copy()
        
        if config_override:
            config.update(config_override)
            
        # Create LLM instance
        provider = config.get("provider")
        model_name = config.get("model", Models.DEFAULT)
        temperature = config.get("temperature", TemperatureSettings.DEFAULT)
        max_tokens = config.get("max_output_tokens", TokenLimits.DEFAULT_MAX_OUTPUT_TOKENS)
        
        # Generate completion based on provider
        if provider == ModelProvider.OPENAI:
            client = self._create_openai_instance(config)
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content
            
        elif provider == ModelProvider.ANTHROPIC:
            client = self._create_anthropic_instance(config)
            response = client.messages.create(
                model=model_name,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
            
        elif provider == ModelProvider.COHERE:
            client = self._create_cohere_instance(config)
            response = client.generate(
                model=model_name,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature
            )
            return response.generations[0].text
            
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")
    
    async def generate_completion(
        self, 
        prompt: str, 
        temperature: float = None,
        max_tokens: int = None,
        task_name: Optional[str] = None,
        config_override: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate a completion for a prompt using the appropriate LLM asynchronously.
        
        Args:
            prompt: The prompt text
            temperature: Optional temperature override
            max_tokens: Optional max tokens override
            task_name: Optional name of the task
            config_override: Optional configuration override
            
        Returns:
            The generated completion text
        """
        # Get configuration
        config = self.get_task_config(task_name) if task_name else self.config.copy()
        
        if config_override:
            config.update(config_override)
            
        # Override with explicitly provided parameters
        if temperature is not None:
            config["temperature"] = temperature
        if max_tokens is not None:
            config["max_output_tokens"] = max_tokens
            
        # Create LLM instance
        provider = config.get("provider")
        model_name = config.get("model", Models.DEFAULT)
        temperature = config.get("temperature", TemperatureSettings.DEFAULT)
        max_tokens = config.get("max_output_tokens", TokenLimits.DEFAULT_MAX_OUTPUT_TOKENS)
        
        # Generate completion based on provider
        if provider == ModelProvider.OPENAI:
            # Import OpenAI async client
            try:
                from openai import AsyncOpenAI
            except ImportError:
                logger.warning("AsyncOpenAI not available, falling back to synchronous client")
                from openai import OpenAI as AsyncOpenAI
                
            client = AsyncOpenAI(api_key=self.api_keys[ModelProvider.OPENAI])
            response = await client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content
            
        elif provider == ModelProvider.ANTHROPIC:
            # For now, use sync client for Anthropic as their async API might differ
            client = self._create_anthropic_instance(config)
            response = client.messages.create(
                model=model_name,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
            
        elif provider == ModelProvider.COHERE:
            # For now, use sync client for Cohere as their async API might differ
            client = self._create_cohere_instance(config)
            response = client.generate(
                model=model_name,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature
            )
            return response.generations[0].text
            
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")
    
    def get_completion_with_template(
        self,
        template_name: str,
        template_vars: Optional[Dict[str, Any]] = None,
        task_name: Optional[str] = None,
        config_override: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Load a prompt template, fill it with variables, and generate a completion.
        
        Args:
            template_name: Name of the prompt template
            template_vars: Optional variables to fill in the template
            task_name: Optional name of the task
            config_override: Optional configuration override
            
        Returns:
            The generated completion text
        """
        # Load template
        template = self.load_prompt_template(template_name)
        
        # Fill template with variables
        if template_vars:
            # Simple string formatting for templates
            # In a real implementation, you might want to use a proper templating engine
            try:
                prompt = template.format(**template_vars)
            except KeyError as e:
                logger.error(f"Missing template variable: {e}")
                raise ValueError(f"Missing template variable: {e}")
        else:
            prompt = template
            
        # Generate completion
        return self.generate_completion(prompt, task_name, config_override)
    
    def track_usage(self, prompt: str, completion: str, model_name: str) -> Dict[str, Any]:
        """
        Track token usage and cost for an LLM interaction.
        
        Args:
            prompt: The input prompt
            completion: The generated completion
            model_name: The name of the model used
            
        Returns:
            Dictionary with usage information
        """
        # This is a simplified implementation
        # In a real system, you would use a tokenizer to count tokens accurately
        # and apply the correct pricing for the specific model
        
        # Rough estimation of tokens (1 token ≈ 4 chars for English text)
        prompt_tokens = len(prompt) // 4
        completion_tokens = len(completion) // 4
        total_tokens = prompt_tokens + completion_tokens
        
        # Very simplified cost calculation
        # Actual implementation would use the correct pricing for each model
        cost_per_1k_tokens = 0.002  # Example rate for gpt-4o-mini
        cost = (total_tokens / 1000) * cost_per_1k_tokens
        
        usage_info = {
            "model": model_name,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "estimated_cost_usd": cost
        }
        
        logger.debug(f"LLM usage: {json.dumps(usage_info)}")
        
        return usage_info

    @lru_cache(maxsize=32)
    def _load_prompt_template(self, template_name: str) -> str:
        """
        Load a prompt template from file.
        
        Args:
            template_name: Name of the template file (without extension)
            
        Returns:
            The prompt template as a string
            
        Raises:
            FileNotFoundError: If the template file doesn't exist
        """
        # Generate variations of the template name to try
        template_variations = [
            f"{template_name}.txt",                  # text_intent_classification.txt
            f"{template_name}_prompt.txt",           # text_intent_classification_prompt.txt
        ]
        
        # Try multiple paths with different template name variations
        possible_paths = []
        for variation in template_variations:
            possible_paths.extend([
                # Path from instance prompts_dir
                Path(self.prompts_dir) / variation,
                # Absolute path from current working directory
                Path.cwd() / "prompts" / variation,
                # Hard-coded absolute path
                Path("/Users/viprasingh/Developer/whatsapp-invoice-assistant/prompts") / variation,
            ])
        
        # Log all possible paths
        for i, path in enumerate(possible_paths):
            logger.debug(f"Possible prompt path {i+1}: {path} (exists: {path.exists()})")
        
        # Try each path
        errors = []
        for path in possible_paths:
            try:
                if path.exists():
                    with open(path, "r") as file:
                        template = file.read()
                        # Print a preview of the template to confirm it was loaded correctly
                        preview = template[:100] + "..." if len(template) > 100 else template
                        logger.debug(f"Successfully loaded prompt template from {path}")
                        logger.debug(f"Template preview: {preview}")
                        return template
            except Exception as e:
                error_msg = f"Error loading from {path}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        # If we got here, all paths failed
        error_summary = "\n".join(errors) if errors else "No errors reported, but no valid paths found."
        error_msg = f"Prompt template not found: {template_name}. Tried paths: {', '.join(str(p) for p in possible_paths)}. Errors: {error_summary}"
        logger.error(error_msg)
        
        # As a last resort, check if we can access the file system and list directory contents
        try:
            logger.debug(f"Listing contents of prompts directory {Path.cwd() / 'prompts'}:")
            for item in (Path.cwd() / "prompts").iterdir():
                logger.debug(f"  - {item.name} ({item.stat().st_size} bytes)")
        except Exception as e:
            logger.error(f"Error listing prompts directory: {str(e)}")
            
        raise FileNotFoundError(error_msg)
    
    async def classify_text_intent(self, input_text: str) -> str:
        """
        Classify the intent of a text input.
        
        Args:
            input_text: The text input to classify
            
        Returns:
            A JSON string containing the classified intent and confidence
        """
        try:
            # Load the intent classification prompt using prompt mappings
            prompt_template = self.load_prompt_template(
                get_prompt_for_agent(AgentType.TEXT_INTENT_CLASSIFIER)
            )
            
            # Combine the prompt with the input
            full_prompt = f"{prompt_template}\n\nINPUT:\n{input_text}\n\nOUTPUT:"
            
            # Call the LLM with a low temperature for more deterministic results
            response = await self.generate_completion(
                prompt=full_prompt,
                temperature=TemperatureSettings.CLASSIFICATION,
                max_tokens=TokenLimits.MAX_OUTPUT_TOKENS_SHORT
            )
            
            logger.debug(f"Intent classification response: {response}")
            return response
            
        except Exception as e:
            logger.error(f"Error in classify_text_intent: {str(e)}", exc_info=True)
            # Return a JSON string with UNKNOWN intent
            return json.dumps({
                "intent": "unknown",
                "confidence": 0.0,
                "explanation": f"Error: {str(e)}"
            })
    
    async def convert_text_to_sql(self, query_text: str, schema_info: str) -> str:
        """
        Convert natural language query to SQL.
        
        Args:
            query_text: The natural language query
            schema_info: Information about the database schema
            
        Returns:
            A JSON string containing the generated SQL and explanation
        """
        try:
            # Load the SQL conversion prompt using prompt mappings
            prompt_template = self.load_prompt_template(
                get_prompt_for_agent(AgentType.TEXT_TO_SQL_CONVERSION)
            )
            
            # Prepare the input data
            input_data = {
                "query": query_text,
                "schema": schema_info
            }
            
            # Combine the prompt with the input
            full_prompt = f"{prompt_template}\n\nINPUT:\n{json.dumps(input_data)}\n\nOUTPUT:"
            
            # Call the LLM with low temperature for more deterministic SQL generation
            response = await self.generate_completion(
                prompt=full_prompt,
                temperature=TemperatureSettings.SQL_GENERATION,
                max_tokens=TokenLimits.MAX_OUTPUT_TOKENS_MEDIUM
            )
            
            logger.debug(f"SQL conversion response: {response}")
            return response
            
        except Exception as e:
            logger.error(f"Error in convert_text_to_sql: {str(e)}", exc_info=True)
            # Return a JSON string with error information
            return json.dumps({
                "sql": "",
                "explanation": f"Error: {str(e)}",
                "status": "error"
            })
    
    async def extract_invoice_entities(self, text: str) -> str:
        """
        Extract invoice-related entities from text.
        
        Args:
            text: The text to extract entities from
            
        Returns:
            A JSON string containing the extracted entities
        """
        try:
            # Load the entity extraction prompt using prompt mappings
            prompt_template = self.load_prompt_template(
                get_prompt_for_agent(AgentType.INVOICE_ENTITY_EXTRACTION)
            )
            
            # Combine the prompt with the input
            full_prompt = f"{prompt_template}\n\nINPUT:\n{text}\n\nOUTPUT:"
            
            # Call the LLM with a moderate temperature for entity extraction
            response = await self.generate_completion(
                prompt=full_prompt,
                temperature=TemperatureSettings.ENTITY_EXTRACTION,
                max_tokens=TokenLimits.MAX_OUTPUT_TOKENS_MEDIUM
            )
            
            logger.debug(f"Entity extraction response: {response}")
            return response
            
        except Exception as e:
            logger.error(f"Error in extract_invoice_entities: {str(e)}", exc_info=True)
            # Return a JSON string with error information
            return json.dumps({
                "entities": {},
                "explanation": f"Error: {str(e)}",
                "status": "error"
            })
    
    async def validate_invoice_file(self, file_content: str) -> str:
        """
        Validate if a file contains a valid invoice.
        
        Args:
            file_content: The content of the file to validate
            
        Returns:
            A JSON string containing validation results
        """
        try:
            # Load the file validation prompt using prompt mappings
            prompt_template = self.load_prompt_template(
                get_prompt_for_agent(AgentType.FILE_VALIDATION)
            )
            
            # Combine the prompt with the input
            full_prompt = f"{prompt_template}\n\nINPUT:\n{file_content}\n\nOUTPUT:"
            
            # Call the LLM for file validation
            response = await self.generate_completion(
                prompt=full_prompt,
                temperature=TemperatureSettings.VALIDATION,
                max_tokens=TokenLimits.MAX_OUTPUT_TOKENS_SHORT
            )
            
            logger.debug(f"File validation response: {response}")
            return response
            
        except Exception as e:
            logger.error(f"Error in validate_invoice_file: {str(e)}", exc_info=True)
            # Return a JSON string with error information
            return json.dumps({
                "is_valid_invoice": False,
                "confidence_score": 0.0,
                "missing_elements": ["error occurred"],
                "reasons": f"Error during validation: {str(e)}"
            })
    
    async def extract_invoice_data(self, content: Union[str, Dict[str, Any]]) -> str:
        """
        Extract structured data from invoice file content. Supports both text and image content.
        
        Args:
            content: The content of the invoice file. Can be text or a dictionary with image data
                If a dictionary, it should contain 'type': 'image' and 'content': <base64_encoded_image>
            
        Returns:
            A JSON string containing the extracted invoice data
        """
        try:
            # Check if content is an image
            is_image = False
            base64_image = None
            
            if isinstance(content, dict) and content.get("type") == "image" and "content" in content:
                is_image = True
                base64_image = content["content"]
                dimensions = content.get("dimensions", "unknown")
                mime_type = content.get("mime_type", "image/jpeg")
                logger.info(f"Processing image for data extraction: {dimensions}, {mime_type}")
                
            # Load the appropriate data extraction prompt using prompt mappings
            if is_image:
                prompt_template = self.load_prompt_template(
                    get_prompt_for_agent(AgentType.INVOICE_IMAGE_DATA_EXTRACTION)
                )
            else:
                prompt_template = self.load_prompt_template(
                    get_prompt_for_agent(AgentType.INVOICE_DATA_EXTRACTION)
                )
                
            if is_image:
                # For image content, use GPT-4o-mini with vision capabilities
                try:
                    from openai import OpenAI
                    
                    client = OpenAI(api_key=self.api_keys[ModelProvider.OPENAI])
                    
                    # Create a message with the image content
                    messages = [
                        {
                            "role": "system",
                            "content": prompt_template
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Extract all invoice information from this image."
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{mime_type};base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ]
                    
                    # Call the model with vision capabilities
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",  # Use GPT-4o-mini for vision
                        messages=messages,
                        temperature=TemperatureSettings.DATA_EXTRACTION,
                        max_tokens=TokenLimits.MAX_OUTPUT_TOKENS_MEDIUM
                    )
                    
                    # Extract the response content
                    extracted_data = response.choices[0].message.content
                    logger.info("Successfully extracted data from image using GPT-4o-mini")
                    
                    return extracted_data
                    
                except ImportError as e:
                    logger.error(f"OpenAI package not installed for image processing: {str(e)}")
                    return json.dumps({
                        "vendor": {},
                        "transaction": {},
                        "items": [],
                        "financial": {},
                        "additional_info": {},
                        "confidence_score": 0.0,
                        "error": f"OpenAI package required for image processing: {str(e)}"
                    })
                    
                except Exception as e:
                    logger.error(f"Error in GPT-4o-mini image processing: {str(e)}")
                    # Return error as JSON string
                    return json.dumps({
                        "vendor": {},
                        "transaction": {},
                        "items": [],
                        "financial": {},
                        "additional_info": {},
                        "confidence_score": 0.0,
                        "error": f"Error processing image: {str(e)}"
                    })
                    
            else:
                # For text content, use the standard approach
                # Convert dict to string if necessary
                if isinstance(content, dict):
                    content = json.dumps(content)
                    
                # Combine the prompt with the input
                full_prompt = f"{prompt_template}\n\nINPUT:\n{content}\n\nOUTPUT:"
                
                # Call the LLM for data extraction
                response = await self.generate_completion(
                    prompt=full_prompt,
                    temperature=TemperatureSettings.DATA_EXTRACTION,
                    max_tokens=TokenLimits.MAX_OUTPUT_TOKENS_MEDIUM
                )
                
                logger.debug(f"Invoice data extraction response: {response}")
                return response
                
        except Exception as e:
            logger.error(f"Error in extract_invoice_data: {str(e)}", exc_info=True)
            # Return a JSON string with error information
            return json.dumps({
                "vendor": {},
                "transaction": {},
                "items": [],
                "financial": {},
                "additional_info": {},
                "confidence_score": 0.0,
                "error": f"Error during data extraction: {str(e)}"
            })
    
    async def format_invoice_data(self, invoice_data: Union[str, Dict[str, Any]]) -> str:
        """
        Format invoice data into a readable response.
        
        Args:
            invoice_data: Invoice data to format, either as JSON string or dict
            
        Returns:
            Formatted response string
        """
        logger.debug(f"Formatting invoice data: {type(invoice_data)}")
        
        # Parse invoice data if it's a string
        if isinstance(invoice_data, str):
            try:
                invoice_data = json.loads(invoice_data)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON data provided to format_invoice_data")
                return GENERAL_FALLBACKS["error"]
        
        try:
            # Convert complex objects to serializable form
            class CustomEncoder(json.JSONEncoder):
                def default(self, obj):
                    if isinstance(obj, datetime):
                        return obj.isoformat()
                    if isinstance(obj, Decimal):
                        return float(obj)
                    if isinstance(obj, UUID):
                        return str(obj)
                    return json.JSONEncoder.default(self, obj)
            
            # Convert to string for template insertion
            invoice_json = json.dumps(invoice_data, cls=CustomEncoder, ensure_ascii=False)
            
            # Load the response formatting prompt using prompt mappings
            template = self.load_prompt_template(
                get_prompt_for_agent(AgentType.RESPONSE_FORMATTING)
            )
            prompt = template.replace("{content_to_format}", invoice_json)
            prompt = prompt.replace("{format_type}", "invoice_data")
            
            # Generate formatted response
            formatted_response = await self.generate_completion(prompt)
            logger.debug("Invoice data formatting completed")
            
            if not formatted_response or formatted_response.strip() == "":
                logger.warning("Empty response from format_invoice_data")
                return get_invoice_processing_message("formatting_error")
                
            # Check if the response is properly formatted
            if not ("total amount" in formatted_response.lower() or "total:" in formatted_response.lower()):
                logger.warning("Response formatting lacks key invoice details")
                return get_invoice_processing_message("details_formatting_error")
                
            return formatted_response
            
        except Exception as e:
            logger.error(f"Error formatting invoice data: {str(e)}", exc_info=True)
            return GENERAL_FALLBACKS["error"]
    
    async def validate_response(self, 
                              response_content: str, 
                              response_type: str, 
                              context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Validate a generated response against quality standards.
        
        Args:
            response_content: The response content to validate
            response_type: The expected type of response (invoice_summary, error, etc.)
            context: Optional context information about the user's situation
            
        Returns:
            Dict containing validation results with is_valid flag and confidence
        """
        try:
            # Load the response validation prompt template using prompt mappings
            prompt_template = self.load_prompt_template(
                get_prompt_for_agent(AgentType.RESPONSE_VALIDATION)
            )
            
            # Create the validation input
            validation_input = {
                "response": response_content,
                "response_type": response_type,
                "context": context or {}
            }
            
            # Format the prompt with the validation input
            prompt = f"{prompt_template}\n\nInput:\n{json.dumps(validation_input, indent=2)}\n\nOutput:"
            
            # Generate the validation result
            logger.debug(f"Validating {response_type} response")
            validation_result = await self.generate_completion(
                prompt=prompt,
                temperature=TemperatureSettings.VALIDATION,
                max_tokens=TokenLimits.MAX_OUTPUT_TOKENS_SHORT
            )
            
            # Parse the validation result
            try:
                result = json.loads(validation_result)
                logger.debug(f"Response validation result: {result}")
                return result
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse validation result as JSON: {validation_result}")
                return {
                    "is_valid": False,
                    "confidence": 0.0,
                    "issues": ["Invalid validation response format"],
                    "fixed_response": None
                }
                
        except Exception as e:
            logger.error(f"Error in validate_response: {str(e)}", exc_info=True)
            return {
                "is_valid": False,
                "confidence": 0.0,
                "issues": [f"Error during validation: {str(e)}"],
                "fixed_response": None
            }
        
    async def text_to_sql(
        self,
        query: str,
        entity_info: Optional[Dict[str, Any]] = None,
        conversation_context: Optional[str] = None,
        query_context: Optional[str] = None
    ) -> str:
        """
        Convert natural language to SQL using a specialized prompt.
        
        Args:
            query: The natural language query to convert
            entity_info: Optional entity information for context, may include schema information
            conversation_context: Optional conversation history for context
            query_context: Optional query context to guide SQL generation
            
        Returns:
            The SQL query as a string
        """
        logger.info(f"Converting text to SQL: '{query}'")
        
        try:
            # Load the prompt template
            prompt_template = self.load_prompt_template("text_to_sql_conversion_prompt")
            
            # Prepare entity_info string
            entity_info_str = "No specific entity information provided."
            if entity_info and isinstance(entity_info, dict):
                # Extract database schema information if provided
                schema_info = entity_info.get("schema", "")
                user_id = entity_info.get("user_id", "")
                
                entity_info_parts = []
                if schema_info:
                    entity_info_parts.append(f"DATABASE SCHEMA:\n{schema_info}")
                if user_id:
                    entity_info_parts.append(f"USER ID: {user_id}")
                
                # Add any other entity information
                for k, v in entity_info.items():
                    if k not in ["schema", "user_id"]:
                        entity_info_parts.append(f"{k}: {v}")
                
                entity_info_str = "\n".join(entity_info_parts)
            
            # Prepare conversation_context string
            if not conversation_context:
                conversation_context = "No conversation history available."
            
            # Include query context or use default
            if not query_context:
                query_context = "Using semantic understanding to detect if this is a summary, product-specific, or time-based query."
            
            # Instead of format, use safer replacement
            prompt = prompt_template
            prompt = prompt.replace("{query}", query)
            prompt = prompt.replace("{entity_info}", entity_info_str)
            prompt = prompt.replace("{conversation_context}", conversation_context)
            prompt = prompt.replace("{query_context}", query_context)
            
            logger.debug(f"SQL generation prompt: {prompt[:100]}...")
            
            # Generate the SQL
            sql_result = await self.generate_completion(
                prompt=prompt,
                temperature=0.2,  # Lower temperature for more deterministic results
                max_tokens=500
            )
            
            # Get and return the result
            result = sql_result.strip()
            logger.info(f"SQL generation completed: {len(result)} chars")
            
            return result
        except Exception as e:
            logger.error(f"Error in text_to_sql: {str(e)}", exc_info=True)
            return f"Error generating SQL: {str(e)}"

    async def format_response(self, content: Dict[str, Any], format_type: str = "default") -> str:
        """
        Format a response using the appropriate template.
        
        Args:
            content: The content to format
            format_type: The type of format to use
            
        Returns:
            The formatted response
        """
        logger.debug(f"Formatting response of type: {format_type}")
        
        # Load the response formatting prompt template
        prompt_template = self.load_prompt_template("response_formatting_prompt")
        
        try:
            # Use custom encoder for handling datetime and Decimal objects
            class CustomEncoder(json.JSONEncoder):
                def default(self, obj):
                    if isinstance(obj, datetime):
                        return obj.isoformat()
                    if isinstance(obj, Decimal):
                        return float(obj)
                    return super().default(obj)
            
            # Create input data structure if not already in correct format
            if not isinstance(content, dict) or "type" not in content:
                input_data = {
                    "type": format_type,
                    "content": content
                }
            else:
                input_data = content
            
            # Format the prompt with the content
            prompt = f"{prompt_template}\n\nInput:\n{json.dumps(input_data, indent=2, cls=CustomEncoder)}\n\nOutput:"
            
            # Generate the completion
            logger.debug("Sending format prompt to LLM")
            formatted_response = await self.generate_completion(
                prompt,
                task_name="response_formatting"
            )
            
            logger.debug(f"Formatted response (first 100 chars): {formatted_response[:100]}...")
            return formatted_response
            
        except Exception as e:
            logger.error(f"Error in format_response: {str(e)}", exc_info=True)
            logger.warning(f"Error serializing input data to JSON: {str(e)}")
            
            # Fallback: Simple formatting for when JSON serialization fails
            try:
                # Create a simple response based on the query result content
                if isinstance(content, dict):
                    query_type = content.get("type", format_type)
                    if query_type == "query_result":
                        query_content = content.get("content", {})
                        query = query_content.get("query", "your query")
                        results = query_content.get("results", [])
                        count = len(results)
                        
                        if count > 0:
                            return f"I found {count} results for {query}. Here's a summary of what I found."
                        else:
                            return f"I couldn't find any results for {query}. Please try a different query."
                    else:
                        return f"I found some information related to your request, but encountered an issue formatting it."
                else:
                    return "I found some information related to your request, but encountered an issue with the formatting."
            except Exception as e2:
                logger.error(f"Error in fallback formatting: {str(e2)}", exc_info=True)
                return "I found some information related to your request, but encountered an issue with the formatting."
    
    async def generate_sql_from_query(
        self, 
        query: str, 
        db_schema: str,
        user_id: str,
        conversation_history: List[Dict[str, Any]] = None,
        is_summary_query: bool = False,
        is_semantic_search: bool = False
    ) -> str:
        """
        Generate SQL from a natural language query.
        
        Args:
            query: Natural language query
            db_schema: Database schema information
            user_id: User ID for filtering
            conversation_history: Optional list of conversation messages for context
            is_summary_query: Flag indicating if this is a query requesting summarized data 
            is_semantic_search: Flag indicating if semantic search should be used
        
        Returns:
            Generated SQL query
        """
        # Debug logging
        logger.debug(f"Generating SQL for query: '{query}'")
        logger.debug(f"Using semantic search: {is_semantic_search}")
        
        # Format conversation history
        formatted_history = ""
        if conversation_history:
            # Take the last 5 messages as context
            last_messages = conversation_history[-5:]
            for msg in last_messages:
                role = msg.get("role", "unknown").capitalize()
                content = msg.get("content", "")
                formatted_history += f"{role}: {content}\n"
        
        # Determine query context
        if is_summary_query:
            # Load summary query context template
            query_context = self._load_query_context_template("summary_query_context")
        elif is_semantic_search:
            # Load semantic search context template
            query_context = self._load_query_context_template("semantic_search_context")
            
            # Replace the VECTOR_SIMILARITY_THRESHOLD placeholder with actual value from constants
            from constants.vector_search_configs import VECTOR_SIMILARITY_THRESHOLD
            query_context = query_context.replace("[:VECTOR_SIMILARITY_THRESHOLD]", str(VECTOR_SIMILARITY_THRESHOLD))
            logger.info(f"Using vector similarity threshold: {VECTOR_SIMILARITY_THRESHOLD}")
        else:
            query_context = ""
        
        # Build entity info
        entity_info = {
            "db_schema": db_schema,
            "user_id": user_id,
            "is_summary_query": is_summary_query,
            "is_semantic_search": is_semantic_search
        }
        
        # Append original query as comment (aids in embedding generation)
        query_with_comment = f"{query}\n-- Original query for embedding: {query}"
        
        # Call text_to_sql function
        result = await self.text_to_sql(
            query=query_with_comment,
            entity_info=entity_info,
            conversation_context=formatted_history,
            query_context=query_context
        )
        
        return result 

    def _load_query_context_template(self, template_name: str) -> str:
        """
        Load a query context template from the prompts directory.
        
        Args:
            template_name: Name of the template to load
            
        Returns:
            The loaded template or an empty string if not found
        """
        try:
            template_path = Path(__file__).parent.parent / "prompts" / "sql_context_templates" / f"{template_name}.txt"
            
            if template_path.exists():
                with open(template_path, "r") as f:
                    template = f.read()
                logger.debug(f"Loaded {template_name} from prompts/sql_context_templates directory")
                return template
            else:
                logger.warning(f"{template_name}.txt not found, using empty context")
                return ""
        except Exception as e:
            logger.error(f"Error loading query context template {template_name}: {str(e)}")
            logger.warning("Using empty query context as fallback")
            return "" 