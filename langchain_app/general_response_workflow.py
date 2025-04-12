"""
General Response Workflow for WhatsApp Invoice Assistant.

This module implements specialized workflow for handling general conversations
and greeting responses, providing helpful information to users.
"""

import logging
from typing import Dict, Any, List, Optional

from utils.base_agent import BaseAgent
from agents.response_formatter import ResponseFormatterAgent
from services.llm_factory import LLMFactory
from langchain_app.state import IntentType as StateIntentType
from constants.fallback_messages import get_intent_fallback, GENERAL_FALLBACKS

logger = logging.getLogger(__name__)


async def process_general_response(
    text_content: str,
    intent: str = StateIntentType.GENERAL.value,
    user_id: Optional[str] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Process general response for non-specific intents.
    
    Args:
        text_content: The user's message
        intent: The detected intent (default: general)
        user_id: The user's ID
        conversation_history: Previous conversation history
        
    Returns:
        Dict containing the formatted response and confidence
    """
    try:
        logger.info(f"Processing general response for: {text_content[:30]}...")
        
        # Create LLMFactory instance
        llm_factory = LLMFactory()
        
        # Create response formatter agent with the LLMFactory
        agent = ResponseFormatterAgent(llm_factory)
        
        # Format the response
        formatter_input = {
            "content": text_content,
            "intent": intent,
            "user_id": user_id,
            "type": "default"
        }
        
        # If we have conversation history, add it
        if conversation_history:
            formatter_input["conversation_history"] = conversation_history
            
        result = await agent.process(formatter_input)
        
        if not result or "content" not in result:
            logger.warning(f"Failed to format {intent} response")
            
            # Use fallback responses from constants file
            response = get_intent_fallback(intent)
            
            return {
                "content": response,
                "confidence": 0.6
            }
        
        return result
    except Exception as e:
        logger.exception(f"Error generating {intent} response: {str(e)}")
        return {
            "content": GENERAL_FALLBACKS["error"],
            "confidence": 0.5
        }


async def process_greeting(
    text_content: str,
    user_id: Optional[str] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Process greeting response.
    
    Args:
        text_content: The user's message
        user_id: The user's ID
        conversation_history: Previous conversation history
        
    Returns:
        Dict containing the formatted greeting response and confidence
    """
    return await process_general_response(
        text_content,
        intent=StateIntentType.GREETING.value,
        user_id=user_id,
        conversation_history=conversation_history
    )


async def generate_general_response(
    text_content: str,
    intent: str,
    user_id: Optional[str] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Generate a general response based on intent.
    
    Args:
        text_content: The user's message
        intent: The detected intent
        user_id: The user's ID
        conversation_history: Previous conversation history
        
    Returns:
        Dict containing the formatted response and confidence
    """
    if intent == StateIntentType.GREETING.value:
        return await process_greeting(text_content, user_id, conversation_history)
    else:
        return await process_general_response(text_content, intent, user_id, conversation_history) 