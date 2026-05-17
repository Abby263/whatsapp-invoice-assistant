"""
API interface for the WhatsApp Invoice Assistant LangGraph workflow.

This module provides functions for interfacing between Flask routes and the
agent workflows, handling request parsing and response formatting.
"""

import logging
import os
import hashlib
import io
import tempfile
import shutil
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
from uuid import UUID
import mimetypes

import httpx
from sqlalchemy.orm import Session

from langchain_app.text_processing_workflow import process_text_message as process_text
from langchain_app.file_processing_workflow import process_file_message as process_file
from langchain_app.state import IntentType
from constants.fallback_messages import GENERAL_FALLBACKS, STORAGE_FALLBACKS, FILE_PROCESSING_FALLBACKS
from services.conversation_policy import media_processing_ack
from services.twilio_messaging import send_processing_ack

logger = logging.getLogger(__name__)

GENERIC_MEDIA_CONTENT_TYPES = {
    "",
    "application/octet-stream",
    "binary/octet-stream",
    "application/x-download",
}

MEDIA_CONTENT_TYPE_EXTENSIONS = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/webp": ".webp",
    "text/csv": ".csv",
    "application/csv": ".csv",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
}


async def process_text_message(
    message: str, 
    sender: str, 
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    user_id: Optional[Union[str, UUID]] = None,
    conversation_id: Optional[str] = None,
    db_session: Optional[Session] = None,
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
        
        # Update the result processing to handle cases where content is missing.
        # AgentOutput dictionaries include ``error: None`` on successful local
        # responses, so only treat the result as an error when the error value
        # is truthy or the status is explicitly failed.
        if result and (result.get("error") or result.get("status") == "error"):
            return {
                "message": f"Error: {result.get('error') or result.get('message') or 'Processing failed'}",
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
    db_session: Optional[Session] = None,
    file_metadata: Optional[Dict[str, Any]] = None,
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
            conversation_history=conversation_history or [],
            file_metadata=file_metadata,
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
            # This is a media message. Twilio indexes media fields as
            # MediaUrl0, MediaContentType0, MediaUrl1, ... up to NumMedia.
            temp_dir = Path(tempfile.mkdtemp())
            try:
                conversation_history = await load_conversation_history(user_id)
                results = []
                seen_checksums: set[str] = set()
                media_count = _parse_num_media(message_data.get("NumMedia"))
                if media_count > 0:
                    send_processing_ack(
                        to_number=sender,
                        from_number=message_data.get("To") or os.environ.get("TWILIO_PHONE_NUMBER"),
                        body=media_processing_ack(media_count),
                    )

                async with httpx.AsyncClient() as client:
                    for index in range(media_count):
                        media_url = message_data.get(f"MediaUrl{index}", "")
                        media_content_type = message_data.get(f"MediaContentType{index}", "")
                        if not media_url:
                            logger.error("Media URL not found for index %s", index)
                            results.append({
                                "status": "error",
                                "message": STORAGE_FALLBACKS["download_failure"],
                                "metadata": {"media_index": index},
                            })
                            continue

                        file_name = _twilio_media_filename(media_url, media_content_type, index)
                        auth = _twilio_media_auth(media_url)
                        response = await client.get(media_url, auth=auth, follow_redirects=True)
                        if response.status_code != 200:
                            logger.error("Failed to download media %s: %s", index, response.status_code)
                            results.append({
                                "status": "error",
                                "message": STORAGE_FALLBACKS["download_failure"],
                                "metadata": {"media_index": index, "media_url": media_url},
                            })
                            continue

                        file_bytes = response.content
                        effective_content_type = _sniff_twilio_media_content_type(
                            file_bytes,
                            media_content_type,
                            file_name,
                        )
                        file_name = _ensure_media_filename_extension(
                            file_name,
                            effective_content_type,
                            index,
                        )
                        file_path = temp_dir / f"{index}_{file_name}"
                        checksum = hashlib.sha256(file_bytes).hexdigest()
                        if checksum in seen_checksums:
                            logger.info("Skipping duplicate media in same WhatsApp message: index=%s", index)
                            results.append({
                                "status": "success",
                                "message": f"I skipped duplicate attachment {index + 1}; it matched another file in this message.",
                                "metadata": {
                                    "media_index": index,
                                    "duplicate": True,
                                    "duplicate_scope": "message_batch",
                                    "checksum_sha256": checksum,
                                },
                            })
                            continue
                        seen_checksums.add(checksum)

                        with open(file_path, "wb") as f:
                            f.write(file_bytes)
                        logger.info(
                            "Downloaded Twilio media message_sid=%s index=%s declared_type=%s effective_type=%s filename=%s bytes=%s",
                            message_data.get("MessageSid") or message_data.get("SmsMessageSid"),
                            index,
                            media_content_type or "",
                            effective_content_type,
                            file_name,
                            len(file_bytes),
                        )

                        result = await process_file_message(
                            str(file_path),
                            file_name,
                            effective_content_type,
                            sender,
                            conversation_history,
                            user_id,
                            file_metadata={
                                "source": "twilio_whatsapp",
                                "twilio_message_sid": (
                                    message_data.get("MessageSid")
                                    or message_data.get("SmsMessageSid")
                                ),
                                "twilio_media_sid": message_data.get(f"MediaSid{index}"),
                                "twilio_media_index": index,
                                "twilio_media_url": media_url,
                                "checksum_sha256": checksum,
                            },
                        )
                        result.setdefault("metadata", {})
                        result["metadata"]["media_index"] = index
                        results.append(result)

                return _combine_media_results(results)
            finally:
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception as e:
                    logger.warning(f"Failed to clean up temporary file: {str(e)}")
        
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


def _twilio_media_auth(media_url: str):
    """Return Basic Auth for protected Twilio media URLs when configured."""

    if "api.twilio.com" not in (media_url or ""):
        return None
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not account_sid or not auth_token:
        return None
    return (account_sid, auth_token)


def _parse_num_media(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _twilio_media_filename(media_url: str, media_content_type: str, index: int) -> str:
    file_name = os.path.basename((media_url or "").split("?", 1)[0]) or f"receipt_{index + 1}"
    return _ensure_media_filename_extension(file_name, media_content_type, index)


def _ensure_media_filename_extension(file_name: str, content_type: str, index: int) -> str:
    file_name = file_name or f"receipt_{index + 1}"
    if Path(file_name).suffix:
        return file_name

    normalized_content_type = _normalize_media_content_type(content_type)
    guessed_ext = (
        MEDIA_CONTENT_TYPE_EXTENSIONS.get(normalized_content_type)
        or mimetypes.guess_extension(normalized_content_type)
    )
    if guessed_ext:
        return f"{file_name}{guessed_ext}"
    return file_name


def _normalize_media_content_type(content_type: str) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def _sniff_twilio_media_content_type(
    file_bytes: bytes,
    declared_content_type: str,
    file_name: str,
) -> str:
    declared_type = _normalize_media_content_type(declared_content_type)
    if declared_type not in GENERIC_MEDIA_CONTENT_TYPES:
        return declared_type

    guessed_type, _ = mimetypes.guess_type(file_name)
    guessed_type = _normalize_media_content_type(guessed_type or "")
    if guessed_type and guessed_type not in GENERIC_MEDIA_CONTENT_TYPES:
        return guessed_type

    if file_bytes.startswith(b"%PDF"):
        return "application/pdf"

    try:
        from PIL import Image

        with Image.open(io.BytesIO(file_bytes)) as image:
            image_format = (image.format or "").lower()
        if image_format in {"jpeg", "jpg"}:
            return "image/jpeg"
        if image_format:
            return f"image/{image_format}"
    except Exception:
        pass

    return declared_type or "application/octet-stream"


def _combine_media_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not results:
        return {"status": "error", "message": STORAGE_FALLBACKS["download_failure"]}

    successes = [result for result in results if result.get("status") != "error"]
    errors = [result for result in results if result.get("status") == "error"]
    duplicates = [
        result for result in successes
        if result.get("metadata", {}).get("duplicate")
    ]
    stored = [
        result for result in successes
        if result.get("metadata", {}).get("stored_in_database")
    ]

    if len(results) == 1:
        return results[0]

    summary_parts = [
        f"Processed {len(results)} attachments.",
        f"{len(stored)} saved",
        f"{len(duplicates)} duplicate{'s' if len(duplicates) != 1 else ''} skipped",
        f"{len(errors)} failed",
    ]
    detail_lines = []
    for result in results:
        metadata = result.get("metadata", {})
        index = metadata.get("media_index")
        label = f"Attachment {index + 1}" if isinstance(index, int) else "Attachment"
        if metadata.get("duplicate"):
            state = "duplicate"
        elif result.get("status") == "error":
            state = "failed"
        elif metadata.get("stored_in_database"):
            state = "saved"
        else:
            state = "processed"
        if state == "failed":
            detail_lines.append(f"{label}: failed")
        else:
            detail_lines.append(f"{label}: {state}")

    return {
        "status": "success" if successes else "error",
        "message": " ".join(summary_parts) + "\n" + "\n".join(detail_lines[:8]),
        "metadata": {
            "intent": IntentType.FILE_PROCESSING.value,
            "media_count": len(results),
            "saved_count": len(stored),
            "duplicate_count": len(duplicates),
            "failed_count": len(errors),
            "results": results,
        },
    }


def extract_user_id_from_sender(sender: str) -> Optional[str]:
    """
    Resolve the internal app user ID from a WhatsApp sender identifier.
    
    Args:
        sender: The sender identifier (usually a phone number)
        
    Returns:
        User ID if found, None otherwise
    """
    whatsapp_number = (sender or "").replace("whatsapp:", "").strip()
    if not whatsapp_number:
        return None

    try:
        from database.connection import get_db_session
        from database.user_utils import create_user

        session = get_db_session()
        try:
            user = create_user(
                session=session,
                whatsapp_number=whatsapp_number,
                name=f"WhatsApp User {whatsapp_number}",
            )
            return str(user.get("id"))
        finally:
            session.close()
    except Exception as exc:
        logger.warning("Could not resolve WhatsApp sender %s to user: %s", sender, exc)
        return None


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
