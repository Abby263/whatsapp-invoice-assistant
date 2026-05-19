"""User-scoped history listing and deletion helpers."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import func, or_

from storage import StorageConfigurationError, SupabaseStorageHandler

logger = logging.getLogger(__name__)


def list_user_history(user_id: int, limit: int = 50) -> Dict[str, Any]:
    """Return receipt/media and generated-invoice history for one user."""

    from database.connection import get_db_session, ensure_application_schema
    from database.schemas import GeneratedInvoice, Invoice, Item, Media

    ensure_application_schema()
    limit = max(1, min(int(limit or 50), 200))
    session = get_db_session()
    try:
        invoices = (
            session.query(Invoice)
            .filter(Invoice.user_id == user_id)
            .order_by(Invoice.created_at.desc())
            .limit(limit)
            .all()
        )
        invoice_ids = [invoice.id for invoice in invoices]
        item_counts = dict(
            session.query(Item.invoice_id, func.count(Item.id))
            .filter(Item.invoice_id.in_(invoice_ids))
            .group_by(Item.invoice_id)
            .all()
        ) if invoice_ids else {}
        media_by_invoice: Dict[int, List[Any]] = {}
        if invoice_ids:
            for media in (
                session.query(Media)
                .filter(Media.user_id == user_id, Media.invoice_id.in_(invoice_ids))
                .order_by(Media.created_at.desc())
                .all()
            ):
                if media.invoice_id is not None:
                    media_by_invoice.setdefault(media.invoice_id, []).append(media)

        documents = [
            _serialize_invoice_document(
                invoice,
                media_by_invoice.get(invoice.id, []),
                item_counts.get(invoice.id, 0),
            )
            for invoice in invoices
        ]

        media_only = (
            session.query(Media)
            .filter(
                Media.user_id == user_id,
                Media.invoice_id.is_(None),
                or_(Media.status.is_(None), Media.status != "error"),
            )
            .order_by(Media.created_at.desc())
            .limit(limit)
            .all()
        )
        documents.extend(_serialize_media_document(media) for media in media_only)
        documents.sort(key=lambda row: row.get("created_at") or "", reverse=True)
        documents = documents[:limit]

        generated = (
            session.query(GeneratedInvoice)
            .filter(GeneratedInvoice.user_id == user_id)
            .order_by(GeneratedInvoice.created_at.desc())
            .limit(limit)
            .all()
        )

        return {
            "status": "success",
            "documents": documents,
            "generated_invoices": [_serialize_generated_invoice(invoice) for invoice in generated],
            "counts": {
                "documents": len(documents),
                "generated_invoices": len(generated),
            },
        }
    finally:
        session.close()


def delete_user_history(user_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Delete one user-owned history record or a scoped set of history records."""

    from database.connection import get_db_session, ensure_application_schema
    from database.schemas import (
        Conversation,
        GeneratedInvoice,
        GeneratedInvoiceItem,
        Invoice,
        InvoiceEmbedding,
        Item,
        Media,
        Message,
        Usage,
        WhatsAppMessage,
    )

    ensure_application_schema()
    scope = str(payload.get("scope") or "document").strip().lower()
    kind = str(payload.get("kind") or "").strip().lower()
    record_id = payload.get("id")

    if payload.get("confirmed") is not True:
        return {
            "status": "needs_confirmation",
            "message": "Deletion requires explicit human confirmation before anything is removed.",
            "confirmation_required": True,
            "scope": scope,
            "kind": kind,
            "id": record_id,
        }

    session = get_db_session()
    try:
        invoice_ids: List[int] = []
        media_ids: List[int] = []
        generated_ids: List[int] = []
        delete_conversation = False
        delete_usage = False

        if scope in {"all", "receipts", "documents"}:
            invoice_ids.extend(
                row[0]
                for row in session.query(Invoice.id)
                .filter(Invoice.user_id == user_id)
                .all()
            )
            media_ids.extend(
                row[0]
                for row in session.query(Media.id)
                .filter(Media.user_id == user_id)
                .all()
            )

        if scope in {"all", "generated", "generated_invoices"}:
            generated_ids.extend(
                row[0]
                for row in session.query(GeneratedInvoice.id)
                .filter(GeneratedInvoice.user_id == user_id)
                .all()
            )

        if scope == "document":
            if kind == "invoice":
                invoice_id = _coerce_int(record_id, "invoice id")
                invoice = (
                    session.query(Invoice)
                    .filter(Invoice.id == invoice_id, Invoice.user_id == user_id)
                    .first()
                )
                if not invoice:
                    return {"status": "not_found", "message": "Receipt not found"}
                invoice_ids.append(invoice.id)
            elif kind == "media":
                media_id = _coerce_int(record_id, "media id")
                media = (
                    session.query(Media)
                    .filter(Media.id == media_id, Media.user_id == user_id)
                    .first()
                )
                if not media:
                    return {"status": "not_found", "message": "Upload not found"}
                media_ids.append(media.id)
            else:
                raise ValueError("Document deletion requires kind=invoice or kind=media")

        if scope in {"generated_invoice", "generated"} and record_id is not None:
            generated_id = _coerce_int(record_id, "generated invoice id")
            generated_invoice = (
                session.query(GeneratedInvoice)
                .filter(GeneratedInvoice.id == generated_id, GeneratedInvoice.user_id == user_id)
                .first()
            )
            if not generated_invoice:
                return {"status": "not_found", "message": "Generated invoice not found"}
            generated_ids.append(generated_invoice.id)

        if scope in {"all", "conversation", "messages"}:
            delete_conversation = True
        if scope in {"all", "usage"}:
            delete_usage = True

        invoice_ids = _unique_ints(invoice_ids)
        media_ids = _unique_ints(media_ids)
        generated_ids = _unique_ints(generated_ids)

        media_query = session.query(Media).filter(Media.user_id == user_id)
        media_filters = []
        if invoice_ids:
            media_filters.append(Media.invoice_id.in_(invoice_ids))
        if media_ids:
            media_filters.append(Media.id.in_(media_ids))
        media_records = media_query.filter(or_(*media_filters)).all() if media_filters else []
        media_ids.extend(media.id for media in media_records)
        media_ids = _unique_ints(media_ids)

        generated_records = (
            session.query(GeneratedInvoice)
            .filter(GeneratedInvoice.user_id == user_id, GeneratedInvoice.id.in_(generated_ids))
            .all()
            if generated_ids
            else []
        )

        storage_paths = _collect_media_paths(media_records)
        storage_paths.extend(_collect_generated_paths(generated_records))
        storage_result = _delete_storage_paths(storage_paths)
        if storage_result.get("failed"):
            session.rollback()
            return {
                "status": "error",
                "message": "Could not delete one or more stored files. Database rows were not removed.",
                "storage": storage_result,
            }

        deleted = {
            "documents": 0,
            "media": 0,
            "generated_invoices": 0,
            "messages": 0,
            "usage": 0,
            "storage_files": len(storage_result.get("deleted", [])),
        }

        if invoice_ids:
            session.query(InvoiceEmbedding).filter(
                InvoiceEmbedding.user_id == user_id,
                InvoiceEmbedding.invoice_id.in_(invoice_ids),
            ).delete(synchronize_session=False)
            session.query(Item).filter(Item.invoice_id.in_(invoice_ids)).delete(synchronize_session=False)

        if media_ids:
            deleted["media"] = session.query(Media).filter(
                Media.user_id == user_id,
                Media.id.in_(media_ids),
            ).delete(synchronize_session=False)

        if invoice_ids:
            deleted["documents"] = session.query(Invoice).filter(
                Invoice.user_id == user_id,
                Invoice.id.in_(invoice_ids),
            ).delete(synchronize_session=False)

        if generated_ids:
            session.query(GeneratedInvoiceItem).filter(
                GeneratedInvoiceItem.generated_invoice_id.in_(generated_ids)
            ).delete(synchronize_session=False)
            deleted["generated_invoices"] = session.query(GeneratedInvoice).filter(
                GeneratedInvoice.user_id == user_id,
                GeneratedInvoice.id.in_(generated_ids),
            ).delete(synchronize_session=False)

        if delete_conversation:
            conversation_ids = [
                row[0]
                for row in session.query(Conversation.id)
                .filter(Conversation.user_id == user_id)
                .all()
            ]
            message_ids = [
                row[0]
                for row in session.query(Message.id)
                .filter(Message.user_id == user_id)
                .all()
            ]
            if conversation_ids:
                message_ids.extend(
                    row[0]
                    for row in session.query(Message.id)
                    .filter(Message.conversation_id.in_(conversation_ids))
                    .all()
                )
            message_ids = _unique_ints(message_ids)
            if message_ids:
                session.query(WhatsAppMessage).filter(
                    WhatsAppMessage.message_id.in_(message_ids)
                ).delete(synchronize_session=False)
                deleted["messages"] = session.query(Message).filter(
                    Message.id.in_(message_ids)
                ).delete(synchronize_session=False)
            if conversation_ids:
                session.query(Conversation).filter(
                    Conversation.id.in_(conversation_ids)
                ).delete(synchronize_session=False)

        if delete_usage:
            deleted["usage"] = session.query(Usage).filter(Usage.user_id == user_id).delete(
                synchronize_session=False
            )

        session.commit()
        return {
            "status": "success",
            "message": "History deleted",
            "deleted": deleted,
            "storage": storage_result,
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _serialize_invoice_document(invoice: Any, media_records: Sequence[Any], item_count: int) -> Dict[str, Any]:
    media = media_records[0] if media_records else None
    filename = (media.original_filename or media.filename) if media else None
    access_url = _media_access_url(media) if media else None
    return {
        "kind": "invoice",
        "id": str(invoice.id),
        "invoice_id": str(invoice.id),
        "media_id": str(media.id) if media else None,
        "title": invoice.vendor or "Receipt",
        "filename": filename,
        "date": invoice.invoice_date.date().isoformat() if invoice.invoice_date else None,
        "total_amount": invoice.total_amount,
        "currency": invoice.currency,
        "item_count": int(item_count or 0),
        "status": "processed",
        "created_at": _iso(invoice.created_at),
        "file_path": media.file_path if media else None,
        "file_url": access_url,
        "signed_url": access_url,
        "content_type": media.content_type if media else None,
    }


def _serialize_media_document(media: Any) -> Dict[str, Any]:
    metadata = media.processing_metadata if isinstance(media.processing_metadata, dict) else {}
    review_summary = metadata.get("pending_extraction_summary")
    if not isinstance(review_summary, dict):
        review_summary = {}
    access_url = _media_access_url(media)
    hitl_status = metadata.get("hitl_status")
    approval_command = metadata.get("hitl_approval_command")
    rejection_command = metadata.get("hitl_rejection_command")
    if hitl_status == "awaiting_confirmation":
        approval_command = approval_command or f"APPROVE {media.id}"
        rejection_command = rejection_command or f"REJECT {media.id}"
    return {
        "kind": "media",
        "id": str(media.id),
        "media_id": str(media.id),
        "invoice_id": None,
        "title": media.original_filename or media.filename or "Upload",
        "filename": media.original_filename or media.filename,
        "date": _visible_review_value(review_summary.get("transaction_date")),
        "total_amount": review_summary.get("total_amount"),
        "currency": review_summary.get("currency"),
        "item_count": int(review_summary.get("item_count") or 0),
        "status": media.status or "uploaded",
        "processing_status": metadata.get("processing_status"),
        "hitl_status": hitl_status,
        "hitl_action": metadata.get("hitl_action"),
        "approval_command": approval_command,
        "rejection_command": rejection_command,
        "review_summary": review_summary,
        "created_at": _iso(media.created_at),
        "file_path": media.file_path,
        "file_url": access_url,
        "signed_url": access_url,
        "content_type": media.content_type,
    }


def _serialize_generated_invoice(invoice: Any) -> Dict[str, Any]:
    return {
        "kind": "generated_invoice",
        "id": str(invoice.id),
        "invoice_number": invoice.invoice_number,
        "client_name": invoice.client_name,
        "client_company": invoice.client_company,
        "status": invoice.status,
        "total_amount": invoice.total_amount,
        "currency": invoice.currency,
        "created_at": _iso(invoice.created_at),
    }


def _collect_media_paths(media_records: Iterable[Any]) -> List[str]:
    paths: List[str] = []
    for media in media_records:
        paths.append(media.file_path)
        metadata = media.processing_metadata if isinstance(media.processing_metadata, dict) else {}
        storage = metadata.get("file_storage") if isinstance(metadata, dict) else {}
        if isinstance(storage, dict):
            paths.extend([storage.get("file_key"), storage.get("path")])
    return _clean_storage_paths(paths)


def _collect_generated_paths(generated_records: Iterable[Any]) -> List[str]:
    paths: List[str] = []
    for invoice in generated_records:
        paths.extend([invoice.document_path, invoice.pdf_path])
    return _clean_storage_paths(paths)


def _delete_storage_paths(paths: List[str]) -> Dict[str, Any]:
    paths = _clean_storage_paths(paths)
    if not paths:
        return {"deleted": [], "failed": [], "skipped": []}
    try:
        return SupabaseStorageHandler().delete_files(paths)
    except StorageConfigurationError as exc:
        logger.warning("Could not delete Supabase files because storage is not configured: %s", exc)
        return {"deleted": [], "failed": paths, "error": str(exc)}
    except Exception as exc:
        logger.exception("Could not delete Supabase files: %s", exc)
        return {"deleted": [], "failed": paths, "error": str(exc)}


def _clean_storage_paths(paths: Iterable[Any]) -> List[str]:
    cleaned: List[str] = []
    seen = set()
    for path in paths:
        value = str(path or "").strip().lstrip("/")
        if not value or value.startswith(("http://", "https://", "pending://")) or value in seen:
            continue
        seen.add(value)
        cleaned.append(value)
    return cleaned


def _media_access_url(media: Any) -> Optional[str]:
    """Return a browser-safe URL for a private media object when available."""

    if not media:
        return None

    file_url = str(getattr(media, "file_url", "") or "").strip()
    if file_url.startswith("/uploads/"):
        return file_url

    file_path = str(getattr(media, "file_path", "") or "").strip().lstrip("/")
    if file_path.startswith("pending://"):
        return None
    if not file_path:
        if file_url.startswith(("http://", "https://")):
            return file_url
        return None

    try:
        return SupabaseStorageHandler().generate_url(file_path)
    except StorageConfigurationError as exc:
        logger.warning("Could not sign media file %s because storage is not configured: %s", file_path, exc)
    except Exception as exc:
        logger.warning("Could not sign media file %s: %s", file_path, exc)
    if file_url.startswith(("http://", "https://")):
        return file_url
    return None


def _coerce_int(value: Any, label: str) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        raise ValueError(f"Invalid {label}") from None


def _visible_review_value(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text or text.lower() == "not visible":
        return None
    return text


def _unique_ints(values: Iterable[Any]) -> List[int]:
    unique: List[int] = []
    seen = set()
    for value in values:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed not in seen:
            seen.add(parsed)
            unique.append(parsed)
    return unique


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None
