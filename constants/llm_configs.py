"""
Configuration constants for LLM settings and models.

This module defines the configuration constants for LLM settings,
including model names, providers, temperature settings, and token limits.
"""
from enum import Enum, auto

# LLM Providers
class ModelProvider(str, Enum):
    """Enum for supported LLM providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    COHERE = "cohere"

# Model Names
class Models:
    """Available model names by provider."""
    # OpenAI models
    GPT4 = "gpt-4"
    GPT4_TURBO = "gpt-4-turbo-preview"
    GPT4O_MINI = "gpt-4o-mini"
    GPT35_TURBO = "gpt-3.5-turbo"
    
    # Anthropic models
    CLAUDE_3_OPUS = "claude-3-opus-20240229"
    CLAUDE_3_SONNET = "claude-3-sonnet-20240229"
    CLAUDE_3_HAIKU = "claude-3-haiku-20240307"
    
    # Cohere models
    COHERE_COMMAND = "command"
    COHERE_COMMAND_LIGHT = "command-light"
    
    # Default model
    DEFAULT = GPT4O_MINI

# Temperature Settings
class TemperatureSettings:
    """Temperature settings for different tasks."""
    DEFAULT = 0.7
    CLASSIFICATION = 0.3  # Lower temperature for more deterministic classifications
    SQL_GENERATION = 0.1  # Very low temperature for deterministic SQL
    ENTITY_EXTRACTION = 0.4  # Low-medium temperature for entity extraction
    DATA_EXTRACTION = 0.2  # Low temperature for extracting structured data
    VALIDATION = 0.0  # Zero temperature for validation tasks
    RESPONSE_FORMATTING = 0.6  # Medium temperature for creative formatting

# Token Limits
class TokenLimits:
    """Token limits for different operations."""
    DEFAULT_MAX_OUTPUT_TOKENS = 1500
    MAX_OUTPUT_TOKENS_SHORT = 500   # For short responses like classifications
    MAX_OUTPUT_TOKENS_MEDIUM = 1500  # For medium-length responses like SQL or data extraction
    MAX_OUTPUT_TOKENS_LONG = 4000   # For long responses like comprehensive summaries

# LLM Provider enum (backward compatibility)
class LLMProvider(str, Enum):
    """Enum for supported LLM providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    COHERE = "cohere"

# Model Name enum (backward compatibility)
class ModelName(str, Enum):
    """Enum for available model names."""
    GPT4 = "gpt-4"
    GPT4_TURBO = "gpt-4-turbo-preview"
    GPT4O_MINI = "gpt-4o-mini"
    GPT35_TURBO = "gpt-3.5-turbo"
    CLAUDE_3_OPUS = "claude-3-opus-20240229"
    CLAUDE_3_SONNET = "claude-3-sonnet-20240229"
    CLAUDE_3_HAIKU = "claude-3-haiku-20240307"
    COHERE_COMMAND = "command"
    COHERE_COMMAND_LIGHT = "command-light"

# Default LLM configuration
DEFAULT_LLM_CONFIG = {
    "provider": ModelProvider.OPENAI,
    "model": Models.GPT4O_MINI,
    "temperature": TemperatureSettings.DEFAULT,
    "max_output_tokens": TokenLimits.DEFAULT_MAX_OUTPUT_TOKENS
}

# Task-specific LLM configurations
TASK_LLM_CONFIGS = {
    "classification": {
        "temperature": TemperatureSettings.CLASSIFICATION,
        "max_output_tokens": TokenLimits.MAX_OUTPUT_TOKENS_SHORT
    },
    "sql_generation": {
        "temperature": TemperatureSettings.SQL_GENERATION,
        "max_output_tokens": TokenLimits.MAX_OUTPUT_TOKENS_MEDIUM
    },
    "entity_extraction": {
        "temperature": TemperatureSettings.ENTITY_EXTRACTION,
        "max_output_tokens": TokenLimits.MAX_OUTPUT_TOKENS_MEDIUM
    },
    "data_extraction": {
        "temperature": TemperatureSettings.DATA_EXTRACTION,
        "max_output_tokens": TokenLimits.MAX_OUTPUT_TOKENS_MEDIUM
    },
    "validation": {
        "temperature": TemperatureSettings.VALIDATION,
        "max_output_tokens": TokenLimits.MAX_OUTPUT_TOKENS_SHORT
    },
    "response_formatting": {
        "temperature": TemperatureSettings.RESPONSE_FORMATTING,
        "max_output_tokens": TokenLimits.MAX_OUTPUT_TOKENS_MEDIUM
    },
    "response_validation": {
        "temperature": TemperatureSettings.VALIDATION,
        "max_output_tokens": TokenLimits.MAX_OUTPUT_TOKENS_SHORT
    }
} 