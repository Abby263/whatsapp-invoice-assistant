"""
Text Processing Workflow for WhatsApp Invoice Assistant.

This module implements the core text processing workflow that classifies user
text input and routes to the appropriate specialized workflow.
"""

import logging
from typing import Dict, Any, Optional, List, Union
from uuid import UUID

from agents.text_intent_classifier import TextIntentClassifierAgent
from services.llm_factory import LLMFactory
from langchain_app.state import IntentType, UserInput
from langchain_app.general_response_workflow import process_general_response, process_greeting
from langchain_app.invoice_query_workflow import process_invoice_query
from langchain_app.invoice_creator_workflow import process_invoice_creation

logger = logging.getLogger(__name__)


async def process_text_message(
    text_content: str,
    user_id: Optional[Union[str, UUID]] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Process a text message by classifying intent and routing to the appropriate workflow.
    
    Args:
        text_content: The text content to process
        user_id: Optional user ID for personalization
        conversation_history: Optional conversation history for context
        
    Returns:
        Dict containing the response content, metadata, and confidence
    """
    logger.info(f"=== TEXT PROCESSING WORKFLOW STARTED ===")
    logger.info(f"Processing text message: '{text_content}'")
    logger.info(f"User ID: {user_id}")
    
    # Ensure conversation_history is always a list
    if conversation_history is None:
        conversation_history = []
    
    logger.info(f"Conversation history length: {len(conversation_history)}")
    
    # Log conversation history for debugging
    if conversation_history:
        logger.debug("Conversation history:")
        for i, msg in enumerate(conversation_history):
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            logger.debug(f"  [{i}] {role}: {content[:50]}...")
    
    # Step 1: Classify the user's intent
    logger.info("=== STEP 1: INTENT CLASSIFICATION ===")
    intent = await classify_intent(text_content, conversation_history)
    logger.info(f"Classified intent: {intent}")
    
    # Step 2: Route to the appropriate workflow based on intent
    logger.info(f"=== STEP 2: WORKFLOW ROUTING FOR INTENT '{intent}' ===")
    
    response = None
    
    if intent == IntentType.GREETING.value:
        logger.info("Routing to GREETING workflow")
        response = await process_greeting(text_content, user_id, conversation_history)
    
    elif intent == IntentType.GENERAL.value:
        logger.info("Routing to GENERAL RESPONSE workflow")
        response = await process_general_response(text_content, intent, user_id, conversation_history)
    
    elif intent == IntentType.INVOICE_QUERY.value:
        logger.info("Routing to INVOICE QUERY workflow")
        response = await process_invoice_query(text_content, user_id, conversation_history)
    
    elif intent == IntentType.INVOICE_CREATOR.value:
        logger.info("Routing to INVOICE CREATOR workflow")
        response = await process_invoice_creation(text_content, user_id, conversation_history)
    
    else:
        # Default to general response for unrecognized intents
        logger.warning(f"Unrecognized intent '{intent}', defaulting to GENERAL RESPONSE workflow")
        response = await process_general_response(text_content, IntentType.GENERAL.value, user_id, conversation_history)
    
    logger.info("=== TEXT PROCESSING WORKFLOW COMPLETED ===")
    logger.info(f"Response content length: {len(response.get('content', ''))}")
    logger.info(f"Response confidence: {response.get('confidence', 0.0)}")
    
    return response


async def classify_intent(
    text_content: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None
) -> str:
    """
    Classify the intent of a text message.
    
    Args:
        text_content: The text content to classify
        conversation_history: Optional conversation history for context
        
    Returns:
        String representing the intent type
    """
    logger.info(f"Starting intent classification for: '{text_content}'")
    llm_factory = LLMFactory()
    logger.debug("LLMFactory initialized for intent classification")
    
    agent = TextIntentClassifierAgent(llm_factory=llm_factory)
    logger.debug("TextIntentClassifierAgent initialized")
    
    user_input = UserInput(
        content=text_content
    )
    logger.debug(f"UserInput created with content length: {len(text_content)}")
    
    try:
        logger.info("Calling intent classification agent to process input")
        result = await agent.process({
            "content": text_content,
            "conversation_history": conversation_history or []
        })
        
        # Handle AgentOutput object - content field contains the intent
        if result and hasattr(result, 'content'):
            logger.info(f"Intent classifier returned intent: {result.content} with confidence: {result.confidence}")
            return result.content
        
        # Fallback if the result is a dict
        elif isinstance(result, dict) and "intent" in result:
            logger.info(f"Intent classifier returned dict with intent: {result['intent']}")
            return result["intent"]
        
        logger.warning("Intent classifier returned invalid result, defaulting to GENERAL")
        return IntentType.GENERAL.value
        
    except Exception as e:
        logger.exception(f"Error classifying intent: {str(e)}")
        logger.warning("Using GENERAL intent due to classification error")
        return IntentType.GENERAL.value 