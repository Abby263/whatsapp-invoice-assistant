"""
LangGraph nodes for the WhatsApp Invoice Assistant workflow.

This module defines the individual nodes (steps) in the LangGraph workflow.
Each node represents a specific agent or action in the workflow.
"""

import logging
import os
from typing import Dict, List, Tuple, Any, Optional, TypedDict

from agents.text_intent_classifier import TextIntentClassifierAgent
from agents.file_validator import FileValidatorAgent
from agents.text_to_sql_conversion_agent import TextToSQLConversionAgent
from agents.invoice_entity_extraction_agent import InvoiceEntityExtractionAgent
from agents.data_extractor import DataExtractorAgent
from agents.response_formatter import ResponseFormatterAgent
from utils.input_type_router import InputTypeRouter
from services.llm_factory import LLMFactory
from langchain_app.state import WorkflowState, InputType, IntentType, ValidationResult, AgentResponse

logger = logging.getLogger(__name__)


def input_classifier(state: WorkflowState) -> WorkflowState:
    """
    Classifies the type of input (text or file).
    
    Args:
        state: The current workflow state
        
    Returns:
        Updated workflow state with input_type set
    """
    logger.info("Classifying input type")
    
    if not state.user_input:
        logger.error("No user input available for classification")
        state.errors.append("No user input available for classification")
        return state
    
    # Create an input router
    router = InputTypeRouter()
    
    # Determine input type
    if state.user_input.content_type != InputType.TEXT:
        # If content type is already set to something other than TEXT, use that
        state.input_type = state.user_input.content_type
    else:
        # For text content, check if it's a text message
        if isinstance(state.user_input.content, str):
            state.input_type = InputType.TEXT
        elif state.user_input.file_path:
            # If there's a file path, determine type from file extension
            file_ext = os.path.splitext(state.user_input.file_path)[1].lower()
            state.input_type = router.detect_file_type_from_extension(file_ext)
    
    logger.info(f"Input classified as: {state.input_type}")
    return state


def text_intent_classifier(state: WorkflowState) -> WorkflowState:
    """
    Classifies the intent of text input.
    
    Args:
        state: The current workflow state
        
    Returns:
        Updated workflow state with intent classification
    """
    logger.info("Classifying text intent")
    
    if state.input_type != InputType.TEXT:
        logger.info(f"Skipping text intent classification for non-text input: {state.input_type}")
        return state
    
    if not state.user_input or not isinstance(state.user_input.content, str):
        logger.error("No text content available for intent classification")
        state.errors.append("No text content available for intent classification")
        return state
    
    try:
        # Initialize the text intent classifier agent
        llm_factory = LLMFactory()
        agent = TextIntentClassifierAgent(llm_factory=llm_factory)
        
        # Get conversation history for context
        conversation_history = state.conversation_history.messages
        
        # Process the input (run synchronously)
        # We can't use await in a synchronous function, so we need to run the agent synchronously
        result = agent.process_sync({
            "content": state.user_input.content,
            "conversation_history": conversation_history
        })
        
        # Update the state with the classification result
        if result:
            try:
                # First, check for direct 'intent' key in dictionary (our new format)
                if isinstance(result, dict) and "intent" in result:
                    # This is for our new format where we explicitly set intent
                    intent_value = result["intent"]
                    try:
                        # Check if it's already an enum
                        if hasattr(intent_value, "value"):
                            state.intent = intent_value
                        else:
                            # Convert string to enum
                            intent_str = str(intent_value).upper()
                            state.intent = getattr(IntentType, intent_str, IntentType.UNKNOWN)
                    except (AttributeError, ValueError) as e:
                        logger.warning(f"Error converting intent to enum: {e}")
                        state.intent = IntentType.UNKNOWN
                # Fall back to old format with content
                elif isinstance(result, dict) and "content" in result:
                    intent_str = str(result["content"]).upper()
                    state.intent = getattr(IntentType, intent_str, IntentType.UNKNOWN)
                # Handle string result
                elif isinstance(result, str):
                    intent_str = result.upper()
                    state.intent = getattr(IntentType, intent_str, IntentType.UNKNOWN)
                # If all else fails, assume it's an unrecognized format
                else:
                    logger.warning(f"Intent classification returned unrecognized result structure: {type(result)}")
                    # If it has attributes that make it look like the result of our classifier,
                    # try to extract a useful value
                    for key in ["intent", "value", "type", "content", "result"]:
                        if isinstance(result, dict) and key in result:
                            intent_value = result[key]
                            try:
                                intent_str = str(intent_value).upper()
                                state.intent = getattr(IntentType, intent_str, IntentType.UNKNOWN)
                                logger.info(f"Extracted intent from key {key}: {state.intent}")
                                break
                            except (AttributeError, ValueError):
                                continue
                    else:
                        # Nothing worked, use UNKNOWN
                        state.intent = IntentType.UNKNOWN
                
                logger.info(f"Text intent classified as: {state.intent}")
            except Exception as e:
                logger.exception(f"Error processing intent classification result: {e}")
                state.intent = IntentType.UNKNOWN
        else:
            logger.warning("Intent classification returned no result")
            state.intent = IntentType.UNKNOWN
            
    except Exception as e:
        logger.exception(f"Error during text intent classification: {str(e)}")
        state.errors.append(f"Error during text intent classification: {str(e)}")
        state.intent = IntentType.UNKNOWN
        
    return state


def file_validator(state: WorkflowState) -> WorkflowState:
    """
    Validates if a file is a valid invoice.
    
    Args:
        state: The current workflow state
        
    Returns:
        Updated workflow state with file validation result
    """
    logger.info("Validating file")
    
    # Skip if input is text
    if state.input_type == InputType.TEXT:
        logger.info("Skipping file validation for text input")
        return state
    
    if not state.user_input or not state.user_input.file_path:
        logger.error("No file available for validation")
        state.errors.append("No file available for validation")
        return state
    
    try:
        # Initialize the file validator agent
        llm_factory = LLMFactory()
        agent = FileValidatorAgent(llm_factory=llm_factory)
        
        # Process the input
        result = agent.process({
            "file_path": state.user_input.file_path,
            "file_type": state.input_type
        })
        
        # Update the state with the validation result
        if result and "is_valid" in result:
            validation_result = ValidationResult(
                is_valid=result["is_valid"],
                confidence=result.get("confidence", 0.0),
                reason=result.get("reason")
            )
            state.file_validation = validation_result
            logger.info(f"File validation result: {validation_result.is_valid} (confidence: {validation_result.confidence})")
        else:
            logger.warning("File validation returned no result")
            state.file_validation = ValidationResult(is_valid=False, confidence=0.0, reason="Validation failed")
            
    except Exception as e:
        logger.exception(f"Error during file validation: {str(e)}")
        state.errors.append(f"Error during file validation: {str(e)}")
        state.file_validation = ValidationResult(is_valid=False, confidence=0.0, reason=f"Error: {str(e)}")
        
    return state


def invoice_entity_extractor(state: WorkflowState) -> WorkflowState:
    """
    Extracts invoice entities from text input.
    
    Args:
        state: The current workflow state
        
    Returns:
        Updated workflow state with extracted entities
    """
    logger.info("Extracting invoice entities from text")
    
    # Only process if input is text and intent is INVOICE_CREATOR
    if state.input_type != InputType.TEXT or state.intent != IntentType.INVOICE_CREATOR:
        logger.info(f"Skipping entity extraction for input type: {state.input_type}, intent: {state.intent}")
        return state
    
    if not state.user_input or not isinstance(state.user_input.content, str):
        logger.error("No text content available for entity extraction")
        state.errors.append("No text content available for entity extraction")
        return state
    
    try:
        # Initialize the entity extraction agent
        llm_factory = LLMFactory()
        agent = InvoiceEntityExtractionAgent(llm_factory=llm_factory)
        
        # Process the input
        result = agent.process({
            "text": state.user_input.content,
            "conversation_history": state.conversation_history.messages
        })
        
        # Update the state with the extracted entities
        if result and isinstance(result, dict):
            state.extracted_entities = result
            logger.info(f"Extracted entities: {state.extracted_entities}")
        else:
            logger.warning("Entity extraction returned no result")
            
    except Exception as e:
        logger.exception(f"Error during entity extraction: {str(e)}")
        state.errors.append(f"Error during entity extraction: {str(e)}")
        
    return state


def data_extractor(state: WorkflowState) -> WorkflowState:
    """
    Extracts data from invoice files.
    
    Args:
        state: The current workflow state
        
    Returns:
        Updated workflow state with extracted invoice data
    """
    logger.info("Extracting data from invoice file")
    
    # Skip if input is text or file validation failed
    if state.input_type == InputType.TEXT:
        logger.info("Skipping data extraction for text input")
        return state
    
    if state.file_validation and not state.file_validation.is_valid:
        logger.info("Skipping data extraction for invalid file")
        return state
    
    if not state.user_input or not state.user_input.file_path:
        logger.error("No file available for data extraction")
        state.errors.append("No file available for data extraction")
        return state
    
    try:
        # Initialize the data extractor agent
        llm_factory = LLMFactory()
        agent = DataExtractorAgent(llm_factory=llm_factory)
        
        # Process the input
        result = agent.process({
            "file_path": state.user_input.file_path,
            "file_type": state.input_type
        })
        
        # Update the state with the extracted data
        if result and isinstance(result, dict):
            state.extracted_invoice_data = result
            logger.info(f"Extracted invoice data: {state.extracted_invoice_data}")
        else:
            logger.warning("Data extraction returned no result")
            
    except Exception as e:
        logger.exception(f"Error during data extraction: {str(e)}")
        state.errors.append(f"Error during data extraction: {str(e)}")
        
    return state


def sql_query_generator(state: WorkflowState) -> WorkflowState:
    """
    Generates SQL queries from natural language.
    
    Args:
        state: The current workflow state
        
    Returns:
        Updated workflow state with SQL query
    """
    logger.info("Generating SQL query")
    
    # Only process if input is text and intent is INVOICE_QUERY
    if state.input_type != InputType.TEXT or state.intent != IntentType.INVOICE_QUERY:
        logger.info(f"Skipping SQL generation for input type: {state.input_type}, intent: {state.intent}")
        return state
    
    if not state.user_input or not isinstance(state.user_input.content, str):
        logger.error("No text content available for SQL generation")
        state.errors.append("No text content available for SQL generation")
        return state
    
    try:
        # Initialize the SQL conversion agent
        llm_factory = LLMFactory()
        agent = TextToSQLConversionAgent(llm_factory=llm_factory)
        
        # Process the input
        result = agent.process({
            "text": state.user_input.content,
            "conversation_history": state.conversation_history.messages
        })
        
        # Update the state with the generated SQL
        if result and "sql_query" in result:
            state.query_data = result
            logger.info(f"Generated SQL query: {state.query_data.sql_query}")
        else:
            logger.warning("SQL generation returned no result")
            
    except Exception as e:
        logger.exception(f"Error during SQL generation: {str(e)}")
        state.errors.append(f"Error during SQL generation: {str(e)}")
        
    return state


def response_formatter(state: WorkflowState) -> WorkflowState:
    """
    Formats the final response based on workflow results.
    
    Args:
        state: The current workflow state
        
    Returns:
        Updated workflow state with formatted response
    """
    logger.info("Formatting response")
    
    try:
        # Initialize the response formatter agent
        llm_factory = LLMFactory()
        agent = ResponseFormatterAgent(llm_factory=llm_factory)
        
        # Create the input for the formatter
        formatter_input = {
            "content": "Format response for user",
            "intent": state.intent.value if state.intent else IntentType.UNKNOWN.value,
            "input_type": state.input_type.value if state.input_type else InputType.UNKNOWN.value,
            "conversation_history": state.conversation_history.messages,
            "errors": state.errors
        }
        
        # Add extracted entities if available
        if state.extracted_entities:
            formatter_input["entities"] = state.extracted_entities
            
        # Add file validation result if available
        if state.file_validation:
            formatter_input["file_validation"] = {
                "is_valid": state.file_validation.is_valid,
                "reason": state.file_validation.reason
            }
            
        # Add extracted data if available
        if state.extracted_invoice_data:
            formatter_input["invoice_data"] = state.extracted_invoice_data
            
        # Add query result if available
        if state.query_data:
            formatter_input["query_result"] = state.query_data
            
        # Process the input (run synchronously)
        result = agent.process_sync(formatter_input)
        
        # Update the state with the formatted response
        if result:
            try:
                # Extract content based on result structure
                if isinstance(result, str):
                    # Handle string result
                    content = result
                    metadata = {}
                    confidence = 1.0
                elif isinstance(result, dict):
                    # Explicitly check for content key (our preferred format)
                    if "content" in result:
                        content = result["content"]
                        metadata = result.get("metadata", {})
                        confidence = result.get("confidence", 1.0)
                    else:
                        # Try to extract content from other possible keys
                        content_keys = ["response", "message", "result", "text", "answer"]
                        for key in content_keys:
                            if key in result:
                                content = result[key]
                                break
                        else:
                            # If no recognized keys found, convert the entire result to a string
                            content = str(result)
                            
                        # Extract any metadata if present
                        if "metadata" in result:
                            metadata = result["metadata"]
                        else:
                            # Use remaining fields as metadata
                            metadata = {k: v for k, v in result.items() 
                                      if k not in ["content", "confidence", "status", "error"] + content_keys}
                        
                        # Extract confidence if present
                        confidence = result.get("confidence", 1.0)
                else:
                    # Unknown result type, convert to string
                    content = str(result)
                    metadata = {}
                    confidence = 0.7
                
                # Ensure content is a string
                if not isinstance(content, str):
                    content = str(content)
                
                state.current_response = AgentResponse(
                    content=content,
                    metadata=metadata,
                    confidence=confidence
                )
                logger.info(f"Response formatted: {content[:50]}...")
            except Exception as e:
                logger.exception(f"Error processing response formatter result: {e}")
                state.current_response = AgentResponse(
                    content="I apologize, but I encountered an error processing the response.",
                    metadata={"error": str(e)},
                    confidence=0.0
                )
        else:
            logger.warning("Response formatting returned no result")
            state.current_response = AgentResponse(
                content="I apologize, but I couldn't generate a proper response at this time.",
                metadata={},
                confidence=0.0
            )
            
    except Exception as e:
        logger.exception(f"Error during response formatting: {str(e)}")
        state.errors.append(f"Error during response formatting: {str(e)}")
        state.current_response = AgentResponse(
            content=f"I apologize, but an error occurred while formatting the response: {str(e)}",
            metadata={"error": str(e)},
            confidence=0.0
        )
        
    return state 