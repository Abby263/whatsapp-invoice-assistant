"""
Configuration settings for Large Language Models used in the application.

This module contains settings and constants for different LLM configurations
used throughout the application.
"""
from enum import Enum, auto

class ModelProvider(Enum):
    """Supported LLM providers."""
    OPENAI = auto()
    ANTHROPIC = auto()
    COHERE = auto()

class Models:
    """Available models from different providers."""
    # OpenAI models
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_4O = "gpt-4o"
    GPT_4_TURBO = "gpt-4-turbo"
    
    # Anthropic models
    CLAUDE_3_HAIKU = "claude-3-haiku-20240307"
    CLAUDE_3_SONNET = "claude-3-sonnet-20240229"
    CLAUDE_3_OPUS = "claude-3-opus-20240229"
    
    # Cohere models
    COHERE_COMMAND = "command"
    COHERE_COMMAND_LIGHT = "command-light"
    COHERE_COMMAND_R = "command-r"
    
    # Default model to use
    DEFAULT = GPT_4O_MINI

class TemperatureSettings:
    """Temperature settings for different tasks."""
    # More deterministic tasks
    CLASSIFICATION = 0.0
    SQL_GENERATION = 0.0
    ENTITY_EXTRACTION = 0.1
    DATA_EXTRACTION = 0.1
    VALIDATION = 0.1
    
    # More creative tasks
    RESPONSE_FORMATTING = 0.3
    CONVERSATION = 0.5
    
    # Default temperature
    DEFAULT = 0.1

class TokenLimits:
    """Token limits for different models and contexts."""
    # Input tokens (prompt)
    MAX_INPUT_TOKENS_SHORT = 4000
    MAX_INPUT_TOKENS_MEDIUM = 8000
    MAX_INPUT_TOKENS_LONG = 16000
    
    # Output tokens (completion)
    MAX_OUTPUT_TOKENS_SHORT = 1000
    MAX_OUTPUT_TOKENS_MEDIUM = 2000
    MAX_OUTPUT_TOKENS_LONG = 4000
    
    # Default limits
    DEFAULT_MAX_INPUT_TOKENS = MAX_INPUT_TOKENS_MEDIUM
    DEFAULT_MAX_OUTPUT_TOKENS = MAX_OUTPUT_TOKENS_MEDIUM

class PromptTemplateKeys:
    """Keys for accessing prompt templates."""
    TEXT_INTENT_CLASSIFICATION = "text_intent_classification"
    TEXT_TO_SQL_CONVERSION = "text_to_sql_conversion"
    INVOICE_ENTITY_EXTRACTION = "invoice_entity_extraction"
    FILE_VALIDATION = "file_validation"
    INVOICE_DATA_EXTRACTION = "invoice_data_extraction"
    RESPONSE_FORMATTING = "response_formatting"

# Default LLM configuration
DEFAULT_LLM_CONFIG = {
    "provider": ModelProvider.OPENAI,
    "model": Models.DEFAULT,
    "temperature": TemperatureSettings.DEFAULT,
    "max_input_tokens": TokenLimits.DEFAULT_MAX_INPUT_TOKENS,
    "max_output_tokens": TokenLimits.DEFAULT_MAX_OUTPUT_TOKENS,
}

# Task-specific LLM configurations
TASK_LLM_CONFIGS = {
    "intent_classification": {
        "model": Models.GPT_4O_MINI,
        "temperature": TemperatureSettings.CLASSIFICATION,
        "max_output_tokens": 10,  # Very short output for classification
    },
    "sql_generation": {
        "model": Models.GPT_4O_MINI,
        "temperature": TemperatureSettings.SQL_GENERATION,
        "max_output_tokens": TokenLimits.MAX_OUTPUT_TOKENS_MEDIUM,
    },
    "entity_extraction": {
        "model": Models.GPT_4O_MINI,
        "temperature": TemperatureSettings.ENTITY_EXTRACTION,
        "max_output_tokens": TokenLimits.MAX_OUTPUT_TOKENS_MEDIUM,
    },
    "data_extraction": {
        "model": Models.GPT_4O,  # Using more powerful model for OCR extraction
        "temperature": TemperatureSettings.DATA_EXTRACTION,
        "max_output_tokens": TokenLimits.MAX_OUTPUT_TOKENS_MEDIUM,
    },
    "file_validation": {
        "model": Models.GPT_4O_MINI,
        "temperature": TemperatureSettings.VALIDATION,
        "max_output_tokens": TokenLimits.MAX_OUTPUT_TOKENS_SHORT,
    },
    "response_formatting": {
        "model": Models.GPT_4O_MINI,
        "temperature": TemperatureSettings.RESPONSE_FORMATTING,
        "max_output_tokens": TokenLimits.MAX_OUTPUT_TOKENS_MEDIUM,
    },
} 