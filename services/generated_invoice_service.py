"""Durable outgoing invoice generation and persistence."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.connection import get_db_session
from database.schemas import GeneratedInvoice, GeneratedInvoiceItem, User
from services.invoice_template_service import generate_invoice
from storage import StorageConfigurationError, SupabaseStorageHandler

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PROFILE_FIELDS = [
    "company_name",
    "company_address",
    "company_phone",
    "company_email",
    "company_fax",
    "company_slogan",
    "company_website",
    "payment_terms",
    "currency",
    "tax_rate",
    "tax_id",
    "invoice_prefix",
    "payment_instructions",
    "client_name",
    "client_company",
    "client_address",
    "client_phone",
    "client_email",
]


def load_user_preferences(user: User) -> Dict[str, Any]:
    """Return parsed user invoice defaults."""

    if not user or not user.preferences:
        return {}
    try:
        if isinstance(user.preferences, str):
            parsed = json.loads(user.preferences)
        else:
            parsed = user.preferences
        return parsed if isinstance(parsed, dict) else {}
    except Exception as exc:
        logger.warning("Could not parse user preferences for %s: %s", user.id, exc)
        return {}


def update_invoice_defaults(
    session: Session,
    user_id: int,
    defaults: Dict[str, Any],
    commit: bool = True,
) -> Dict[str, Any]:
    """Merge invoice profile defaults into the user's preferences JSON."""

    user = session.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("User not found")

    preferences = load_user_preferences(user)
    for field in PROFILE_FIELDS:
        if field in defaults and defaults[field] not in (None, ""):
            preferences[field] = defaults[field]

    user.preferences = json.dumps(preferences)
    session.add(user)
    if commit:
        session.commit()
        session.refresh(user)
    else:
        session.flush()
    return preferences


def normalize_generated_invoice_payload(
    invoice_data: Dict[str, Any],
    user: Optional[User] = None,
) -> Dict[str, Any]:
    """Merge defaults, normalize totals/dates/items, and prepare template data."""

    preferences = load_user_preferences(user) if user else {}
    normalized: Dict[str, Any] = {}

    for field in PROFILE_FIELDS:
        if preferences.get(field) not in (None, ""):
            normalized[field] = preferences[field]

    normalized.update({k: v for k, v in (invoice_data or {}).items() if v is not None})

    invoice_prefix = normalized.get("invoice_prefix") or "INV"
    normalized["invoice_number"] = (
        normalized.get("invoice_number")
        or f"{invoice_prefix}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    )
    normalized["invoice_date"] = _parse_date(normalized.get("invoice_date")) or date.today()

    due_date = _parse_date(normalized.get("due_date"))
    if due_date is None:
        due_date = normalized["invoice_date"] + timedelta(days=30)
    normalized["due_date"] = due_date

    normalized["currency"] = str(normalized.get("currency") or "USD").upper()[:3]
    normalized["status"] = normalized.get("status") or "generated"

    items = _normalize_items(normalized.get("items") or [])
    if not items:
        amount = _to_float(
            normalized.get("total_amount")
            or normalized.get("total")
            or normalized.get("amount")
        )
        items = [
            {
                "description": normalized.get("description") or "Services or goods",
                "quantity": 1.0,
                "unit_price": amount,
                "total_price": amount,
            }
        ]
    normalized["items"] = items

    subtotal = sum(_to_float(item.get("total_price")) for item in items)
    tax_amount = _to_float(normalized.get("tax_amount") or normalized.get("tax"))
    discount_amount = _to_float(normalized.get("discount_amount") or normalized.get("discount"))

    tax_rate = _to_float(normalized.get("tax_rate"))
    if tax_amount == 0 and tax_rate:
        tax_amount = subtotal * tax_rate / 100

    normalized["subtotal"] = _to_float(normalized.get("subtotal")) or subtotal
    normalized["tax_amount"] = tax_amount
    normalized["discount_amount"] = discount_amount
    normalized["total_amount"] = (
        _to_float(normalized.get("total_amount") or normalized.get("total"))
        or normalized["subtotal"] + tax_amount - discount_amount
    )

    if not normalized.get("client_name"):
        normalized["client_name"] = (
            normalized.get("customer_name")
            or normalized.get("recipient_name")
            or normalized.get("client_company")
            or "Client"
        )

    if not normalized.get("company_name") and user:
        normalized["company_name"] = user.name or "Your Company"

    normalized["preferences"] = preferences
    return normalized


def generate_and_persist_invoice(
    invoice_data: Dict[str, Any],
    user_id: int,
    source: str = "web",
    db_session: Optional[Session] = None,
) -> Dict[str, Any]:
    """Generate invoice document files, store them, and persist metadata."""

    own_session = db_session is None
    session = db_session or get_db_session()

    try:
        user = session.query(User).filter(User.id == int(user_id)).first()
        if not user:
            raise ValueError("User not found")

        if invoice_data.get("save_defaults"):
            update_invoice_defaults(session, int(user_id), invoice_data, commit=False)
            user = session.query(User).filter(User.id == int(user_id)).first()

        normalized = normalize_generated_invoice_payload(invoice_data, user=user)
        logger.info("Generating outgoing invoice %s for user %s", normalized["invoice_number"], user_id)

        generation_result = generate_invoice(normalized)
        if not generation_result.get("success"):
            raise RuntimeError(generation_result.get("message") or "Invoice generation failed")

        document_storage = _store_output_file(
            generation_result.get("document_path"),
            user_id=user_id,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        pdf_storage = _store_output_file(
            generation_result.get("pdf_path"),
            user_id=user_id,
            content_type="application/pdf",
        )

        record = GeneratedInvoice(
            user_id=int(user_id),
            source=source,
            status=normalized.get("status", "generated"),
            invoice_number=normalized.get("invoice_number"),
            invoice_date=_as_datetime(normalized.get("invoice_date")),
            due_date=_as_datetime(normalized.get("due_date")),
            client_name=normalized.get("client_name"),
            client_company=normalized.get("client_company"),
            client_email=normalized.get("client_email"),
            client_address=normalized.get("client_address"),
            currency=normalized.get("currency"),
            subtotal=normalized.get("subtotal"),
            tax_amount=normalized.get("tax_amount"),
            discount_amount=normalized.get("discount_amount"),
            total_amount=normalized.get("total_amount"),
            payment_terms=normalized.get("payment_terms"),
            notes=normalized.get("notes") or normalized.get("payment_instructions"),
            storage_bucket=document_storage.get("bucket") or pdf_storage.get("bucket"),
            document_path=document_storage.get("path"),
            pdf_path=pdf_storage.get("path"),
            local_document_url=document_storage.get("local_url"),
            local_pdf_url=pdf_storage.get("local_url"),
            raw_data={
                "request": invoice_data,
                "normalized": _json_safe(normalized),
                "generation": _json_safe(generation_result),
                "storage": {
                    "document": document_storage,
                    "pdf": pdf_storage,
                },
            },
        )
        session.add(record)
        session.flush()

        for index, item in enumerate(normalized.get("items", [])):
            session.add(
                GeneratedInvoiceItem(
                    generated_invoice_id=record.id,
                    description=item.get("description"),
                    quantity=item.get("quantity"),
                    unit_price=item.get("unit_price"),
                    total_price=item.get("total_price"),
                    sort_order=index,
                )
            )

        session.commit()
        session.refresh(record)
        return serialize_generated_invoice(record)

    except Exception:
        session.rollback()
        raise
    finally:
        if own_session:
            session.close()


def list_generated_invoices(
    user_id: int,
    db_session: Optional[Session] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Return newest generated invoices for a user."""

    own_session = db_session is None
    session = db_session or get_db_session()
    try:
        records = (
            session.query(GeneratedInvoice)
            .filter(GeneratedInvoice.user_id == int(user_id))
            .order_by(GeneratedInvoice.created_at.desc())
            .limit(limit)
            .all()
        )
        return [serialize_generated_invoice(record) for record in records]
    finally:
        if own_session:
            session.close()


def get_generated_invoice_stats(
    user_id: int,
    db_session: Optional[Session] = None,
) -> Dict[str, Any]:
    """Return generated invoice analytics for a user."""

    own_session = db_session is None
    session = db_session or get_db_session()
    try:
        total_count, total_amount = (
            session.query(
                func.count(GeneratedInvoice.id),
                func.coalesce(func.sum(GeneratedInvoice.total_amount), 0),
            )
            .filter(GeneratedInvoice.user_id == int(user_id))
            .one()
        )
        status_rows = (
            session.query(GeneratedInvoice.status, func.count(GeneratedInvoice.id))
            .filter(GeneratedInvoice.user_id == int(user_id))
            .group_by(GeneratedInvoice.status)
            .all()
        )
        recent = list_generated_invoices(user_id, db_session=session, limit=5)
        return {
            "count": int(total_count or 0),
            "total_amount": float(total_amount or 0),
            "by_status": {status or "unknown": int(count) for status, count in status_rows},
            "recent": recent,
        }
    finally:
        if own_session:
            session.close()


def serialize_generated_invoice(record: GeneratedInvoice) -> Dict[str, Any]:
    """Return API-safe generated invoice data with fresh signed URLs when possible."""

    return {
        "id": record.id,
        "user_id": record.user_id,
        "source": record.source,
        "status": record.status,
        "invoice_number": record.invoice_number,
        "invoice_date": record.invoice_date.isoformat() if record.invoice_date else None,
        "due_date": record.due_date.isoformat() if record.due_date else None,
        "client_name": record.client_name,
        "client_company": record.client_company,
        "client_email": record.client_email,
        "client_address": record.client_address,
        "currency": record.currency,
        "subtotal": record.subtotal,
        "tax_amount": record.tax_amount,
        "discount_amount": record.discount_amount,
        "total_amount": record.total_amount,
        "payment_terms": record.payment_terms,
        "notes": record.notes,
        "document_path": record.document_path,
        "pdf_path": record.pdf_path,
        "document_url": record.local_document_url or _signed_url(record.document_path, record.storage_bucket),
        "pdf_url": record.local_pdf_url or _signed_url(record.pdf_path, record.storage_bucket),
        "items": [
            {
                "id": item.id,
                "description": item.description,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "total_price": item.total_price,
                "sort_order": item.sort_order,
            }
            for item in sorted(record.items, key=lambda row: row.sort_order or 0)
        ],
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def _store_output_file(
    file_path: Optional[str],
    user_id: int,
    content_type: str,
) -> Dict[str, Any]:
    if not file_path or not os.path.exists(file_path):
        return {}

    path = Path(file_path)
    resolved_content_type = content_type or mimetypes.guess_type(path.name)[0]

    try:
        handler = SupabaseStorageHandler()
        with open(path, "rb") as file_obj:
            return handler.upload_file(
                file_obj.read(),
                file_name=path.name,
                user_id=user_id,
                content_type=resolved_content_type,
                file_type="generated-invoices",
                metadata={"kind": "generated_invoice"},
            )
    except (StorageConfigurationError, RuntimeError, ValueError) as exc:
        if _is_production_runtime():
            raise RuntimeError(
                "Generated invoice storage is not available. Configure Supabase Storage "
                "before enabling invoice generation in production."
            ) from exc
        logger.warning("Generated invoice storage upload skipped, using local dev copy: %s", exc)
        return _copy_to_local_uploads(path)


def _copy_to_local_uploads(path: Path) -> Dict[str, Any]:
    uploads_dir = PROJECT_ROOT / "ui" / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    target_name = f"generated_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{path.name}"
    target_path = uploads_dir / target_name
    shutil.copy2(path, target_path)
    return {
        "provider": "local",
        "path": str(target_path),
        "local_url": f"/uploads/{target_name}",
        "content_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        "file_size": target_path.stat().st_size,
    }


def _normalize_items(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized_items: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        quantity = _to_float(item.get("quantity")) or 1.0
        unit_price = _to_float(item.get("unit_price") or item.get("price"))
        total_price = _to_float(item.get("total_price") or item.get("amount"))
        if total_price == 0 and unit_price:
            total_price = quantity * unit_price
        if unit_price == 0 and total_price and quantity:
            unit_price = total_price / quantity
        normalized_items.append(
            {
                "description": item.get("description") or item.get("name") or "Item",
                "quantity": quantity,
                "unit_price": unit_price,
                "total_price": total_price,
            }
        )
    return normalized_items


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%m-%d-%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            continue
    return None


def _as_datetime(value: Any) -> Optional[datetime]:
    parsed = _parse_date(value)
    if parsed:
        return datetime.combine(parsed, datetime.min.time())
    return None


def _to_float(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _signed_url(path: Optional[str], bucket: Optional[str]) -> Optional[str]:
    if not path or path.startswith("/uploads/"):
        return path
    try:
        return SupabaseStorageHandler(bucket_name=bucket).generate_url(path)
    except Exception as exc:
        logger.warning("Could not generate signed URL for %s: %s", path, exc)
        return None


def _is_production_runtime() -> bool:
    return (
        os.environ.get("VERCEL") == "1"
        or os.environ.get("FLASK_ENV") == "production"
        or os.environ.get("APP_ENV") == "production"
        or os.environ.get("ENVIRONMENT") == "production"
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value
