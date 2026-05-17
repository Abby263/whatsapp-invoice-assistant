"""Human-in-the-loop approval commands for WhatsApp workflows."""

from __future__ import annotations

import logging
import mimetypes
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from langchain_app.state import IntentType
from services.conversation_policy import compact_whatsapp_message, is_history_deletion_request
from services.history_service import delete_user_history
from storage import StorageConfigurationError, SupabaseStorageHandler

logger = logging.getLogger(__name__)

APPROVAL_RE = re.compile(
    r"^\s*(?:approve|save|confirm)\s+(?:upload\s+|receipt\s+|media\s+|file\s+)?(?P<id>\d+)\s*$",
    re.IGNORECASE,
)
REJECTION_RE = re.compile(
    r"^\s*(?:reject|discard|ignore)\s+(?:upload\s+|receipt\s+|media\s+|file\s+)?(?P<id>\d+)\s*$",
    re.IGNORECASE,
)
CONFIRM_DELETE_RE = re.compile(
    r"^\s*confirm\s+delete\s+(?P<target>all|receipt|invoice|document|upload|file|media|generated(?:\s+invoice)?)"
    r"(?:\s+#?(?P<id>\d+))?\s*$",
    re.IGNORECASE,
)


async def handle_human_confirmation_message(
    text_content: str,
    user_id: Optional[Union[str, UUID, int]],
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Return a HITL response when a WhatsApp text is an approval command."""

    text = (text_content or "").strip()
    if not text:
        return None
    if user_id is None:
        return None

    approved_media_id = _extract_id(APPROVAL_RE, text)
    if approved_media_id is not None:
        return await approve_pending_extraction(user_id, approved_media_id, conversation_history)

    rejected_media_id = _extract_id(REJECTION_RE, text)
    if rejected_media_id is not None:
        return reject_pending_upload(user_id, rejected_media_id)

    confirmed_delete_payload = _parse_confirm_delete_command(text)
    if confirmed_delete_payload is not None:
        if confirmed_delete_payload.get("scope") == "invalid_confirmation":
            return build_delete_confirmation_prompt(text)
        return execute_confirmed_delete(user_id, confirmed_delete_payload)

    if is_history_deletion_request(text):
        return build_delete_confirmation_prompt(text)

    return None


async def approve_pending_extraction(
    user_id: Union[str, UUID, int],
    media_id: int,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Reprocess a pending upload and store extracted rows after WhatsApp approval."""

    media_info = _load_user_media(user_id, media_id)
    if media_info.get("status") != "success":
        return _response(media_info["message"], media_info.get("metadata"))

    if media_info.get("invoice_id"):
        return _response(
            f"Upload #{media_id} is already saved as receipt #{media_info['invoice_id']}.",
            {
                "intent": IntentType.FILE_PROCESSING.value,
                "hitl_status": "already_confirmed",
                "media_id": str(media_id),
                "invoice_id": str(media_info["invoice_id"]),
            },
        )

    file_storage = dict(media_info.get("file_storage") or {})
    file_key = file_storage.get("file_key") or file_storage.get("path") or media_info.get("file_path")
    if not file_key:
        return _response(
            f"I could not find the stored file path for upload #{media_id}. Please upload it again.",
            {"intent": IntentType.FILE_PROCESSING.value, "hitl_status": "missing_storage", "media_id": str(media_id)},
        )

    try:
        file_bytes = SupabaseStorageHandler(bucket_name=file_storage.get("bucket")).download_file(file_key)
    except StorageConfigurationError as exc:
        logger.warning("Storage is not configured for HITL approval: %s", exc)
        return _response(
            "Storage is not configured, so I cannot approve this upload yet.",
            {"intent": IntentType.FILE_PROCESSING.value, "hitl_status": "storage_not_configured", "media_id": str(media_id)},
        )
    except Exception as exc:
        logger.exception("Could not download pending upload %s for approval: %s", media_id, exc)
        return _response(
            f"I could not reopen upload #{media_id}. Please resend the file.",
            {"intent": IntentType.FILE_PROCESSING.value, "hitl_status": "download_failed", "media_id": str(media_id)},
        )

    file_name = media_info.get("original_filename") or media_info.get("filename") or f"upload_{media_id}"
    suffix = Path(file_name).suffix or mimetypes.guess_extension(media_info.get("content_type") or "") or ".bin"
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(file_bytes)
            temp_path = handle.name

        from langchain_app.file_processing_workflow import detect_file_type, process_invoice_file

        file_type = detect_file_type(temp_path, media_info.get("content_type") or "")
        file_metadata = {
            **(media_info.get("file_metadata") or {}),
            "file_storage": file_storage,
            "checksum_sha256": media_info.get("content_hash"),
            "original_filename": file_name,
            "media_record": {"media_id": str(media_id)},
            "source": "hitl_whatsapp_approval",
        }

        result = await process_invoice_file(
            temp_path,
            file_type,
            file_name,
            user_id,
            conversation_history or [],
            validation_result=media_info.get("validation_result"),
            file_metadata=file_metadata,
            hitl_confirmed=True,
        )
        result.setdefault("metadata", {})
        result["metadata"].update({
            "hitl_status": "confirmed",
            "hitl_action": "store_extraction",
            "approved_media_id": str(media_id),
        })
        if result.get("content"):
            result["content"] = compact_whatsapp_message(result["content"], max_chars=1000)
        return result
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                logger.debug("Temporary HITL file already removed: %s", temp_path)


def reject_pending_upload(user_id: Union[str, UUID, int], media_id: int) -> Dict[str, Any]:
    """Discard a pending upload after the user explicitly rejects it."""

    media_info = _load_user_media(user_id, media_id)
    if media_info.get("status") != "success":
        return _response(media_info["message"], media_info.get("metadata"))
    if media_info.get("invoice_id"):
        return _response(
            f"Upload #{media_id} is already saved as receipt #{media_info['invoice_id']}. Use CONFIRM DELETE RECEIPT {media_info['invoice_id']} if you want it removed.",
            {
                "intent": IntentType.FILE_PROCESSING.value,
                "hitl_status": "already_confirmed",
                "media_id": str(media_id),
                "invoice_id": str(media_info["invoice_id"]),
            },
        )

    result = delete_user_history(
        int(str(user_id)),
        {"scope": "document", "kind": "media", "id": media_id, "confirmed": True},
    )
    if result.get("status") == "success":
        return _response(
            f"Upload #{media_id} was discarded. No invoice or analytics rows were created.",
            {
                "intent": IntentType.FILE_PROCESSING.value,
                "hitl_status": "rejected",
                "media_id": str(media_id),
                "deleted": result.get("deleted"),
            },
        )
    return _response(
        result.get("message") or f"Could not discard upload #{media_id}.",
        {
            "intent": IntentType.FILE_PROCESSING.value,
            "hitl_status": "reject_failed",
            "media_id": str(media_id),
            "delete_result": result,
        },
        confidence=0.6,
    )


def execute_confirmed_delete(user_id: Union[str, UUID, int], payload: Dict[str, Any]) -> Dict[str, Any]:
    """Delete user data only after an exact WhatsApp confirmation command."""

    confirmed_payload = {**payload, "confirmed": True}
    result = delete_user_history(int(str(user_id)), confirmed_payload)
    if result.get("status") == "success":
        deleted = result.get("deleted") or {}
        return _response(
            "\n".join(
                [
                    "Deletion confirmed.",
                    f"receipts.deleted: {deleted.get('documents', 0)}",
                    f"uploads.deleted: {deleted.get('media', 0)}",
                    f"generated_invoices.deleted: {deleted.get('generated_invoices', 0)}",
                    f"stored_files.deleted: {deleted.get('storage_files', 0)}",
                ]
            ),
            {
                "intent": IntentType.GENERAL.value,
                "scope": "history_deletion",
                "delete_result": result,
            },
        )
    return _response(
        result.get("message") or "Deletion could not be completed.",
        {
            "intent": IntentType.GENERAL.value,
            "scope": "history_deletion",
            "delete_result": result,
        },
        confidence=0.6,
    )


def build_delete_confirmation_prompt(text_content: str) -> Dict[str, Any]:
    """Ask the user for an exact WhatsApp confirmation before deleting data."""

    payload, command, label = _parse_delete_request(text_content)
    if payload is None:
        return _response(
            "\n".join(
                [
                    "Deletion needs confirmation.",
                    "Reply with one exact command:",
                    "CONFIRM DELETE ALL",
                    "CONFIRM DELETE RECEIPT <id>",
                    "CONFIRM DELETE UPLOAD <id>",
                    "CONFIRM DELETE GENERATED <id>",
                ]
            ),
            {
                "intent": IntentType.GENERAL.value,
                "scope": "history_deletion",
                "confirmation_required": True,
            },
        )

    return _response(
        "\n".join(
            [
                "Deletion needs WhatsApp confirmation.",
                f"target: {label}",
                f"Reply exactly: {command}",
            ]
        ),
        {
            "intent": IntentType.GENERAL.value,
            "scope": "history_deletion",
            "confirmation_required": True,
            "confirmation_command": command,
            "delete_payload": payload,
        },
    )


def _load_user_media(user_id: Union[str, UUID, int], media_id: int) -> Dict[str, Any]:
    try:
        user_id_value = int(str(user_id))
    except (TypeError, ValueError):
        return {
            "status": "error",
            "message": "I need a linked WhatsApp user before approving uploads.",
            "metadata": {"hitl_status": "missing_user"},
        }

    try:
        from database.connection import ensure_application_schema, get_db_session
        from database.schemas import Media

        ensure_application_schema()
        session = get_db_session()
        try:
            media = (
                session.query(Media)
                .filter(Media.id == int(media_id), Media.user_id == user_id_value)
                .first()
            )
            if not media:
                return {
                    "status": "not_found",
                    "message": f"I could not find upload #{media_id} for your WhatsApp account.",
                    "metadata": {"hitl_status": "not_found", "media_id": str(media_id)},
                }
            metadata = media.processing_metadata if isinstance(media.processing_metadata, dict) else {}
            file_storage = metadata.get("file_storage") if isinstance(metadata.get("file_storage"), dict) else {}
            file_storage = {
                **file_storage,
                "file_key": file_storage.get("file_key") or media.file_path,
                "path": file_storage.get("path") or media.file_path,
                "url": file_storage.get("url") or media.file_url,
                "content_type": file_storage.get("content_type") or media.content_type,
                "file_size": file_storage.get("file_size") or media.file_size,
                "checksum_sha256": file_storage.get("checksum_sha256") or media.content_hash,
                "original_filename": file_storage.get("original_filename") or media.original_filename or media.filename,
                "media_id": str(media.id),
            }
            return {
                "status": "success",
                "media_id": media.id,
                "invoice_id": media.invoice_id,
                "filename": media.filename,
                "original_filename": media.original_filename,
                "file_path": media.file_path,
                "file_url": media.file_url,
                "content_type": media.content_type,
                "content_hash": media.content_hash,
                "file_storage": file_storage,
                "file_metadata": metadata.get("file_metadata") if isinstance(metadata.get("file_metadata"), dict) else {},
                "validation_result": metadata.get("validation_result") if isinstance(metadata.get("validation_result"), dict) else None,
                "metadata": metadata,
            }
        finally:
            session.close()
    except Exception as exc:
        logger.exception("Could not load media %s for HITL command: %s", media_id, exc)
        return {
            "status": "error",
            "message": "I could not load that upload right now. Please try again.",
            "metadata": {"hitl_status": "load_failed", "media_id": str(media_id)},
        }


def _parse_confirm_delete_command(text: str) -> Optional[Dict[str, Any]]:
    match = CONFIRM_DELETE_RE.match(text or "")
    if not match:
        return None
    target = " ".join(match.group("target").lower().split())
    record_id = match.group("id")
    if target == "all":
        return {"scope": "all"}
    if target in {"receipt", "invoice", "document"} and record_id:
        return {"scope": "document", "kind": "invoice", "id": record_id}
    if target in {"upload", "file", "media"} and record_id:
        return {"scope": "document", "kind": "media", "id": record_id}
    if target in {"generated", "generated invoice"} and record_id:
        return {"scope": "generated_invoice", "id": record_id}
    return {"scope": "invalid_confirmation"}


def _parse_delete_request(text: str) -> tuple[Optional[Dict[str, Any]], Optional[str], str]:
    normalized = " ".join((text or "").lower().split())
    record_id = _first_int(normalized)

    if "generated" in normalized and record_id:
        return (
            {"scope": "generated_invoice", "id": record_id},
            f"CONFIRM DELETE GENERATED {record_id}",
            f"generated invoice #{record_id}",
        )
    if any(term in normalized for term in ("upload", "file", "media")) and record_id:
        return (
            {"scope": "document", "kind": "media", "id": record_id},
            f"CONFIRM DELETE UPLOAD {record_id}",
            f"upload #{record_id}",
        )
    if any(term in normalized for term in ("receipt", "invoice", "document")) and record_id:
        return (
            {"scope": "document", "kind": "invoice", "id": record_id},
            f"CONFIRM DELETE RECEIPT {record_id}",
            f"receipt #{record_id}",
        )
    if any(term in normalized for term in ("all", "history", "everything", "data")):
        return {"scope": "all"}, "CONFIRM DELETE ALL", "all saved data for this linked WhatsApp user"
    return None, None, ""


def _extract_id(pattern: re.Pattern[str], text: str) -> Optional[int]:
    match = pattern.match(text or "")
    if not match:
        return None
    try:
        return int(match.group("id"))
    except (TypeError, ValueError):
        return None


def _first_int(text: str) -> Optional[str]:
    match = re.search(r"\b(\d+)\b", text or "")
    return match.group(1) if match else None


def _response(
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
    confidence: float = 0.95,
) -> Dict[str, Any]:
    return {
        "content": compact_whatsapp_message(content, max_chars=900),
        "confidence": confidence,
        "metadata": metadata or {},
    }
