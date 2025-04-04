"""
LLM Factory for creating and managing LLM instances.

This module provides a factory class for creating and managing LLM instances
with different configurations and capabilities.
"""
import os
import json
import logging
from typing import Dict, Any, Optional, List, Union
from pathlib import Path

from utils.config import config
from constants.llm_configs import (
    ModelProvider, 
    Models, 
    TemperatureSettings,
    TokenLimits,
    PromptTemplateKeys,
    DEFAULT_LLM_CONFIG,
    TASK_LLM_CONFIGS
)

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
            
        # Load API keys from config
        self.api_keys = {
            ModelProvider.OPENAI: config.get("openai", "api_key", default=os.environ.get("OPENAI_API_KEY")),
            ModelProvider.ANTHROPIC: config.get("anthropic", "api_key", default=os.environ.get("ANTHROPIC_API_KEY")),
            ModelProvider.COHERE: config.get("cohere", "api_key", default=os.environ.get("COHERE_API_KEY")),
        }
        
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
        
        # Determine file path
        file_name = f"{prompt_name}.txt"
        if not file_name.endswith(".txt"):
            file_name = f"{file_name}.txt"
            
        file_path = self.prompts_dir / file_name
        
        # Load from file
        try:
            with open(file_path, "r") as f:
                template = f.read()
            
            # Cache the template
            self.prompt_cache[prompt_name] = template
            return template
        except FileNotFoundError:
            logger.error(f"Prompt template file not found: {file_path}")
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