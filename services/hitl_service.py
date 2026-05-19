"""Human-in-the-loop approval commands for WhatsApp workflows."""

from __future__ import annotations

import logging
import json
import mimetypes
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from langchain_app.state import IntentType
from services.conversation_policy import compact_whatsapp_message
from services.history_service import delete_user_history
from services.llm_factory import LLMFactory
from storage import StorageConfigurationError, SupabaseStorageHandler

logger = logging.getLogger(__name__)


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

    hitl_intent = await classify_hitl_intent(text, conversation_history or [])
    action = hitl_intent.get("action")
    target_id = _coerce_optional_int(hitl_intent.get("target_id"))

    if action == "approve_upload" and target_id is not None:
        return await approve_pending_extraction(user_id, target_id, conversation_history)

    if action == "reject_upload" and target_id is not None:
        return reject_pending_upload(user_id, target_id)

    if action == "confirm_delete":
        delete_payload = _delete_payload_from_intent(hitl_intent)
        if delete_payload:
            return execute_confirmed_delete(user_id, delete_payload)
        return build_delete_confirmation_prompt(hitl_intent)

    if action in {"request_delete", "select_delete_scope"}:
        return build_delete_confirmation_prompt(hitl_intent)

    return None


async def classify_hitl_intent(
    text_content: str,
    conversation_history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Use the LLM to classify HITL commands instead of local text rules."""

    try:
        llm_factory = LLMFactory()
        prompt_template = llm_factory.load_prompt_template("hitl_intent")
        prompt = (
            prompt_template
            .replace("{message}", json.dumps(text_content))
            .replace("{conversation_history}", json.dumps(conversation_history[-8:]))
        )
        raw_response = await llm_factory.agenerate_completion(
            prompt=prompt,
            temperature=0,
            max_tokens=300,
        )
        return _parse_hitl_intent_json(raw_response)
    except Exception as exc:
        logger.warning("Could not classify HITL intent with LLM: %s", exc)
        return {
            "action": "none",
            "target_scope": "unknown",
            "target_id": None,
            "confidence": 0.0,
            "reason": str(exc),
        }


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
            "\n".join(
                [
                    "✅ *Document Already Saved*",
                    "",
                    f"*Upload:* #{media_id}",
                    f"*Receipt:* #{media_info['invoice_id']}",
                ]
            ),
            {
                "intent": IntentType.FILE_PROCESSING.value,
                "hitl_status": "already_confirmed",
                "media_id": str(media_id),
                "invoice_id": str(media_info["invoice_id"]),
            },
        )

    file_storage = dict(media_info.get("file_storage") or {})
    pending_extraction_result = _pending_extraction_from_media(media_info)
    if _is_metadata_only_pending(file_storage) and pending_extraction_result:
        return await _approve_pending_extraction_payload(
            user_id=user_id,
            media_id=media_id,
            extraction_result=pending_extraction_result,
        )

    file_key = file_storage.get("file_key") or file_storage.get("path") or media_info.get("file_path")
    if not file_key:
        if pending_extraction_result:
            return await _approve_pending_extraction_payload(
                user_id=user_id,
                media_id=media_id,
                extraction_result=pending_extraction_result,
            )
        return _response(
            "\n".join(
                [
                    "⚠️ *Approval Failed*",
                    "",
                    f"*Upload:* #{media_id}",
                    "*Reason:* Stored file could not be found.",
                    "",
                    "Please resend the file.",
                ]
            ),
            {"intent": IntentType.FILE_PROCESSING.value, "hitl_status": "missing_storage", "media_id": str(media_id)},
        )

    try:
        file_bytes = SupabaseStorageHandler(bucket_name=file_storage.get("bucket")).download_file(file_key)
    except StorageConfigurationError as exc:
        logger.warning("Storage is not configured for HITL approval: %s", exc)
        return _response(
            "⚠️ *Approval Failed*\n\n*Reason:* Storage is not configured, so this upload cannot be approved yet.",
            {"intent": IntentType.FILE_PROCESSING.value, "hitl_status": "storage_not_configured", "media_id": str(media_id)},
        )
    except Exception as exc:
        logger.exception("Could not download pending upload %s for approval: %s", media_id, exc)
        if pending_extraction_result:
            return await _approve_pending_extraction_payload(
                user_id=user_id,
                media_id=media_id,
                extraction_result=pending_extraction_result,
            )
        return _response(
            f"⚠️ *Approval Failed*\n\n*Upload:* #{media_id}\n*Reason:* The stored file could not be reopened.\n\nPlease resend the file.",
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


async def _approve_pending_extraction_payload(
    user_id: Union[str, UUID, int],
    media_id: int,
    extraction_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Finalize a pending extraction saved in media metadata."""

    from agents.database_storage_agent import DatabaseStorageAgent
    from utils.base_agent import AgentContext, AgentInput

    payload = _json_safe_dict(extraction_result)
    payload.setdefault("metadata", {})
    if not isinstance(payload["metadata"], dict):
        payload["metadata"] = {}
    payload["metadata"].update({
        "hitl_confirmed": True,
        "hitl_status": "confirmed",
        "hitl_action": "store_extraction",
        "approved_media_id": str(media_id),
    })
    file_storage = payload["metadata"].get("file_storage")
    if isinstance(file_storage, dict):
        file_storage["media_id"] = str(media_id)

    storage_agent = DatabaseStorageAgent()
    storage_result = await storage_agent.process(
        AgentInput(
            content=json.dumps(payload),
            metadata={"user_id": str(user_id), "hitl_confirmed": True},
        ),
        AgentContext(user_id=str(user_id)),
    )
    content = storage_result.content if isinstance(storage_result.content, dict) else {}
    if storage_result.status == "success" and content.get("status") in {"success", "duplicate"}:
        invoice_id = content.get("invoice_id")
        item_count = len(content.get("item_ids") or [])
        lines = [
            "✅ *Document Saved*",
            "",
            f"*Upload:* #{media_id}",
            f"*Receipt:* #{invoice_id or 'existing'}",
            f"*Items:* {item_count}",
            "*Status:* Analytics updated.",
        ]
        return _response(
            "\n".join(lines),
            {
                "intent": IntentType.FILE_PROCESSING.value,
                "hitl_status": "confirmed",
                "hitl_action": "store_extraction",
                "approved_media_id": str(media_id),
                "invoice_id": str(invoice_id) if invoice_id else None,
                "item_ids": content.get("item_ids") or [],
                "media_id": str(content.get("media_id") or media_id),
                "stored_from_pending_extraction": True,
            },
        )

    error_message = storage_result.error or content.get("error") or "Could not save the pending extraction."
    return _response(
        f"⚠️ *Approval Failed*\n\n*Upload:* #{media_id}\n*Reason:* {error_message}",
        {
            "intent": IntentType.FILE_PROCESSING.value,
            "hitl_status": "store_failed",
            "media_id": str(media_id),
            "stored_from_pending_extraction": True,
        },
        confidence=0.5,
    )


def _pending_extraction_from_media(media_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    metadata = media_info.get("metadata") if isinstance(media_info.get("metadata"), dict) else {}
    value = metadata.get("pending_extraction_result")
    return value if isinstance(value, dict) else None


def _is_metadata_only_pending(file_storage: Dict[str, Any]) -> bool:
    file_key = str(file_storage.get("file_key") or file_storage.get("path") or "")
    return (
        file_storage.get("storage_class") == "pending_extraction"
        or file_storage.get("access_scope") == "metadata_only"
        or file_key.startswith("pending://")
    )


def _json_safe_dict(value: Dict[str, Any]) -> Dict[str, Any]:
    try:
        safe_value = json.loads(json.dumps(value, default=str))
        return safe_value if isinstance(safe_value, dict) else {}
    except (TypeError, ValueError):
        return {}


async def review_pending_upload_from_web(
    user_id: Union[str, UUID, int],
    media_id: int,
    action: str,
) -> Dict[str, Any]:
    """Reject website approval attempts; receipt approval is WhatsApp-only."""

    del user_id
    media_id_text = str(media_id)
    return {
        "status": "error",
        "message": (
            "🔐 *WhatsApp Approval Required*\n\n"
            f"Reply *APPROVE {media_id_text}* to save this document.\n"
            f"Reply *REJECT {media_id_text}* to discard it."
        ),
        "metadata": {
            "hitl_status": "whatsapp_required",
            "media_id": media_id_text,
            "action": action,
        },
        "media_id": media_id_text,
        "action": str(action or "").strip().lower(),
    }


def reject_pending_upload(user_id: Union[str, UUID, int], media_id: int) -> Dict[str, Any]:
    """Discard a pending upload after the user explicitly rejects it."""

    media_info = _load_user_media(user_id, media_id)
    if media_info.get("status") != "success":
        return _response(media_info["message"], media_info.get("metadata"))
    if media_info.get("invoice_id"):
        return _response(
            "\n".join(
                [
                    "✅ *Document Already Saved*",
                    "",
                    f"*Upload:* #{media_id}",
                    f"*Receipt:* #{media_info['invoice_id']}",
                    f"*To remove it:* CONFIRM DELETE RECEIPT {media_info['invoice_id']}",
                ]
            ),
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
            f"🗑️ *Upload Discarded*\n\n*Upload:* #{media_id}\n*Status:* No invoice or analytics rows were created.",
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
                    "✅ *Deletion Confirmed*",
                    "",
                    f"*Receipts deleted:* {deleted.get('documents', 0)}",
                    f"*Uploads deleted:* {deleted.get('media', 0)}",
                    f"*Generated invoices deleted:* {deleted.get('generated_invoices', 0)}",
                    f"*Stored files deleted:* {deleted.get('storage_files', 0)}",
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


def build_delete_confirmation_prompt(hitl_intent: Dict[str, Any]) -> Dict[str, Any]:
    """Ask the user for an exact WhatsApp confirmation before deleting data."""

    payload, command, label = _confirmation_details_from_intent(hitl_intent)
    if payload is None:
        return _response(
            "\n".join(
                [
                    "⚠️ *Deletion Needs Confirmation*",
                    "",
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
                "⚠️ *Deletion Needs WhatsApp Confirmation*",
                "",
                f"*Target:* {label}",
                f"*Reply exactly:* {command}",
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


def _delete_payload_from_intent(hitl_intent: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    payload, _, _ = _confirmation_details_from_intent(hitl_intent)
    return payload


def _confirmation_details_from_intent(
    hitl_intent: Dict[str, Any],
) -> tuple[Optional[Dict[str, Any]], Optional[str], str]:
    scope = hitl_intent.get("target_scope")
    target_id = _coerce_optional_int(hitl_intent.get("target_id"))

    if scope == "all":
        return {"scope": "all"}, "CONFIRM DELETE ALL", "all saved records for this linked WhatsApp user"
    if scope == "receipt" and target_id is not None:
        return (
            {"scope": "document", "kind": "invoice", "id": target_id},
            f"CONFIRM DELETE RECEIPT {target_id}",
            f"receipt #{target_id}",
        )
    if scope == "upload" and target_id is not None:
        return (
            {"scope": "document", "kind": "media", "id": target_id},
            f"CONFIRM DELETE UPLOAD {target_id}",
            f"upload #{target_id}",
        )
    if scope == "generated_invoice" and target_id is not None:
        return (
            {"scope": "generated_invoice", "id": target_id},
            f"CONFIRM DELETE GENERATED {target_id}",
            f"generated invoice #{target_id}",
        )
    return None, None, ""


def _parse_hitl_intent_json(raw_response: str) -> Dict[str, Any]:
    start = raw_response.find("{")
    end = raw_response.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("HITL intent response did not contain a JSON object")
    parsed = json.loads(raw_response[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("HITL intent response was not a JSON object")
    return {
        "action": parsed.get("action") or "none",
        "target_scope": parsed.get("target_scope") or "unknown",
        "target_id": parsed.get("target_id"),
        "confidence": parsed.get("confidence", 0.0),
        "reason": parsed.get("reason", ""),
    }


def _coerce_optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
