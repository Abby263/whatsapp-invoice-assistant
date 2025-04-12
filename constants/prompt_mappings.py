"""
Prompt template mappings for the WhatsApp Invoice Assistant.

This module defines mappings between agent types and the prompt templates they use,
providing a centralized place to manage which prompt is used by which component.
"""
from enum import Enum, auto

class AgentType(str, Enum):
    """Enum for agent types in the system."""
    TEXT_INTENT_CLASSIFIER = "text_intent_classifier"
    TEXT_TO_SQL_CONVERSION = "text_to_sql_conversion"
    INVOICE_ENTITY_EXTRACTION = "invoice_entity_extraction"
    FILE_VALIDATION = "file_validation"
    INVOICE_DATA_EXTRACTION = "invoice_data_extraction"
    INVOICE_IMAGE_DATA_EXTRACTION = "invoice_image_data_extraction"
    RESPONSE_FORMATTING = "response_formatting"
    RESPONSE_VALIDATION = "response_validation"
    DATABASE_STORAGE = "database_storage"

# Mapping of agent types to prompt template names
# This centralizes which prompt template each agent uses
AGENT_PROMPT_MAPPINGS = {
    # Text processing agents
    AgentType.TEXT_INTENT_CLASSIFIER: "text_intent_classification_prompt",
    AgentType.TEXT_TO_SQL_CONVERSION: "text_to_sql_conversion_prompt",
    AgentType.INVOICE_ENTITY_EXTRACTION: "invoice_entity_extraction_prompt",
    
    # File processing agents
    AgentType.FILE_VALIDATION: "file_validation_prompt",
    AgentType.INVOICE_DATA_EXTRACTION: "invoice_data_extraction_prompt",
    AgentType.INVOICE_IMAGE_DATA_EXTRACTION: "invoice_image_data_extraction_prompt",
    
    # Response handling agents
    AgentType.RESPONSE_FORMATTING: "response_formatting_prompt",
    AgentType.RESPONSE_VALIDATION: "response_validation_prompt",
    
    # Storage agents
    AgentType.DATABASE_STORAGE: "database_storage_prompt"
}

# Optional mapping for system prompts (when separated from main prompts)
AGENT_SYSTEM_PROMPT_MAPPINGS = {
    AgentType.TEXT_TO_SQL_CONVERSION: "text_to_sql_system_prompt"
}

# Function to get the prompt template name for a given agent
def get_prompt_for_agent(agent_type: str) -> str:
    """
    Get the prompt template name for a given agent type.
    
    Args:
        agent_type: The type of agent
        
    Returns:
        The prompt template name to use
        
    Raises:
        KeyError: If the agent type is not recognized
    """
    if agent_type not in AGENT_PROMPT_MAPPINGS:
        raise KeyError(f"Unknown agent type: {agent_type}")
    
    return AGENT_PROMPT_MAPPINGS[agent_type]

# Function to get the system prompt template name for a given agent (if applicable)
def get_system_prompt_for_agent(agent_type: str) -> str:
    """
    Get the system prompt template name for a given agent type.
    
    Args:
        agent_type: The type of agent
        
    Returns:
        The system prompt template name or None if not applicable
        
    Raises:
        KeyError: If the agent type is not recognized
    """
    if agent_type not in AGENT_SYSTEM_PROMPT_MAPPINGS:
        return None
    
    return AGENT_SYSTEM_PROMPT_MAPPINGS[agent_type] 