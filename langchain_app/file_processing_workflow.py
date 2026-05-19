"""
File Processing Workflow for WhatsApp Invoice Assistant.

This module implements specialized workflow for handling file inputs,
validating invoice files, extracting data, and formatting responses.
"""

import logging
import os
import hashlib
from typing import Dict, Any, Optional, List, Union
from uuid import UUID
from pathlib import Path
from datetime import datetime
import json
import mimetypes

from agents.file_validator import FileValidatorAgent
from agents.data_extractor import DataExtractorAgent
from services.llm_factory import LLMFactory
from services.conversation_policy import compact_whatsapp_message
from langchain_app.state import IntentType, FileType
from utils.base_agent import AgentInput, AgentContext
from constants.fallback_messages import FILE_PROCESSING_FALLBACKS
from storage import StorageConfigurationError, record_media_upload, store_user_upload
from schemas.llm_outputs import is_ledger_document
from schemas.llm_outputs.document_extraction import coerce_number

logger = logging.getLogger(__name__)


async def process_file_message(
    file_path: str,
    file_type: str,
    file_name: Optional[str] = None,
    user_id: Optional[Union[str, UUID]] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    file_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Process a file message by validating and extracting data.

    Args:
        file_path: Path to the file to process
        file_type: MIME type or file extension
        file_name: Optional original filename
        user_id: Optional user ID for personalization
        conversation_history: Optional conversation history for context

    Returns:
        Dict containing the response content, metadata, and confidence
    """
    logger.info(f"Processing file: {file_name or file_path}")

    # Detect normalized file type from MIME type or extension
    normalized_file_type = detect_file_type(file_path, file_type)
    prepared_file_metadata = _prepare_file_metadata(file_path, file_metadata)

    duplicate_media = _find_existing_media_by_checksum(user_id, prepared_file_metadata)
    if duplicate_media:
        logger.info(
            "Duplicate upload detected for user=%s checksum=%s",
            user_id,
            prepared_file_metadata.get("checksum_sha256"),
        )
        return await format_duplicate_file_response(
            duplicate_media,
            file_name or file_path,
            normalized_file_type,
            prepared_file_metadata,
        )

    _store_original_upload(
        file_path=file_path,
        file_name=file_name or os.path.basename(file_path),
        user_id=user_id,
        document_type="invoices",
        content_type=file_type,
        file_metadata=prepared_file_metadata,
    )

    # Validate the file
    validation_result = await validate_file(file_path, normalized_file_type)

    if not validation_result.get("is_valid", False):
        logger.warning(f"Invalid file: {validation_result.get('reason', 'Unknown reason')}")
        _update_media_status(
            user_id=user_id,
            file_metadata=prepared_file_metadata,
            status="error",
            processing_metadata={"validation_result": validation_result},
        )
        return await format_invalid_file_response(validation_result, file_name or file_path)

    # Extract data if it's a valid invoice
    if validation_result.get("is_invoice", False):
        return await process_invoice_file(
            file_path,
            normalized_file_type,
            file_name,
            user_id,
            conversation_history,
            validation_result=validation_result,
            file_metadata=prepared_file_metadata,
        )

    # Handwritten or low-quality receipts are sometimes rejected by validation
    # even though the vision model can still extract useful structured fields.
    # Try one best-effort extraction for supported visual documents, then only
    # keep it when meaningful fields are present.
    if _should_try_best_effort_extraction(normalized_file_type, validation_result):
        best_effort_result = await process_invoice_file(
            file_path,
            normalized_file_type,
            file_name,
            user_id,
            conversation_history,
            validation_result=validation_result,
            best_effort=True,
            file_metadata=prepared_file_metadata,
        )
        extraction_data = (
            best_effort_result.get("metadata", {})
            .get("extraction_results", {})
            .get("data", {})
        )
        if _has_storable_extraction_data(extraction_data):
            return best_effort_result

    # Supported file type, but validation did not find a financial document.
    _update_media_status(
        user_id=user_id,
        file_metadata=prepared_file_metadata,
        status="error",
        processing_metadata={"validation_result": validation_result, "reason": "non_financial_document"},
    )
    return await format_invalid_file_response(validation_result, file_name or file_path)


async def validate_file(
    file_path: str,
    file_type: str
) -> Dict[str, Any]:
    """
    Validate a file to determine if it's a valid invoice.

    Args:
        file_path: Path to the file
        file_type: MIME type or file extension

    Returns:
        Dict containing validation results
    """
    llm_factory = LLMFactory()
    agent = FileValidatorAgent(llm_factory=llm_factory)

    try:
        # Check if file exists
        if not os.path.exists(file_path):
            return {
                "is_valid": False,
                "is_invoice": False,
                "reason": "File not found",
                "file_type": file_type
            }

        # Validate file type first
        supported_types = [
            FileType.PDF.value,
            FileType.IMAGE.value,
            FileType.EXCEL.value,
            FileType.CSV.value
        ]

        detected_type = detect_file_type(file_path, file_type)

        if detected_type not in supported_types:
            return {
                "is_valid": False,
                "is_invoice": False,
                "reason": f"Unsupported file type: {detected_type}",
                "file_type": detected_type
            }

        # Read file content
        with open(file_path, 'rb') as f:
            file_content = f.read()

        # Use agent to validate if it's an invoice - create an AgentInput object
        agent_input = AgentInput(
            content=file_content,
            file_path=file_path,
            file_name=os.path.basename(file_path),
            content_type=detected_type,
            metadata={"file_type": detected_type}
        )

        # Process with the properly constructed AgentInput object
        result = await agent.process(agent_input)

        if not result:
            return {
                "is_valid": True,
                "is_invoice": False,
                "reason": "Could not determine if file is an invoice",
                "file_type": detected_type
            }

        return {
            "is_valid": True,
            "is_invoice": result.content,  # The content field contains the boolean is_invoice result
            "confidence": result.confidence,
            "file_type": detected_type,
            "reason": result.metadata.get("reasons", "")
        }

    except Exception as e:
        logger.exception(f"Error validating file: {str(e)}")
        return {
            "is_valid": False,
            "is_invoice": False,
            "reason": f"Error during validation: {str(e)}",
            "file_type": file_type
        }


def detect_file_type(file_path: str, mime_type: str) -> str:
    """
    Detect file type based on extension and/or MIME type.

    Args:
        file_path: Path to the file
        mime_type: MIME type or file extension

    Returns:
        Normalized file type string
    """
    # Extract file extension
    extension = Path(file_path).suffix.lower()

    # Check based on extension
    if extension in ['.pdf']:
        return FileType.PDF.value
    elif extension in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']:
        return FileType.IMAGE.value
    elif extension in ['.xls', '.xlsx']:
        return FileType.EXCEL.value
    elif extension in ['.csv']:
        return FileType.CSV.value

    # Check based on MIME type
    if mime_type:
        mime_lower = mime_type.lower()
        if 'pdf' in mime_lower:
            return FileType.PDF.value
        elif any(img_type in mime_lower for img_type in ['jpeg', 'jpg', 'png', 'image']):
            return FileType.IMAGE.value
        elif any(excel_type in mime_lower for excel_type in ['excel', 'spreadsheet', 'xlsx', 'xls']):
            return FileType.EXCEL.value
        elif 'csv' in mime_lower:
            return FileType.CSV.value

    sniffed_file_type = _sniff_file_type_from_content(file_path)
    if sniffed_file_type:
        return sniffed_file_type

    # Default to binary
    return FileType.BINARY.value


def _sniff_file_type_from_content(file_path: str) -> Optional[str]:
    """Detect common supported files when upstream MIME/extension data is missing."""

    try:
        with open(file_path, "rb") as handle:
            header = handle.read(16)
    except OSError:
        return None

    if header.startswith(b"%PDF"):
        return FileType.PDF.value

    try:
        from PIL import Image

        with Image.open(file_path) as image:
            image.verify()
        return FileType.IMAGE.value
    except Exception:
        return None


async def process_invoice_file(
    file_path: str,
    file_type: str,
    file_name: Optional[str] = None,
    user_id: Optional[Union[str, UUID]] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    validation_result: Optional[Dict[str, Any]] = None,
    best_effort: bool = False,
    file_metadata: Optional[Dict[str, Any]] = None,
    hitl_confirmed: bool = False,
) -> Dict[str, Any]:
    """
    Process a valid invoice file by extracting data.

    Args:
        file_path: Path to the file
        file_type: File type
        file_name: Optional original filename
        user_id: Optional user ID
        conversation_history: Optional conversation history

    Returns:
        Dict containing extracted data and response
    """
    # Extract data from invoice
    extraction_result = await extract_invoice_data(
        file_path,
        file_type,
        user_id,
        conversation_history,
        file_metadata=file_metadata,
    )

    # If extraction failed
    if "error" in extraction_result:
        logger.warning(f"Data extraction error: {extraction_result['error']}")
        return {
            "content": FILE_PROCESSING_FALLBACKS["extraction_failed"],
            "metadata": {
                "intent": IntentType.FILE_PROCESSING.value,
                "file_type": file_type,
                "error": extraction_result["error"]
            },
            "confidence": 0.4
        }

    if user_id is not None and _hitl_required() and not hitl_confirmed:
        pending_metadata = _mark_media_awaiting_approval(
            user_id=user_id,
            file_metadata=file_metadata or {},
            extraction_result=extraction_result,
            validation_result=validation_result,
        )
        extraction_result.setdefault("metadata", {}).update(pending_metadata)
        response = await format_extraction_response(extraction_result, file_name or file_path)
        return {
            "content": response.get("content", ""),
            "metadata": {
                "intent": IntentType.FILE_PROCESSING.value,
                "file_type": file_type,
                "extraction_results": extraction_result,
                "invoice_data": extraction_result.get("data", {}),
                "stored_in_database": False,
                "storage_status": "awaiting_human_confirmation",
                "hitl_required": True,
                "hitl_status": "awaiting_confirmation",
                "hitl_action": "store_extraction",
                "hitl_approval_command": pending_metadata.get("hitl_approval_command"),
                "hitl_rejection_command": pending_metadata.get("hitl_rejection_command"),
                "media_id": pending_metadata.get("media_id"),
                "best_effort_extraction": best_effort,
                "validation_result": validation_result,
            },
            "confidence": response.get("confidence", 0.7),
        }

    # Store invoice data in database after HITL confirmation
    invoice_id = None
    item_ids = []
    storage_error = None
    if user_id is not None:
        # Use the DatabaseStorageAgent to store the invoice data
        from agents.database_storage_agent import DatabaseStorageAgent

        storage_agent = DatabaseStorageAgent()

        # Convert extraction_result to JSON string to satisfy AgentInput requirements
        extraction_result.setdefault("metadata", {})["hitl_confirmed"] = True
        extraction_result_json = json.dumps(extraction_result)
        logger.info(f"Preparing to store invoice data for user_id: {user_id}, data size: {len(extraction_result_json)} bytes")

        try:
            # Create agent input with the extraction result as JSON string
            agent_input = AgentInput(
                content=extraction_result_json,
                metadata={"user_id": user_id, "hitl_confirmed": True}
            )

            # Create agent context with the user_id
            agent_context = AgentContext(user_id=str(user_id))

            # Store the invoice data
            logger.info("Calling DatabaseStorageAgent to store invoice data")
            storage_result = await storage_agent.process(agent_input, agent_context)

            # Get the invoice_id from the result if successful
            if storage_result and storage_result.status == "success" and isinstance(storage_result.content, dict):
                invoice_id = storage_result.content.get("invoice_id")
                item_ids = storage_result.content.get("item_ids", [])
                logger.info(f"✅ Successfully stored invoice data in database with ID: {invoice_id}, items: {len(item_ids)}")

                # Add invoice ID to extraction result for reference
                if "metadata" not in extraction_result:
                    extraction_result["metadata"] = {}
                extraction_result["metadata"]["invoice_id"] = invoice_id
                extraction_result["metadata"]["item_ids"] = item_ids
                if storage_result.content.get("duplicate"):
                    extraction_result["metadata"]["duplicate"] = True
                if storage_result.content.get("media_id"):
                    extraction_result["metadata"]["media_id"] = storage_result.content.get("media_id")
            else:
                error_message = storage_result.error if storage_result else "No result returned from storage agent"
                storage_error = error_message
                logger.error(f"❌ Error storing invoice data: {error_message}")
                if storage_result:
                    logger.error(f"Storage result status: {storage_result.status}, content type: {type(storage_result.content)}")
                    if isinstance(storage_result.content, dict) and "error" in storage_result.content:
                        logger.error(f"Storage error details: {storage_result.content['error']}")
        except Exception as e:
            storage_error = str(e)
            logger.exception(f"❌ Exception in database storage: {str(e)}")

    # Format successful extraction response
    response = await format_extraction_response(extraction_result, file_name or file_path)

    # Add file storage metadata if available
    file_storage = None
    if "metadata" in extraction_result:
        file_storage = extraction_result["metadata"].get("file_storage")

    # Prepare response metadata
    response_metadata = {
        "intent": IntentType.FILE_PROCESSING.value,
        "file_type": file_type,
        "extraction_results": extraction_result,
        "invoice_data": extraction_result.get("data", {}),
        "stored_in_database": bool(invoice_id),
        "storage_status": (
            "success" if invoice_id else "error" if user_id is not None else "not_attempted"
        ),
        "best_effort_extraction": best_effort,
        "duplicate": bool(
            extraction_result.get("metadata", {}).get("duplicate")
            if isinstance(extraction_result.get("metadata"), dict)
            else False
        ),
    }
    if validation_result:
        response_metadata["validation_result"] = validation_result

    if file_storage:
        response_metadata["file_storage"] = file_storage
    if storage_error:
        response_metadata["storage_error"] = storage_error

    # Add invoice ID to response metadata if available
    if invoice_id:
        response_metadata["invoice_id"] = str(invoice_id)
    if item_ids:
        response_metadata["item_ids"] = item_ids

    return {
        "content": response.get("content", ""),
        "metadata": response_metadata,
        "confidence": response.get("confidence", 0.7)
    }


async def extract_invoice_data(
    file_path: str,
    file_type: str,
    user_id: Optional[Union[str, UUID]] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    file_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Extract data from an invoice file.

    Args:
        file_path: Path to the invoice file
        file_type: Type of the file
        user_id: Optional user ID for file storage
        conversation_history: Optional conversation history

    Returns:
        Dict containing extracted invoice data
    """
    llm_factory = LLMFactory()
    agent = DataExtractorAgent(llm_factory=llm_factory)

    try:
        # Read file content
        with open(file_path, 'rb') as f:
            file_content = f.read()

        prepared_file_metadata = _prepare_file_metadata(file_path, file_metadata, file_content)
        file_storage = (
            prepared_file_metadata.get("file_storage")
            if isinstance(prepared_file_metadata.get("file_storage"), dict)
            else None
        )
        storage_error = None
        if user_id and not file_storage:
            try:
                file_mime_type, _ = mimetypes.guess_type(file_path)
                if not file_mime_type:
                    if file_type == FileType.PDF.value:
                        file_mime_type = "application/pdf"
                    elif file_type == FileType.IMAGE.value:
                        # Determine image type from extension
                        ext = os.path.splitext(file_path)[1].lower()
                        if ext == '.png':
                            file_mime_type = "image/png"
                        elif ext in ['.jpg', '.jpeg']:
                            file_mime_type = "image/jpeg"
                        else:
                            file_mime_type = "image/unknown"

                upload_metadata = {
                    "user_id": str(user_id),
                    "file_type": file_type,
                    "original_filename": os.path.basename(file_path),
                    **prepared_file_metadata,
                }

                file_storage = store_user_upload(
                    file_path=file_path,
                    file_name=os.path.basename(file_path),
                    user_id=user_id,
                    content_type=file_mime_type,
                    document_type="invoices",
                    metadata=upload_metadata,
                )
                media_record = record_media_upload(
                    user_id=user_id,
                    file_storage=file_storage,
                    status="uploaded",
                    processing_metadata={
                        "file_metadata": prepared_file_metadata,
                        "source": "extract_invoice_data",
                    },
                )
                if media_record:
                    file_storage["media_id"] = media_record.get("media_id")
                    prepared_file_metadata["media_record"] = media_record
                logger.info(
                    "Invoice file uploaded to Supabase Storage: %s",
                    file_storage.get("file_key"),
                )
            except StorageConfigurationError as e:
                storage_error = str(e)
                logger.warning("Supabase Storage is not configured: %s", storage_error)
            except Exception as e:
                storage_error = str(e)
                logger.exception("Error uploading file to Supabase Storage: %s", storage_error)

        # Create an agent context with user ID if available
        agent_context = None
        if user_id:
            agent_context = AgentContext(
                user_id=str(user_id),
                conversation_history=conversation_history or []
            )

        # Create an AgentInput object
        agent_input = AgentInput(
            content=file_content,
            file_path=file_path,
            file_name=os.path.basename(file_path),
            content_type=file_type,
            metadata={
                "file_type": file_type,
                "input_type": file_type,
                "file_storage": file_storage,
                "file_metadata": prepared_file_metadata,
            }
        )

        # Process with the properly constructed AgentInput object
        result = await agent.process(agent_input, agent_context)

        if not result:
            return {"error": "Could not extract data from the invoice"}

        extracted_data = result.content if isinstance(result.content, dict) else {}
        metadata = result.metadata or {}
        metadata["file_metadata"] = prepared_file_metadata
        if prepared_file_metadata.get("checksum_sha256"):
            metadata["checksum_sha256"] = prepared_file_metadata["checksum_sha256"]
        metadata["extraction_status"] = result.status
        metadata["extraction_confidence"] = result.confidence
        if result.error:
            metadata["extraction_error"] = result.error

        if result.error and not _has_storable_extraction_data(extracted_data):
            return {"error": result.error}

        # The content field contains the extracted data
        logger.info(f"Successfully extracted invoice data: {extracted_data.keys() if isinstance(extracted_data, dict) else 'not a dict'}")

        if file_storage:
            metadata["file_storage"] = file_storage
            logger.info("Added file storage metadata to extraction result")
        if storage_error:
            metadata["storage_error"] = storage_error

        # Return a structure that includes both the data and any metadata
        return {
            "data": extracted_data,
            "file_type": file_type,
            "file_path": file_path,
            "metadata": metadata
        }

    except Exception as e:
        logger.exception(f"Error extracting invoice data: {str(e)}")
        return {"error": f"Error extracting data: {str(e)}"}


def _supports_best_effort_extraction(file_type: str) -> bool:
    return file_type in {FileType.IMAGE.value, FileType.PDF.value}


def _should_try_best_effort_extraction(file_type: str, validation_result: Dict[str, Any]) -> bool:
    """Allow extraction only when validation was uncertain, not clearly negative."""

    if not _supports_best_effort_extraction(file_type):
        return False

    confidence = validation_result.get("confidence")
    if confidence is None:
        return False
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        return False

    reason = str(validation_result.get("reason") or "").lower()
    uncertainty_keywords = {
        "unclear",
        "blur",
        "low quality",
        "poor quality",
        "partial",
        "handwritten",
        "ledger",
        "could not determine",
        "not enough visible",
    }
    if confidence_value >= 0.7 and not any(keyword in reason for keyword in uncertainty_keywords):
        return False
    return any(keyword in reason for keyword in uncertainty_keywords) or confidence_value <= 0.35


def _hitl_required() -> bool:
    return os.environ.get("HITL_CONFIRMATION_REQUIRED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _mark_media_awaiting_approval(
    user_id: Union[str, UUID],
    file_metadata: Dict[str, Any],
    extraction_result: Dict[str, Any],
    validation_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist only approval state for an extracted upload; do not store invoice/items."""

    metadata = extraction_result.get("metadata") if isinstance(extraction_result.get("metadata"), dict) else {}
    file_storage = metadata.get("file_storage") if isinstance(metadata.get("file_storage"), dict) else {}
    if file_storage and not isinstance(file_metadata.get("file_storage"), dict):
        file_metadata["file_storage"] = file_storage
    if not file_storage and not isinstance(file_metadata.get("file_storage"), dict):
        file_storage = _build_pending_extraction_file_storage(
            user_id=user_id,
            file_metadata=file_metadata,
            extraction_result=extraction_result,
        )
        file_metadata["file_storage"] = file_storage
        extraction_result.setdefault("metadata", {})["file_storage"] = file_storage
    media_id = (
        file_storage.get("media_id")
        or (file_metadata.get("media_record") or {}).get("media_id")
        or (file_metadata.get("file_storage") or {}).get("media_id")
    )
    approval_command = f"APPROVE {media_id}" if media_id else None
    rejection_command = f"REJECT {media_id}" if media_id else None

    hitl_metadata = {
        "hitl_status": "awaiting_confirmation",
        "hitl_action": "store_extraction",
        "hitl_requested_at": datetime.utcnow().isoformat(),
        "hitl_approval_command": approval_command,
        "hitl_rejection_command": rejection_command,
        "media_id": str(media_id) if media_id else None,
    }
    if validation_result:
        hitl_metadata["validation_result"] = validation_result

    processing_metadata = {
        **hitl_metadata,
        "processing_status": "awaiting_human_confirmation",
        "pending_extraction_summary": _pending_extraction_summary(extraction_result),
        "pending_extraction_result": _pending_extraction_payload(extraction_result),
        "extraction_quality": (
            extraction_result.get("data", {}).get("extraction_quality")
            if isinstance(extraction_result.get("data"), dict)
            else None
        ),
    }
    media_record = _update_media_status(
        user_id=user_id,
        file_metadata=file_metadata,
        status="uploaded",
        processing_metadata=processing_metadata,
    )

    media_id = (
        media_id
        or (media_record or {}).get("media_id")
        or (file_metadata.get("media_record") or {}).get("media_id")
    )
    if not media_id:
        fallback_storage = _build_pending_extraction_file_storage(
            user_id=user_id,
            file_metadata=file_metadata,
            extraction_result=extraction_result,
        )
        file_metadata["file_storage"] = fallback_storage
        extraction_result.setdefault("metadata", {})["file_storage"] = fallback_storage
        processing_metadata["pending_extraction_result"] = _pending_extraction_payload(extraction_result)
        media_record = _update_media_status(
            user_id=user_id,
            file_metadata=file_metadata,
            status="uploaded",
            processing_metadata=processing_metadata,
        )
        media_id = (
            (media_record or {}).get("media_id")
            or (file_metadata.get("media_record") or {}).get("media_id")
            or fallback_storage.get("media_id")
        )
    if media_id and not hitl_metadata.get("hitl_approval_command"):
        hitl_metadata["media_id"] = str(media_id)
        hitl_metadata["hitl_approval_command"] = f"APPROVE {media_id}"
        hitl_metadata["hitl_rejection_command"] = f"REJECT {media_id}"
        if isinstance(file_metadata.get("file_storage"), dict):
            file_metadata["file_storage"]["media_id"] = str(media_id)
        _update_media_status(
            user_id=user_id,
            file_metadata=file_metadata,
            status="uploaded",
            processing_metadata={
                **processing_metadata,
                **hitl_metadata,
                "pending_extraction_result": _pending_extraction_payload(extraction_result),
            },
        )
    return hitl_metadata


def _build_pending_extraction_file_storage(
    user_id: Union[str, UUID],
    file_metadata: Dict[str, Any],
    extraction_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a registry-only file reference when private file storage failed."""

    metadata = extraction_result.get("metadata") if isinstance(extraction_result, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    nested_file_metadata = metadata.get("file_metadata") if isinstance(metadata.get("file_metadata"), dict) else {}
    checksum = (
        file_metadata.get("checksum_sha256")
        or metadata.get("checksum_sha256")
        or nested_file_metadata.get("checksum_sha256")
    )
    filename = (
        file_metadata.get("original_filename")
        or nested_file_metadata.get("original_filename")
        or os.path.basename(str(extraction_result.get("file_path") or "pending_upload"))
    )
    token = checksum or hashlib.sha256(
        f"{user_id}:{filename}:{datetime.utcnow().isoformat()}".encode("utf-8")
    ).hexdigest()
    content_type = (
        file_metadata.get("content_type")
        or nested_file_metadata.get("content_type")
        or mimetypes.guess_type(filename)[0]
        or "application/octet-stream"
    )
    storage_error = (
        file_metadata.get("storage_error")
        or metadata.get("storage_error")
        or nested_file_metadata.get("storage_error")
    )
    return {
        "provider": "metadata",
        "file_key": f"pending://{user_id}/{token}",
        "path": f"pending://{user_id}/{token}",
        "url": "",
        "content_type": content_type,
        "file_size": file_metadata.get("file_size") or nested_file_metadata.get("file_size"),
        "checksum_sha256": checksum,
        "original_filename": filename,
        "storage_class": "pending_extraction",
        "access_scope": "metadata_only",
        "storage_error": storage_error,
    }


def _pending_extraction_payload(extraction_result: Dict[str, Any]) -> Dict[str, Any]:
    """Return a JSON-safe extraction payload that can be finalized after approval."""

    try:
        return json.loads(json.dumps(extraction_result, default=str))
    except (TypeError, ValueError):
        return {
            "data": extraction_result.get("data", {}) if isinstance(extraction_result, dict) else {},
            "metadata": {},
        }


def _pending_extraction_summary(extraction_result: Dict[str, Any]) -> Dict[str, Any]:
    """Store a compact review summary without finalizing analytics rows."""

    data = extraction_result.get("data") if isinstance(extraction_result, dict) else {}
    fields = _document_response_fields(data if isinstance(data, dict) else {})
    items = [item for item in fields["items"] if isinstance(item, dict)]
    return {
        "document_type": fields["document_type"],
        "vendor_name": fields["vendor_name"],
        "transaction_date": fields["transaction_date"],
        "total_amount": fields["total_amount"],
        "currency": fields["currency"],
        "item_count": len(items),
        "item_label": "entries" if fields["is_ledger"] else "items",
        "needs_review": bool((fields.get("extraction_quality") or {}).get("needs_review")),
        "sample_items": [
            _format_item_line(item, fields["currency"], fields["is_ledger"])
            for item in items[:4]
        ],
    }


def _prepare_file_metadata(
    file_path: str,
    file_metadata: Optional[Dict[str, Any]] = None,
    file_content: Optional[bytes] = None,
) -> Dict[str, Any]:
    metadata = dict(file_metadata or {})
    if not metadata.get("checksum_sha256") and os.path.exists(file_path):
        metadata["checksum_sha256"] = _calculate_file_checksum(file_path, file_content)
    if not metadata.get("original_filename"):
        metadata["original_filename"] = os.path.basename(file_path)
    return metadata


def _store_original_upload(
    file_path: str,
    file_name: str,
    user_id: Optional[Union[str, UUID]],
    document_type: str,
    content_type: str,
    file_metadata: Dict[str, Any],
) -> None:
    """Persist the original upload before validation/extraction."""

    if not user_id:
        return

    try:
        storage_metadata = store_user_upload(
            file_path=file_path,
            file_name=file_name,
            user_id=user_id,
            document_type=document_type,
            content_type=content_type,
            metadata={
                **file_metadata,
                "user_id": str(user_id),
                "document_type": document_type,
                "storage_class": "original_upload",
            },
        )
        media_record = record_media_upload(
            user_id=user_id,
            file_storage=storage_metadata,
            status="uploaded",
            processing_metadata={
                "file_metadata": file_metadata,
                "source": file_metadata.get("source") or "direct_upload",
            },
        )
        if media_record:
            storage_metadata["media_id"] = media_record.get("media_id")
            file_metadata["media_record"] = media_record
        file_metadata["file_storage"] = storage_metadata
        logger.info(
            "Stored original upload for user=%s path=%s media_id=%s",
            user_id,
            storage_metadata.get("file_key"),
            storage_metadata.get("media_id"),
        )
    except StorageConfigurationError as exc:
        file_metadata["storage_error"] = str(exc)
        logger.warning("Original upload skipped because storage is not configured: %s", exc)
    except Exception as exc:
        file_metadata["storage_error"] = str(exc)
        logger.exception("Original upload could not be stored: %s", exc)


def _update_media_status(
    user_id: Optional[Union[str, UUID]],
    file_metadata: Dict[str, Any],
    status: str,
    processing_metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    file_storage = file_metadata.get("file_storage")
    if not user_id or not isinstance(file_storage, dict):
        return None
    media_record = record_media_upload(
        user_id=user_id,
        file_storage=file_storage,
        status=status,
        processing_metadata={
            "file_metadata": file_metadata,
            **(processing_metadata or {}),
        },
    )
    if media_record:
        file_metadata["media_record"] = media_record
        if media_record.get("media_id"):
            file_storage["media_id"] = str(media_record["media_id"])
    return media_record


def _calculate_file_checksum(file_path: str, file_content: Optional[bytes] = None) -> str:
    digest = hashlib.sha256()
    if file_content is not None:
        digest.update(file_content)
    else:
        with open(file_path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _find_existing_media_by_checksum(
    user_id: Optional[Union[str, UUID]],
    file_metadata: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    checksum = file_metadata.get("checksum_sha256")
    if not user_id or not checksum:
        return None
    try:
        user_id_value = int(str(user_id))
    except (TypeError, ValueError):
        return None

    try:
        from database.connection import get_db_session
        from database.schemas import Invoice, Media

        session = get_db_session()
        try:
            media = (
                session.query(Media)
                .filter(Media.user_id == user_id_value, Media.content_hash == checksum)
                .order_by(Media.created_at.desc())
                .first()
            )
            if media:
                metadata = media.processing_metadata if isinstance(media.processing_metadata, dict) else {}
                return {
                    "id": media.id,
                    "invoice_id": media.invoice_id,
                    "filename": media.filename,
                    "file_path": media.file_path,
                    "file_url": media.file_url,
                    "content_type": media.content_type,
                    "file_size": media.file_size,
                    "content_hash": media.content_hash,
                    "processing_metadata": metadata,
                    "created_at": media.created_at.isoformat() if media.created_at else None,
                }

            invoice_candidates = (
                session.query(Invoice)
                .filter(Invoice.user_id == user_id_value)
                .order_by(Invoice.created_at.desc())
                .limit(500)
                .all()
            )
            for invoice in invoice_candidates:
                raw_data = invoice.raw_data or {}
                if not isinstance(raw_data, dict):
                    continue
                extraction = raw_data.get("_extraction") or {}
                if not isinstance(extraction, dict):
                    continue
                file_metadata_value = extraction.get("file_metadata") or {}
                if not isinstance(file_metadata_value, dict):
                    file_metadata_value = {}
                stored_checksum = (
                    extraction.get("checksum_sha256")
                    or file_metadata_value.get("checksum_sha256")
                )
                if stored_checksum == checksum:
                    return {
                        "id": None,
                        "invoice_id": invoice.id,
                        "filename": file_metadata.get("original_filename"),
                        "file_path": "",
                        "file_url": invoice.file_url,
                        "content_type": invoice.file_content_type,
                        "file_size": None,
                        "content_hash": stored_checksum,
                        "processing_metadata": extraction,
                        "created_at": invoice.created_at.isoformat() if invoice.created_at else None,
                    }
        finally:
            session.close()
    except Exception as exc:
        logger.warning("Could not check duplicate media by checksum: %s", exc)
    return None


async def format_duplicate_file_response(
    media: Dict[str, Any],
    file_name: str,
    file_type: str,
    file_metadata: Dict[str, Any],
) -> Dict[str, Any]:
    invoice_id = media.get("invoice_id")
    media_id = media.get("id")
    media_metadata = media.get("processing_metadata") if isinstance(media.get("processing_metadata"), dict) else {}
    hitl_pending = media_metadata.get("hitl_status") == "awaiting_confirmation" and not invoice_id
    if hitl_pending:
        approval_command = media_metadata.get("hitl_approval_command") or (
            f"APPROVE {media_id}" if media_id else None
        )
        rejection_command = media_metadata.get("hitl_rejection_command") or (
            f"REJECT {media_id}" if media_id else None
        )
        lines = [
            "📄 *Document Already Pending*",
            "",
            f"*File:* {file_name}",
            "*Status:* Pending WhatsApp approval",
        ]
        if approval_command and rejection_command:
            lines.extend(
                [
                    "",
                    "🔐 *Action Needed*",
                    f"Reply *{approval_command}* to save this document.",
                    f"Reply *{rejection_command}* to discard it.",
                ]
            )
        content = compact_whatsapp_message("\n".join(lines), max_chars=700)
    else:
        lines = [
            "✅ *Document Already Processed*",
            "",
            f"*File:* {file_name}",
        ]
        if invoice_id:
            lines.append(f"*Receipt:* #{invoice_id}")
        lines.append("*Status:* No duplicate rows were created.")
        content = compact_whatsapp_message("\n".join(lines), max_chars=700)
    return {
        "content": content,
        "metadata": {
            "intent": IntentType.FILE_PROCESSING.value,
            "file_type": file_type,
            "duplicate": True,
            "stored_in_database": bool(invoice_id),
            "storage_status": "awaiting_human_confirmation" if hitl_pending else "duplicate",
            "hitl_status": "awaiting_confirmation" if hitl_pending else None,
            "hitl_approval_command": media_metadata.get("hitl_approval_command"),
            "hitl_rejection_command": media_metadata.get("hitl_rejection_command"),
            "invoice_id": str(invoice_id) if invoice_id else None,
            "media_id": str(media_id) if media_id else None,
            "file_metadata": file_metadata,
            "file_storage": media_metadata.get("file_storage") or media_metadata,
        },
        "confidence": 1.0,
    }


def _has_storable_extraction_data(data: Any) -> bool:
    """Return whether extracted data has enough signal to persist for queries."""

    if not isinstance(data, dict):
        return False

    vendor = data.get("vendor", {})
    if isinstance(vendor, dict):
        vendor_name = vendor.get("name") or vendor.get("vendor_name")
    else:
        vendor_name = vendor
    vendor_text = str(vendor_name or "").strip().lower()
    has_vendor = bool(vendor_text and vendor_text not in {"unknown", "unknown vendor", "n/a", "none"})

    transaction = data.get("transaction", {}) if isinstance(data.get("transaction"), dict) else {}
    has_reference = bool(
        transaction.get("invoice_number")
        or transaction.get("receipt_no")
        or transaction.get("date")
        or data.get("invoice_number")
        or data.get("receipt_no")
        or data.get("date")
        or data.get("invoice_date")
    )

    financial = data.get("financial", {}) if isinstance(data.get("financial"), dict) else {}
    total = _first_number(
        financial.get("total"),
        financial.get("total_amount"),
        data.get("total_amount"),
        data.get("total"),
    )
    has_total = total is not None and total > 0

    items = data.get("items") or []
    if not isinstance(items, list):
        items = []
    has_items = any(
        isinstance(item, dict)
        and (
            str(item.get("description") or item.get("name") or "").strip()
            or _first_number(item.get("total_price"), item.get("amount"), item.get("unit_price")) is not None
        )
        for item in items
    )

    return has_items or has_total or (has_vendor and has_reference)


def _first_number(*values: Any) -> Optional[float]:
    for value in values:
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _document_response_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract canonical response fields from normalized or legacy document data."""

    if not isinstance(data, dict):
        data = {}

    vendor = data.get("vendor", {})
    vendor_name = vendor.get("name") if isinstance(vendor, dict) else vendor
    vendor_name = str(vendor_name or "").strip() or "Not visible"

    transaction = data.get("transaction", {}) if isinstance(data.get("transaction"), dict) else {}
    financial = data.get("financial", {}) if isinstance(data.get("financial"), dict) else {}
    additional_info = data.get("additional_info", {}) if isinstance(data.get("additional_info"), dict) else {}
    extraction_quality = data.get("extraction_quality", {}) if isinstance(data.get("extraction_quality"), dict) else {}

    document_type = str(additional_info.get("document_type") or "").strip()
    if not document_type:
        if is_ledger_document(data):
            document_type = "handwritten_ledger"
        elif transaction.get("receipt_no"):
            document_type = "receipt"
        elif transaction.get("invoice_number") or data.get("invoice_number"):
            document_type = "invoice"
        else:
            document_type = "financial_document"

    transaction_date = (
        transaction.get("date")
        or data.get("date")
        or data.get("invoice_date")
        or "Not visible"
    )
    invoice_number = transaction.get("invoice_number") or data.get("invoice_number") or None
    receipt_no = transaction.get("receipt_no") or data.get("receipt_no") or None
    total_amount = _first_number(
        financial.get("total"),
        financial.get("total_amount"),
        data.get("total_amount"),
        data.get("total"),
    )
    currency = (
        financial.get("currency")
        or data.get("currency")
        or ("INR" if is_ledger_document(data) else "USD")
    )
    items = data.get("items") if isinstance(data.get("items"), list) else []

    return {
        "document_type": document_type,
        "vendor_name": vendor_name,
        "transaction_date": transaction_date,
        "invoice_number": invoice_number,
        "receipt_no": receipt_no,
        "total_amount": total_amount,
        "currency": str(currency or "").upper() or "USD",
        "items": items,
        "is_ledger": is_ledger_document(data),
        "extraction_quality": extraction_quality,
    }


def _format_money(value: Optional[float], currency: str) -> str:
    if value is None:
        return "Not visible"
    try:
        amount = float(value)
    except (TypeError, ValueError):
        amount_text = str(value).strip()
        return f"{amount_text} {currency}".strip()
    return f"{amount:,.2f} {currency}".strip()


def _business_label(value: Any, fallback: str = "Not visible") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    return text.replace("_", " ").replace("-", " ").title()


def _format_row_count(extraction_quality: Dict[str, Any]) -> Optional[str]:
    visible_rows = extraction_quality.get("visible_financial_rows")
    extracted_rows = extraction_quality.get("extracted_financial_rows")
    visible_count = _first_number(visible_rows)
    extracted_count = _first_number(extracted_rows)
    if visible_count is None or extracted_count is None:
        return None
    return f"{extracted_count:g} of {visible_count:g} rows extracted"


def _format_item_line(item: Dict[str, Any], currency: str, is_ledger: bool) -> str:
    description = str(item.get("description") or "Entry").strip()
    amount = _first_number(item.get("total_price"), item.get("amount"), item.get("unit_price"))
    if is_ledger:
        row_date = str(item.get("transaction_date") or item.get("raw_date") or "").strip()
        amount_text = _format_money(amount, currency)
        if row_date:
            return f"{row_date}: {description} - {amount_text}"
        return f"{description} - {amount_text}"

    quantity = coerce_number(item.get("quantity"), 1.0) or 1.0
    return f"{description} - Qty {quantity:g}, Total {_format_money(amount, currency)}"


async def format_extraction_response(
    extraction_result: Dict[str, Any],
    file_name: str
) -> Dict[str, Any]:
    """
    Format the extraction results into a user-friendly response.

    Args:
        extraction_result: The extraction results
        file_name: Original filename

    Returns:
        Dict containing the formatted response
    """
    file_storage = None
    if "metadata" in extraction_result:
        file_storage = extraction_result["metadata"].get("file_storage")

    # Get the invoice data
    invoice_data = extraction_result.get("data", {})

    fields = _document_response_fields(invoice_data)
    metadata = extraction_result.get("metadata", {}) if isinstance(extraction_result.get("metadata"), dict) else {}
    hitl_pending = metadata.get("hitl_status") == "awaiting_confirmation"
    private_file_saved = _is_private_file_storage(file_storage)
    status = (
        "awaiting WhatsApp approval"
        if hitl_pending
        else "saved"
        if metadata.get("invoice_id") or private_file_saved
        else "processed"
    )
    items = [item for item in fields["items"] if isinstance(item, dict)]
    item_label = "entries" if fields["is_ledger"] else "items"
    extraction_quality = fields.get("extraction_quality") or {}
    needs_review = bool(extraction_quality.get("needs_review"))
    status_label = (
        "Pending WhatsApp approval"
        if hitl_pending
        else "Saved to analytics"
        if status == "saved"
        else "Processed"
    )
    if needs_review:
        status_label = f"{status_label} - needs review"
    title = (
        "📄 *Document Review*"
        if hitl_pending
        else "✅ *Document Saved*"
        if status == "saved"
        else "📄 *Document Processed*"
    )
    item_label_title = "Entries" if fields["is_ledger"] else "Items"

    lines = [
        title,
        "",
        f"*Status:* {status_label}",
        f"*File:* {file_name}",
        f"*Type:* {_business_label(fields['document_type'], 'Document')}",
        f"*Vendor:* {fields['vendor_name']}",
        f"*Date:* {fields['transaction_date']}",
        f"*Total:* {_format_money(fields['total_amount'], fields['currency'])}",
        f"*{item_label_title}:* {len(items)} extracted",
    ]
    if fields["invoice_number"]:
        lines.append(f"*Invoice #:* {fields['invoice_number']}")
    if fields["receipt_no"]:
        lines.append(f"*Receipt #:* {fields['receipt_no']}")

    if extraction_quality:
        quality_lines = []
        row_count = _format_row_count(extraction_quality)
        if row_count:
            quality_lines.append(row_count)
        warnings = extraction_quality.get("warnings")
        if isinstance(warnings, list) and warnings:
            quality_lines.append(str(warnings[0]).strip()[:140])
        if quality_lines:
            lines.append("")
            lines.append("*Quality:*")
            for quality_line in quality_lines[:2]:
                lines.append(f"• {quality_line}")

    if items:
        lines.append("")
        lines.append(f"*Sample {item_label}:*")
        for index, item in enumerate(items[:4], start=1):
            lines.append(f"{index}. {_format_item_line(item, fields['currency'], fields['is_ledger'])}")
        remaining = len(items) - 4
        if remaining > 0:
            item_state = "extracted" if hitl_pending else "saved"
            lines.append(f"+ {remaining} more {item_label} {item_state}")

    lines.append("")
    if hitl_pending:
        approval_command = metadata.get("hitl_approval_command")
        rejection_command = metadata.get("hitl_rejection_command")
        lines.append("🔐 *Action Needed*")
        lines.append("Analytics have not been updated yet.")
        if approval_command and rejection_command:
            lines.append(f"Reply *{approval_command}* to save this document.")
            lines.append(f"Reply *{rejection_command}* to discard it.")
        else:
            lines.append("Approval id could not be created. Please resend this file.")
    else:
        lines.append("*Next:* Ask \"What did I spend on printing?\"")
    response = compact_whatsapp_message("\n".join(lines), max_chars=1000)
    return {
        "content": response,
        "confidence": 0.85,
    }


def _is_private_file_storage(file_storage: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(file_storage, dict):
        return False
    file_key = str(file_storage.get("file_key") or file_storage.get("path") or "")
    return not (
        file_storage.get("provider") == "metadata"
        or file_storage.get("storage_class") == "pending_extraction"
        or file_storage.get("access_scope") == "metadata_only"
        or file_key.startswith("pending://")
    )


async def format_invalid_file_response(
    validation_result: Dict[str, Any],
    file_name: str
) -> Dict[str, Any]:
    """Return a deterministic rejection message for non-financial uploads."""

    reason = str(validation_result.get("reason") or "").strip() or "This does not look like a receipt, invoice, or expense ledger."
    response = "\n".join(
        [
            "⚠️ *Document Not Processed*",
            "",
            f"*File:* {file_name}",
            f"*Reason:* {reason}",
            "",
            "Please send a receipt, invoice, bill, PDF, or handwritten expense ledger.",
        ]
    )
    return {
        "content": compact_whatsapp_message(response, max_chars=700),
        "metadata": {
            "intent": IntentType.FILE_PROCESSING.value,
            "success": False,
            "validation_result": validation_result,
        },
        "confidence": 0.8,
    }


async def format_unsupported_format_response(
    file_name: str,
    file_type: str
) -> Dict[str, Any]:
    """
    Format response for valid but unsupported file formats.

    Args:
        file_name: Original filename
        file_type: File type

    Returns:
        Dict containing the formatted response
    """
    logger.info("Unsupported file format received: %s (%s)", file_name, file_type)
    return {
        "content": FILE_PROCESSING_FALLBACKS["unsupported_format"],
        "metadata": {
            "intent": IntentType.FILE_PROCESSING.value,
            "file_name": file_name,
            "file_type": file_type,
            "success": False,
        },
        "confidence": 0.6,
    }
