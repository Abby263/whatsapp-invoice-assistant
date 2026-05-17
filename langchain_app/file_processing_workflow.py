"""
File Processing Workflow for WhatsApp Invoice Assistant.

This module implements specialized workflow for handling file inputs,
validating invoice files, extracting data, and formatting responses.
"""

import logging
import os
import hashlib
from typing import Dict, Any, Optional, List, Union, BinaryIO
from uuid import UUID
from pathlib import Path
from datetime import datetime
import uuid
import json
import tempfile
import asyncio
import mimetypes

from sqlalchemy.orm import Session

from agents.file_validator import FileValidatorAgent
from agents.data_extractor import DataExtractorAgent
from agents.response_formatter import ResponseFormatterAgent
from services.llm_factory import LLMFactory
from langchain_app.state import IntentType, FileType
from utils.base_agent import AgentInput, AgentContext
from constants.fallback_messages import FILE_PROCESSING_FALLBACKS
from storage import StorageConfigurationError, SupabaseStorageHandler

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

    # Validate the file
    validation_result = await validate_file(file_path, normalized_file_type)

    if not validation_result.get("is_valid", False):
        logger.warning(f"Invalid file: {validation_result.get('reason', 'Unknown reason')}")
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
    if _supports_best_effort_extraction(normalized_file_type):
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

    # Handle non-invoice but valid files
    return await format_unsupported_format_response(file_name or file_path, normalized_file_type)


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

    # Store invoice data in database
    invoice_id = None
    item_ids = []
    storage_error = None
    if user_id is not None:
        # Use the DatabaseStorageAgent to store the invoice data
        from agents.database_storage_agent import DatabaseStorageAgent

        storage_agent = DatabaseStorageAgent()

        # Convert extraction_result to JSON string to satisfy AgentInput requirements
        extraction_result_json = json.dumps(extraction_result)
        logger.info(f"Preparing to store invoice data for user_id: {user_id}, data size: {len(extraction_result_json)} bytes")

        try:
            # Create agent input with the extraction result as JSON string
            agent_input = AgentInput(
                content=extraction_result_json,
                metadata={"user_id": user_id}
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
        response_metadata["s3_storage"] = file_storage  # Backward-compatible UI key.
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
        file_storage = None
        storage_error = None
        if user_id:
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

                storage_handler = SupabaseStorageHandler()
                file_storage = storage_handler.upload_file(
                    file_content=file_content,
                    file_name=os.path.basename(file_path),
                    user_id=user_id,
                    content_type=file_mime_type,
                    file_type="invoices",
                    metadata=upload_metadata
                )
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
            candidates = (
                session.query(Media)
                .filter(Media.user_id == user_id_value)
                .order_by(Media.created_at.desc())
                .limit(500)
                .all()
            )
            for media in candidates:
                metadata = media.processing_metadata or {}
                if not isinstance(metadata, dict):
                    continue
                stored_checksum = (
                    getattr(media, "content_hash", None)
                    or metadata.get("checksum_sha256")
                    or metadata.get("metadata", {}).get("checksum_sha256")
                )
                if stored_checksum == checksum:
                    return {
                        "id": media.id,
                        "invoice_id": media.invoice_id,
                        "filename": media.filename,
                        "file_path": media.file_path,
                        "file_url": media.file_url,
                        "content_type": media.content_type,
                        "file_size": media.file_size,
                        "content_hash": stored_checksum,
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
    content = (
        f"I already processed {file_name} earlier."
        + (f" It is linked to invoice #{invoice_id}." if invoice_id else "")
    )
    return {
        "content": content,
        "metadata": {
            "intent": IntentType.FILE_PROCESSING.value,
            "file_type": file_type,
            "duplicate": True,
            "stored_in_database": True,
            "storage_status": "duplicate",
            "invoice_id": str(invoice_id) if invoice_id else None,
            "media_id": str(media.get("id")) if media.get("id") else None,
            "file_metadata": file_metadata,
            "file_storage": media.get("processing_metadata") or {},
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
    llm_factory = LLMFactory()
    agent = ResponseFormatterAgent(llm_factory=llm_factory)

    file_storage = None
    if "metadata" in extraction_result:
        file_storage = (
            extraction_result["metadata"].get("file_storage")
            or extraction_result["metadata"].get("s3_storage")
        )

    # Get the invoice data
    invoice_data = extraction_result.get("data", {})

    # Check for sample data flag in the raw extraction metadata
    is_sample_data = False

    # Check if this is sample data
    if "file_path" in extraction_result and isinstance(invoice_data, dict):
        file_path = extraction_result.get("file_path", "")
        if "is_sample_data" in extraction_result:
            is_sample_data = extraction_result.get("is_sample_data", False)
        # Also check the data directly, which might come from the DataExtractorAgent
        elif "metadata" in extraction_result and isinstance(extraction_result["metadata"], dict):
            is_sample_data = extraction_result["metadata"].get("is_sample_data", False)

    # Use a specialized function to create a formatted response from the invoice data
    def create_formatted_response(data, file_url=None):
        vendor = data.get("vendor", {})
        vendor_name = vendor.get("name", "Unknown Vendor") if isinstance(vendor, dict) else vendor
        additional_info = data.get("additional_info", {})
        document_type = (
            additional_info.get("document_type")
            if isinstance(additional_info, dict)
            else ""
        )
        is_ledger = "ledger" in str(document_type or "").lower()

        transaction = data.get("transaction", {})
        invoice_number = transaction.get("invoice_number", "Unknown") if isinstance(transaction, dict) else None
        date = transaction.get("date", "Unknown Date") if isinstance(transaction, dict) else data.get("date", "Unknown Date")
        due_date = transaction.get("due_date", "Unknown") if isinstance(transaction, dict) else data.get("due_date", "Unknown")

        financial = data.get("financial", {})
        if isinstance(financial, dict):
            total = financial.get("total", 0)
            currency = financial.get("currency", "USD")
        else:
            total = data.get("total_amount", 0)
            currency = data.get("currency", "USD")

        items = data.get("items", [])

        items_text = ""
        if items and len(items) > 0:
            label = "Ledger entries" if is_ledger else "Items"
            items_text = f"\n\n📋 {label}:"
            visible_items = items[:8]
            for item in visible_items:
                if not isinstance(item, dict):
                    continue
                description = item.get("description", "Item")
                quantity = item.get("quantity", 1)
                unit_price = item.get("unit_price", 0)
                total_price = item.get("total_price", 0)
                items_text += f"\n- {description}: {quantity} x {unit_price} {currency} = {total_price} {currency}"
            remaining = len(items) - len(visible_items)
            if remaining > 0:
                items_text += f"\n- ...and {remaining} more saved entries."

        document_label = "ledger page" if is_ledger else "invoice"
        response = f"✅ I've successfully processed your {document_label} from {file_name}!\n\n"
        response += f"🏢 Vendor: {vendor_name}\n" if not is_ledger else ""
        if invoice_number and invoice_number != "Unknown":
            response += f"📝 Invoice #{invoice_number}\n"
        response += f"💰 Total: {total} {currency}\n"
        if date and date != "Unknown Date":
            response += f"📅 Dated: {date}\n"
        if due_date and due_date != "Unknown":
            response += f"⏱️ Due by: {due_date}"
        response += items_text

        if file_url:
            response += f"\n\n🔗 Your invoice has been saved and is available here."

        return response

    # For sample data, use a templated response
    if is_sample_data:
        logger.info(f"Using templated response for sample invoice data")
        file_url = file_storage.get("url") if file_storage else None
        response = create_formatted_response(invoice_data, file_url)

        return {
            "content": response,
            "confidence": 0.9
        }

    # Create a proper AgentInput object with file storage info if available
    metadata = {
        "intent": IntentType.FILE_PROCESSING.value,
        "extraction_result": extraction_result,
        "file_name": file_name,
        "response_type": "invoice_summary"  # Specify the type of response we want
    }

    if file_storage:
        metadata["file_storage"] = file_storage
        metadata["s3_storage"] = file_storage

    agent_input = AgentInput(
        content="Format invoice extraction response",
        metadata=metadata
    )

    try:
        # First attempt with the ResponseFormatterAgent
        result = await agent.process(agent_input)

        # Only proceed if we got some response content
        if result and hasattr(result, "content") and result.content:
            # Validate the response quality using LLM-based validation
            validation_context = {
                "invoice_data": invoice_data,
                "has_file_storage": file_storage is not None
            }

            validation_result = await llm_factory.validate_response(
                response_content=result.content,
                response_type="invoice_summary",
                context=validation_context
            )

            # Check if the response is valid based on validation results
            if validation_result.get("is_valid", False) and validation_result.get("confidence", 0) >= 0.6:
                logger.info(f"Response validation successful: {validation_result.get('confidence')}")
                return {
                    "content": result.content,
                    "confidence": result.confidence
                }
            else:
                # Log why validation failed
                issues = validation_result.get("issues", [])
                logger.warning(f"Response validation failed: {', '.join(issues)}")
        else:
            logger.warning("ResponseFormatterAgent returned no content")

        # If validation failed or no content was returned, use our fallback formatter
        file_url = file_storage.get("url") if file_storage else None
        response = create_formatted_response(invoice_data, file_url)

        return {
            "content": response,
            "confidence": 0.8
        }

    except Exception as e:
        logger.exception(f"Error formatting extraction response: {str(e)}")

        # Create a response using our helper function as fallback
        file_url = file_storage.get("url") if file_storage else None
        response = create_formatted_response(invoice_data, file_url)

        return {
            "content": response,
            "confidence": 0.7
        }


async def format_invalid_file_response(
    validation_result: Dict[str, Any],
    file_name: str
) -> Dict[str, Any]:
    """
    Format response for invalid files.

    Args:
        validation_result: Validation results containing error reason
        file_name: Original filename

    Returns:
        Dict containing the formatted response
    """
    llm_factory = LLMFactory()
    agent = ResponseFormatterAgent(llm_factory=llm_factory)

    # Create a proper AgentInput object
    agent_input = AgentInput(
        content="Format invalid file response",
        metadata={
            "intent": IntentType.FILE_PROCESSING.value,
            "validation_result": validation_result,
            "file_name": file_name,
            "response_type": "error",  # Specify the type of response we want
            "error_type": "file_validation_error"  # Provide more context for the formatter
        }
    )

    try:
        # Generate response with the formatter agent
        result = await agent.process(agent_input)

        # Only proceed if we got some response content
        if result and hasattr(result, "content") and result.content:
            # Validate the response quality using LLM-based validation
            validation_context = {
                "validation_result": validation_result,
                "error_reason": validation_result.get("reason", "Unknown error"),
                "file_name": file_name
            }

            validation_result = await llm_factory.validate_response(
                response_content=result.content,
                response_type="error",
                context=validation_context
            )

            # Check if the response is valid based on validation results
            if validation_result.get("is_valid", False) and validation_result.get("confidence", 0) >= 0.6:
                logger.info(f"Error response validation successful: {validation_result.get('confidence')}")
                return {
                    "content": result.content,
                    "confidence": result.confidence
                }
            else:
                # Log why validation failed
                issues = validation_result.get("issues", [])
                logger.warning(f"Error response validation failed: {', '.join(issues)}")
        else:
            logger.warning("ResponseFormatterAgent returned no content for error response")

        # Fallback response if formatter failed or validation failed
        reason = validation_result.get("reason", "Unknown error")
        response = FILE_PROCESSING_FALLBACKS["invalid_file"]

        return {
            "content": response,
            "confidence": 0.6
        }

    except Exception as e:
        logger.exception(f"Error formatting invalid file response: {str(e)}")
        return {
            "content": FILE_PROCESSING_FALLBACKS["invalid_file"],
            "metadata": {"intent": IntentType.FILE_PROCESSING.value, "success": False},
            "confidence": 0.5
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
