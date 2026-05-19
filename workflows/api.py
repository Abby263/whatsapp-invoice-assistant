"""
API interface for the WhatsApp Invoice Assistant workflows.

This module provides functions for interfacing between Flask routes and the
agent workflows, handling request parsing and response formatting.
"""

import logging
import os
import hashlib
import io
import json
import tempfile
import shutil
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
from uuid import UUID
import mimetypes

import httpx
from sqlalchemy.orm import Session

from workflows.text_processing_workflow import process_text_message as process_text
from workflows.file_processing_workflow import process_file_message as process_file
from workflows.state import IntentType
from constants.fallback_messages import GENERAL_FALLBACKS, STORAGE_FALLBACKS
from services.conversation_policy import compact_whatsapp_message, media_processing_ack
from services.conversation_memory import load_user_conversation_history, save_conversation_turn
from services.twilio_messaging import send_processing_ack, send_whatsapp_message
from schemas.llm_outputs import is_ledger_document
from utils.phone_numbers import normalize_whatsapp_number

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
    whatsapp_message_sid: Optional[str] = None,
    conversation_history_trusted: bool = False,
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
        if user_id is None:
            user_id = extract_user_id_from_sender(sender)
            if user_id:
                logger.info("Resolved missing text-message user_id from sender")
            else:
                logger.warning("Could not resolve text-message user_id from sender %s", sender)

        active_history = await _resolve_user_scoped_history(
            user_id=user_id,
            conversation_history=conversation_history,
            conversation_history_trusted=conversation_history_trusted,
        )

        # Process the text message through the specialized workflow
        result = await process_text(
            text_content=message,
            user_id=user_id,
            conversation_history=active_history or []
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
            
            response_payload = {
                "message": result["content"],
                "metadata": metadata,
                "status": "success", 
                "type": "text",
                "user_id": user_id,
                "whatsapp_number": sender
            }
            saved_conversation_id = save_conversation_turn(
                user_id,
                user_message=message,
                assistant_message=result["content"],
                whatsapp_message_sid=whatsapp_message_sid,
            )
            if saved_conversation_id is not None:
                response_payload["conversation_id"] = str(saved_conversation_id)
            return response_payload
        else:
            # Handle the case where content is missing
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
    persist_conversation: bool = True,
    conversation_history_trusted: bool = False,
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
        active_history = await _resolve_user_scoped_history(
            user_id=user_id,
            conversation_history=conversation_history,
            conversation_history_trusted=conversation_history_trusted,
        )
        result = await process_file(
            file_path=file_path,
            file_type=mime_type,
            file_name=file_name,
            user_id=user_id,
            conversation_history=active_history,
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
        response_payload = {
            "message": result["content"],
            "metadata": result.get("metadata", {}),
            "conversation_id": conversation_id
        }
        if persist_conversation:
            saved_conversation_id = save_conversation_turn(
                user_id,
                user_message=f"Uploaded file: {file_name}",
                assistant_message=result.get("content"),
                whatsapp_message_sid=(file_metadata or {}).get("twilio_message_sid"),
            )
            if saved_conversation_id is not None:
                response_payload["conversation_id"] = str(saved_conversation_id)
        return response_payload
    
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
    message_sid = _message_sid_from_payload(message_data)
    webhook_claim = _claim_webhook_event(message_sid)
    if not webhook_claim.get("claimed", True):
        return _duplicate_webhook_response(message_sid, webhook_claim)
    
    try:
        # Extract message information
        sender = message_data.get("From", "unknown")
        media_count = _parse_num_media(message_data.get("NumMedia"))
        has_media = media_count > 0

        if has_media:
            send_processing_ack(
                to_number=sender,
                from_number=(
                    message_data.get("To") or os.environ.get("TWILIO_PHONE_NUMBER")
                ),
                body=media_processing_ack(media_count),
            )

        user_id = extract_user_id_from_sender(sender)
        
        # Check if this is a text or media message
        if "Body" in message_data and not has_media:
            # This is a text message
            message_text = message_data.get("Body", "")
            
            # Get conversation history if available
            conversation_history = await load_conversation_history(user_id)
            
            # Process the text message
            result = await process_text_message(
                message_text, 
                sender, 
                conversation_history,
                user_id,
                whatsapp_message_sid=message_sid,
                conversation_history_trusted=True,
            )
            _mark_webhook_event_processed(message_sid, result)
            return result
            
        elif has_media:
            # This is a media message. Twilio indexes media fields as
            # MediaUrl0, MediaContentType0, MediaUrl1, ... up to NumMedia.
            temp_dir = Path(tempfile.mkdtemp())
            try:
                conversation_history = await load_conversation_history(user_id)
                results = []
                seen_checksums: set[str] = set()

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
                                    "file_name": file_name,
                                    "content_type": effective_content_type,
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
                            persist_conversation=False,
                            conversation_history_trusted=True,
                        )
                        result.setdefault("metadata", {})
                        result["metadata"]["media_index"] = index
                        result["metadata"]["file_name"] = file_name
                        result["metadata"]["content_type"] = effective_content_type
                        results.append(result)

                combined_result = _combine_media_results(results)
                saved_conversation_id = save_conversation_turn(
                    user_id,
                    user_message=_media_memory_user_message(message_data, media_count),
                    assistant_message=combined_result.get("message") or combined_result.get("content"),
                    whatsapp_message_sid=message_sid,
                )
                if saved_conversation_id is not None:
                    combined_result["conversation_id"] = str(saved_conversation_id)
                if _send_media_final_reply(
                    result=combined_result,
                    to_number=sender,
                    from_number=message_data.get("To") or os.environ.get("TWILIO_PHONE_NUMBER"),
                ):
                    combined_result["suppress_twiml_response"] = True
                    combined_result.setdefault("metadata", {})["twilio_final_reply_sent"] = True
                _mark_webhook_event_processed(message_sid, combined_result)
                return combined_result
            finally:
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception as e:
                    logger.warning(f"Failed to clean up temporary file: {str(e)}")
        
        else:
            logger.error("Unknown message type")
            result = {
                "status": "error",
                "message": GENERAL_FALLBACKS["no_response"]
            }
            _mark_webhook_event_processed(message_sid, result)
            return result
    
    except Exception as e:
        logger.exception(f"Error processing WhatsApp message: {str(e)}")
        _mark_webhook_event_failed(message_sid, str(e))
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


def _message_sid_from_payload(message_data: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(message_data, dict):
        return None
    return message_data.get("MessageSid") or message_data.get("SmsMessageSid")


def _claim_webhook_event(message_sid: Optional[str]) -> Dict[str, Any]:
    """Claim a Twilio webhook event before running side-effectful processing."""

    if not message_sid:
        return {"claimed": True, "status": "untracked"}

    try:
        from sqlalchemy.exc import IntegrityError

        from database.connection import ensure_application_schema, get_db_session
        from database.schemas import WebhookEvent

        ensure_application_schema()
        session = get_db_session()
        try:
            event = WebhookEvent(
                event_id=message_sid,
                source="twilio_whatsapp",
                status="processing",
            )
            session.add(event)
            try:
                session.commit()
                return {"claimed": True, "status": "processing"}
            except IntegrityError:
                session.rollback()

            existing = (
                session.query(WebhookEvent)
                .filter(WebhookEvent.event_id == message_sid)
                .first()
            )
            if existing is None:
                return {"claimed": True, "status": "untracked"}
            if existing.status == "failed":
                existing.status = "processing"
                existing.error_message = None
                existing.response_payload = None
                session.commit()
                return {"claimed": True, "status": "processing_retry"}
            return {
                "claimed": False,
                "status": existing.status,
                "response_payload": existing.response_payload if isinstance(existing.response_payload, dict) else None,
            }
        finally:
            session.close()
    except Exception as exc:
        logger.warning("Could not claim webhook event %s; continuing without replay protection: %s", message_sid, exc)
        return {"claimed": True, "status": "unavailable"}


def _mark_webhook_event_processed(message_sid: Optional[str], result: Dict[str, Any]) -> None:
    _update_webhook_event(message_sid, "processed", response_payload=_webhook_response_payload(result))


def _mark_webhook_event_failed(message_sid: Optional[str], error_message: str) -> None:
    _update_webhook_event(message_sid, "failed", error_message=error_message)


def _update_webhook_event(
    message_sid: Optional[str],
    status: str,
    *,
    response_payload: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
) -> None:
    if not message_sid:
        return

    try:
        from database.connection import ensure_application_schema, get_db_session
        from database.schemas import WebhookEvent

        ensure_application_schema()
        session = get_db_session()
        try:
            event = (
                session.query(WebhookEvent)
                .filter(WebhookEvent.event_id == message_sid)
                .first()
            )
            if event is None:
                return
            event.status = status
            event.error_message = error_message
            if response_payload is not None:
                event.response_payload = response_payload
                event.response_hash = hashlib.sha256(
                    json.dumps(response_payload, sort_keys=True, default=str).encode("utf-8")
                ).hexdigest()
            session.commit()
        finally:
            session.close()
    except Exception as exc:
        logger.warning("Could not update webhook event %s to %s: %s", message_sid, status, exc)


def _webhook_response_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    return {
        "status": result.get("status"),
        "message": result.get("message") or result.get("content"),
        "suppress_twiml_response": bool(
            result.get("suppress_twiml_response") or metadata.get("twilio_final_reply_sent")
        ),
        "metadata": {
            key: metadata.get(key)
            for key in (
                "intent",
                "twilio_final_reply_sent",
                "media_count",
                "saved_count",
                "pending_approval_count",
                "duplicate_count",
                "failed_count",
            )
            if key in metadata
        },
    }


def _duplicate_webhook_response(message_sid: Optional[str], claim: Dict[str, Any]) -> Dict[str, Any]:
    """Return an empty response for Twilio webhook replays without repeating side effects."""

    return {
        "status": "duplicate",
        "message": "",
        "suppress_twiml_response": True,
        "metadata": {
            "webhook_duplicate": True,
            "twilio_message_sid": message_sid,
            "webhook_event_status": claim.get("status"),
            "cached_response": claim.get("response_payload"),
        },
    }


async def _resolve_user_scoped_history(
    *,
    user_id: Optional[Union[str, UUID]],
    conversation_history: Optional[List[Dict[str, Any]]],
    conversation_history_trusted: bool,
) -> List[Dict[str, Any]]:
    """Return conversation memory without trusting caller-supplied history across users."""

    if user_id is None:
        return conversation_history or []
    if conversation_history_trusted:
        return conversation_history or []
    if conversation_history:
        logger.warning(
            "Ignoring untrusted supplied conversation history for user-scoped request user_id=%s",
            user_id,
        )
    return await load_conversation_history(user_id)


def _media_memory_user_message(message_data: Dict[str, Any], media_count: int) -> str:
    body = str(message_data.get("Body") or "").strip()
    if body:
        return body
    attachment_label = "attachment" if media_count == 1 else "attachments"
    return f"Uploaded {media_count} WhatsApp {attachment_label}."


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

    successes = [result for result in results if _media_result_state(result) not in {"failed", "rejected"}]
    errors = [result for result in results if _media_result_state(result) in {"failed", "rejected"}]
    duplicates = [
        result for result in results
        if _media_result_state(result) == "duplicate"
    ]
    stored = [
        result for result in results
        if _media_result_state(result) == "saved"
    ]
    pending = [
        result for result in results
        if _media_result_state(result) == "awaiting approval"
    ]

    if len(results) == 1:
        return results[0]

    lines = [
        "📎 *Batch Processing Result*",
        "",
        f"*Attachments received:* {len(results)}",
        f"*Saved:* {len(stored)}",
        f"*Pending approval:* {len(pending)}",
        f"*Duplicates:* {len(duplicates)}",
        f"*Failed:* {len(errors)}",
        "",
        "*Files:*",
    ]
    for result in results[:8]:
        lines.append(_media_result_summary_line(result))
    if len(results) > 8:
        lines.append(f"+ {len(results) - 8} more attachments processed")

    return {
        "status": "success" if successes else "error",
        "message": "\n".join(lines),
        "metadata": {
            "intent": IntentType.FILE_PROCESSING.value,
            "media_count": len(results),
            "saved_count": len(stored),
            "pending_approval_count": len(pending),
            "duplicate_count": len(duplicates),
            "failed_count": len(errors),
            "results": results,
        },
    }


def _media_result_state(result: Dict[str, Any]) -> str:
    metadata = result.get("metadata", {}) if isinstance(result.get("metadata"), dict) else {}
    if metadata.get("hitl_status") == "awaiting_confirmation":
        return "awaiting approval"
    if metadata.get("duplicate"):
        return "duplicate"
    if metadata.get("success") is False:
        return "rejected"
    if result.get("status") == "error":
        return "failed"
    if metadata.get("stored_in_database"):
        return "saved"
    return "processed"


def _media_result_summary_line(result: Dict[str, Any]) -> str:
    metadata = result.get("metadata", {}) if isinstance(result.get("metadata"), dict) else {}
    index = metadata.get("media_index")
    attachment_number = index + 1 if isinstance(index, int) else "?"
    file_name = metadata.get("file_name") or "unknown"
    state = _media_result_state(result)
    invoice_data = metadata.get("invoice_data") if isinstance(metadata.get("invoice_data"), dict) else {}

    document_type = "Unknown"
    transaction_date = "Not visible"
    total = "Not visible"
    item_count = 0
    if invoice_data:
        additional_info = invoice_data.get("additional_info", {}) if isinstance(invoice_data.get("additional_info"), dict) else {}
        transaction = invoice_data.get("transaction", {}) if isinstance(invoice_data.get("transaction"), dict) else {}
        financial = invoice_data.get("financial", {}) if isinstance(invoice_data.get("financial"), dict) else {}
        document_type = _business_summary_label(
            additional_info.get("document_type")
            or ("handwritten_ledger" if is_ledger_document(invoice_data) else "financial_document")
        )
        transaction_date = transaction.get("date") or invoice_data.get("date") or invoice_data.get("invoice_date") or "Not visible"
        currency = financial.get("currency") or invoice_data.get("currency") or ("INR" if is_ledger_document(invoice_data) else "USD")
        amount = (
            financial.get("total")
            or financial.get("total_amount")
            or invoice_data.get("total_amount")
            or invoice_data.get("total")
        )
        total = _format_summary_money(amount, currency) if amount not in (None, "") else "Not visible"
        items = invoice_data.get("items") if isinstance(invoice_data.get("items"), list) else []
        item_count = len(items)

    if state in {"failed", "rejected"}:
        reason = (
            metadata.get("validation_result", {}).get("reason")
            if isinstance(metadata.get("validation_result"), dict)
            else None
        ) or result.get("message") or "Could not process this attachment"
        return f"{attachment_number}. *{_business_summary_label(state)}* - {file_name}\n   Reason: {str(reason)[:120]}"
    return (
        f"{attachment_number}. *{_business_summary_label(state)}* - {file_name}\n"
        f"   Type: {document_type}\n"
        f"   Date: {transaction_date}\n"
        f"   Total: {total}\n"
        f"   Items: {item_count}"
    )


def _business_summary_label(value: Any) -> str:
    return str(value or "").replace("_", " ").replace("-", " ").title()


def _format_summary_money(amount: Any, currency: str) -> str:
    try:
        return f"{float(amount):,.2f} {currency}".strip()
    except (TypeError, ValueError):
        return f"{amount} {currency}".strip()


def _send_media_final_reply(
    result: Dict[str, Any],
    to_number: str,
    from_number: Optional[str],
) -> bool:
    """Send the media processing result out-of-band when possible."""

    if os.environ.get("TWILIO_MEDIA_FINAL_REPLY_ENABLED", "true").lower() not in {"1", "true", "yes"}:
        return False

    message = result.get("message") or result.get("content") or ""
    if not message:
        return False

    return send_whatsapp_message(
        to_number=to_number,
        from_number=from_number,
        body=compact_whatsapp_message(message),
    )


def extract_user_id_from_sender(sender: str) -> Optional[str]:
    """
    Resolve the internal app user ID from a WhatsApp sender identifier.
    
    Args:
        sender: The sender identifier (usually a phone number)
        
    Returns:
        User ID if found, None otherwise
    """
    whatsapp_number = normalize_whatsapp_number(sender)
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
    return load_user_conversation_history(user_id)
