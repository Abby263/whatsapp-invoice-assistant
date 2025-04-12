"""
API interface for the WhatsApp Invoice Assistant LangGraph workflow.

This module provides functions for interfacing between the FastAPI endpoints
and the LangGraph workflow, handling request parsing and response formatting.
"""

import logging
import os
import tempfile
import json
import shutil
import asyncio
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
from uuid import UUID
from fastapi import BackgroundTasks
from urllib.parse import urlparse
import requests

from sqlalchemy.orm import Session

from langchain_app.text_processing_workflow import process_text_message as process_text
from langchain_app.file_processing_workflow import process_file_message as process_file
from services.database import get_session, Database
from langchain_app.workflow import process_input, create_state
from langchain_app.state import IntentType, FileType, InputType
from constants.fallback_messages import GENERAL_FALLBACKS, STORAGE_FALLBACKS, FILE_PROCESSING_FALLBACKS

logger = logging.getLogger(__name__)


async def process_text_message(
    message: str, 
    sender: str, 
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    user_id: Optional[Union[str, UUID]] = None,
    conversation_id: Optional[str] = None,
    db_session: Optional[Session] = None
) -> Dict[str, Any]:
    """
    Process a text message through the text processing workflow.
    
    Args:
        message: The text message content
        sender: The sender identifier
        conversation_history: Optional history of previous conversations
        user_id: Optional user ID for persisting conversation history
        conversation_id: Optional conversation ID for continuing a conversation
        db_session: Optional database session for context persistence
        
    Returns:
        The formatted response
    """
    logger.info(f"Processing text message from {sender}")
    
    try:
        # Process the text message through the specialized workflow
        result = await process_text(
            text_content=message,
            user_id=user_id,
            conversation_history=conversation_history or []
        )
        
        # Update the result processing to handle cases where content is missing
        if result and "error" in result:
            return {
                "message": f"Error: {result['error']}",
                "status": "error",
                "type": "text",
                "user_id": user_id
            }
        elif result and "content" in result:
            # Check if token usage is available
            metadata = result.get("metadata", {})
            
            # Add default token usage if not provided
            if "token_usage" not in metadata:
                # Approximate token counts if not available
                input_tokens = len(message.split()) * 1.3
                output_tokens = len(result["content"].split()) * 1.3
                metadata["token_usage"] = {
                    "input_tokens": int(input_tokens),
                    "output_tokens": int(output_tokens),
                    "total_tokens": int(input_tokens + output_tokens)
                }
            
            return {
                "message": result["content"],
                "metadata": metadata,
                "status": "success", 
                "type": "text",
                "user_id": user_id,
                "whatsapp_number": sender
            }
        else:
            # Handle the case where content is missing
            error_msg = "An unexpected error occurred while processing your request."
            if result:
                error_msg = f"Processing error: {str(result)}"
            return {
                "message": "I apologize, but an error occurred while processing your message.",
                "metadata": {"error": str(result) if result else "No response data"},
                "status": "success",
                "type": "text", 
                "user_id": user_id,
                "whatsapp_number": sender
            }
    
    except Exception as e:
        logger.exception(f"Error processing text message: {str(e)}")
        return {
            "message": "I apologize, but an error occurred while processing your message.",
            "metadata": {"error": str(e)}
        }


async def process_file_message(
    file_path: str, 
    file_name: str, 
    mime_type: str, 
    sender: str, 
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    user_id: Optional[Union[str, UUID]] = None,
    conversation_id: Optional[str] = None,
    db_session: Optional[Session] = None
) -> Dict[str, Any]:
    """
    Process a file message through the file processing workflow.
    
    Args:
        file_path: Path to the uploaded file
        file_name: Original filename
        mime_type: MIME type of the file
        sender: The sender identifier
        conversation_history: Optional history of previous conversations
        user_id: Optional user ID for persisting conversation history
        conversation_id: Optional conversation ID for continuing a conversation
        db_session: Optional database session for context persistence
        
    Returns:
        The formatted response
    """
    logger.info(f"Processing file message from {sender}: {file_name} ({mime_type})")
    logger.info(f"File path: {file_path}, user_id: {user_id}")
    
    try:
        # Process the file through the specialized workflow
        logger.info(f"Calling process_file with user_id: {user_id}")
        result = await process_file(
            file_path=file_path,
            file_type=mime_type,
            file_name=file_name,
            user_id=user_id,
            conversation_history=conversation_history or []
        )
        
        # Log the result
        if isinstance(result, dict):
            metadata = result.get("metadata", {})
            if "invoice_id" in metadata:
                logger.info(f"Successfully stored invoice with ID: {metadata['invoice_id']}")
                if "item_ids" in metadata:
                    logger.info(f"Stored items: {len(metadata['item_ids'])} items")
            else:
                logger.warning("No invoice_id in result metadata, database storage may have failed")
            
            # Add default token usage if not provided
            if "token_usage" not in metadata:
                # For file processing, estimate tokens differently
                # Approximate token counts based on content
                output_content = result.get("content", "")
                output_tokens = len(output_content.split()) * 1.3  
                # Input tokens for file processing are harder to estimate
                input_tokens = 500  # Default value for file processing
                
                metadata["token_usage"] = {
                    "input_tokens": int(input_tokens),
                    "output_tokens": int(output_tokens),
                    "total_tokens": int(input_tokens + output_tokens)
                }
        
        # Return the result
        return {
            "message": result["content"],
            "metadata": result.get("metadata", {}),
            "conversation_id": conversation_id
        }
    
    except Exception as e:
        logger.exception(f"Error processing file message: {str(e)}")
        return {
            "message": "I apologize, but an error occurred while processing your file.",
            "metadata": {"error": str(e)}
        }


async def process_whatsapp_message(message_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a WhatsApp message from Twilio through the appropriate workflow.
    
    Args:
        message_data: The message data from Twilio
        
    Returns:
        The formatted response
    """
    logger.info("Processing WhatsApp message")
    
    try:
        # Extract message information
        sender = message_data.get("From", "unknown")
        user_id = extract_user_id_from_sender(sender)
        
        # Check if this is a text or media message
        if "Body" in message_data and message_data.get("NumMedia", "0") == "0":
            # This is a text message
            message_text = message_data.get("Body", "")
            
            # Get conversation history if available
            conversation_history = await load_conversation_history(user_id)
            
            # Process the text message
            return await process_text_message(
                message_text, 
                sender, 
                conversation_history,
                user_id
            )
            
        elif message_data.get("NumMedia", "0") != "0":
            # This is a media message
            media_url = message_data.get("MediaUrl0", "")
            media_content_type = message_data.get("MediaContentType0", "")
            
            if media_url is None:
                logger.error("Media URL not found in message")
                return {
                    "status": "error",
                    "message": STORAGE_FALLBACKS["download_failure"]
                }
            
            # Download the media file to a temporary location
            import httpx
            
            temp_dir = Path(tempfile.mkdtemp())
            file_name = os.path.basename(media_url)
            file_path = temp_dir / file_name
            
            async with httpx.AsyncClient() as client:
                response = await client.get(media_url)
                if response.status_code != 200:
                    logger.error(f"Failed to download media: {response.status_code}")
                    return {
                        "status": "error",
                        "message": STORAGE_FALLBACKS["download_failure"]
                    }
                
                with open(file_path, "wb") as f:
                    f.write(response.content)
            
            # Get conversation history if available
            conversation_history = await load_conversation_history(user_id)
            
            # Process the file message
            result = await process_file_message(
                str(file_path),
                file_name,
                media_content_type,
                sender,
                conversation_history,
                user_id
            )
            
            # Clean up the temporary file
            try:
                os.unlink(file_path)
                os.rmdir(temp_dir)
            except Exception as e:
                logger.warning(f"Failed to clean up temporary file: {str(e)}")
            
            return result
        
        else:
            logger.error("Unknown message type")
            return {
                "status": "error",
                "message": GENERAL_FALLBACKS["no_response"]
            }
    
    except Exception as e:
        logger.exception(f"Error processing WhatsApp message: {str(e)}")
        return {
            "status": "error",
            "message": GENERAL_FALLBACKS["no_response"]
        }


def extract_user_id_from_sender(sender: str) -> Optional[str]:
    """
    Extract a user ID from the sender identifier.
    In a real implementation, this would look up the user in the database.
    
    Args:
        sender: The sender identifier (usually a phone number)
        
    Returns:
        User ID if found, None otherwise
    """
    # In a real implementation, this would query the database
    # For now, we'll just use the sender as the user ID
    return sender


async def load_conversation_history(user_id: Optional[str]) -> List[Dict[str, Any]]:
    """
    Load conversation history for a user.
    In a real implementation, this would load from the database.
    
    Args:
        user_id: The user ID to load history for
        
    Returns:
        List of conversation history items
    """
    # In a real implementation, this would load from the database
    # For now, return an empty list
    return [] 