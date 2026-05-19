"""Live backend helpers for the Vercel Flask entrypoint.

The root ``app.py`` is the deployed Vercel handler. These helpers keep heavy
database, storage, and LLM imports lazy so the UI can still run in demo mode
when production secrets are not configured.
"""

from __future__ import annotations

import asyncio
import mimetypes
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from werkzeug.utils import secure_filename
from utils.clerk_auth import is_auth_required
from utils.phone_numbers import normalize_whatsapp_number as normalize_phone_number


DEFAULT_WHATSAPP_NUMBER = "+1234567890"
VERIFIED_PHONE_REQUIRED_MESSAGE = "Sign in with a verified phone number first"


def is_live_backend_enabled() -> bool:
    """Return whether the deployed app should use the real backend paths."""

    return backend_configuration_status()["enabled"]


def backend_configuration_status() -> Dict[str, Any]:
    """Return sanitized readiness status for live backend configuration."""

    if os.getenv("APP_MODE", "").strip().lower() in {"demo", "ui-demo"}:
        return {"enabled": False, "reason": "APP_MODE forces demo mode"}

    database_url = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DATABASE_URL")
    supabase_url = os.getenv("NEXT_PUBLIC_SUPABASE_URL") or os.getenv("SUPABASE_URL")
    has_component_db = bool(
        os.getenv("SUPABASE_DB_PASSWORD")
        and supabase_url
    )
    if not database_url and not has_component_db:
        return {"enabled": False, "reason": "Missing DATABASE_URL or Supabase DB password"}
    if database_url and _has_placeholder(database_url):
        return {"enabled": False, "reason": "DATABASE_URL contains a placeholder password"}
    database_url_error = _database_url_error(database_url)
    if database_url_error and not has_component_db:
        return {"enabled": False, "reason": database_url_error}
    if os.getenv("SUPABASE_DB_PASSWORD") and _has_placeholder(os.getenv("SUPABASE_DB_PASSWORD", "")):
        return {"enabled": False, "reason": "SUPABASE_DB_PASSWORD contains a placeholder"}

    missing_optional = []
    if not os.getenv("OPENAI_API_KEY"):
        missing_optional.append("OPENAI_API_KEY")
    if not supabase_url:
        missing_optional.append("NEXT_PUBLIC_SUPABASE_URL")
    if not (os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")):
        missing_optional.append("SUPABASE_SECRET_KEY")
    if database_url_error and has_component_db:
        missing_optional.append(f"DATABASE_URL ignored: {database_url_error}")

    return {
        "enabled": True,
        "reason": "configured",
        "warnings": missing_optional,
    }


def run_async(coro):
    """Run an async operation from a synchronous Flask request."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result_box: dict[str, Any] = {}
    error_box: dict[str, BaseException] = {}

    def runner() -> None:
        try:
            result_box["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - defensive bridge
            error_box["error"] = exc

    import threading

    thread = threading.Thread(target=runner)
    thread.start()
    thread.join()
    if "error" in error_box:
        raise error_box["error"]
    return result_box.get("value")


def serialize_user(user: Any, is_new: bool = False) -> Optional[Dict[str, Any]]:
    if not user:
        return None
    return {
        "id": str(user.id),
        "name": user.name,
        "email": user.email,
        "whatsapp_number": user.whatsapp_number,
        "clerk_user_id": user.clerk_user_id,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        "is_new": is_new,
    }


def get_linked_user(clerk_user_id: Optional[str]) -> Optional[Any]:
    if not clerk_user_id:
        return None
    from database.connection import get_db_session
    from database.user_utils import get_user_by_clerk_id

    session = get_db_session()
    try:
        return get_user_by_clerk_id(session, clerk_user_id)
    finally:
        session.close()


def get_auth_identity(auth_context: Any) -> Optional[Dict[str, Any]]:
    if not auth_context:
        return None
    linked_user = get_linked_user(auth_context.clerk_user_id)
    return {
        "clerk_user_id": auth_context.clerk_user_id,
        "session_id": auth_context.session_id,
        "linked_user": serialize_user(linked_user),
        "needs_link": linked_user is None,
    }


def sync_verified_phone_user(auth_context: Any) -> Dict[str, Any]:
    """Create or link the app user from Clerk's verified phone profile."""

    from database.connection import get_db_session
    from database.user_utils import link_clerk_user_to_whatsapp
    from utils.clerk_auth import ClerkAuthError, verified_phone_profile_from_clerk

    try:
        profile = verified_phone_profile_from_clerk(auth_context)
    except ClerkAuthError as exc:
        raise ValueError(str(exc)) from exc

    session = get_db_session()
    try:
        return link_clerk_user_to_whatsapp(
            session=session,
            clerk_user_id=auth_context.clerk_user_id,
            whatsapp_number=profile.phone_number,
            name=profile.name,
            email=profile.email,
        )
    finally:
        session.close()


def sync_auth_identity(auth_context: Any) -> Optional[Dict[str, Any]]:
    """Ensure a signed-in phone account has an app user and return identity."""

    if not auth_context:
        return None
    linked_user = sync_verified_phone_user(auth_context)
    return {
        "clerk_user_id": auth_context.clerk_user_id,
        "session_id": auth_context.session_id,
        "linked_user": linked_user,
        "needs_link": False,
    }


def link_clerk_to_whatsapp(auth_context: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    del payload

    return sync_verified_phone_user(auth_context)


def get_or_create_user_for_whatsapp(
    whatsapp_number: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
) -> Dict[str, Any]:
    from database.connection import get_db_session
    from database.user_utils import create_user

    normalized_number = normalize_whatsapp_number(whatsapp_number)
    session = get_db_session()
    try:
        return create_user(
            session=session,
            whatsapp_number=normalized_number,
            name=name,
            email=email,
        )
    finally:
        session.close()


def list_users(auth_context: Any = None) -> Dict[str, Any]:
    linked_user = get_linked_user(auth_context.clerk_user_id) if auth_context else None
    if linked_user:
        return {
            "status": "success",
            "users": [serialize_user(linked_user)],
            "needs_link": False,
        }
    if auth_context:
        try:
            synced_user = sync_verified_phone_user(auth_context)
            return {"status": "success", "users": [synced_user], "needs_link": False}
        except ValueError as exc:
            return {
                "status": "success",
                "users": [],
                "needs_link": True,
                "needs_phone": True,
                "message": str(exc),
            }

    from database.connection import get_db_session
    from database.connection import ensure_application_schema
    from database.schemas import User

    ensure_application_schema()
    session = get_db_session()
    try:
        users = session.query(User).order_by(User.id.asc()).limit(100).all()
        return {"status": "success", "users": [serialize_user(user) for user in users]}
    finally:
        session.close()


def initialize_workspace(
    auth_context: Any,
    whatsapp_number: Optional[str],
    reset_conversation: bool = False,
) -> Dict[str, Any]:
    linked_user = get_linked_user(auth_context.clerk_user_id) if auth_context else None
    if not linked_user and auth_context:
        try:
            synced_user = sync_verified_phone_user(auth_context)
            conversation_id = _reset_or_current_conversation_id(synced_user["id"], reset_conversation)
            return {
                "status": "success",
                "message": "Workspace initialized",
                "conversation_id": conversation_id,
                "user_id": synced_user["id"],
                "whatsapp_number": synced_user["whatsapp_number"],
                "needs_link": False,
            }
        except ValueError as exc:
            return {
                "status": "success",
                "message": str(exc),
                "conversation_id": _conversation_key(auth_context.clerk_user_id),
                "user_id": None,
                "whatsapp_number": normalize_whatsapp_number(whatsapp_number),
                "needs_link": True,
                "needs_phone": True,
            }
    if linked_user:
        user = serialize_user(linked_user)
        conversation_id = _reset_or_current_conversation_id(user["id"], reset_conversation)
        return {
            "status": "success",
            "message": "Workspace initialized",
            "conversation_id": conversation_id,
            "user_id": user["id"],
            "whatsapp_number": user["whatsapp_number"],
            "needs_link": False,
        }
    if auth_context:
        return {
            "status": "success",
            "message": "Sign in with a verified phone number to load receipts.",
            "conversation_id": _conversation_key(auth_context.clerk_user_id),
            "user_id": None,
            "whatsapp_number": normalize_whatsapp_number(whatsapp_number),
            "needs_link": True,
            "needs_phone": True,
        }

    user = get_or_create_user_for_whatsapp(whatsapp_number or DEFAULT_WHATSAPP_NUMBER)
    conversation_id = _reset_or_current_conversation_id(user["id"], reset_conversation)
    return {
        "status": "success",
        "message": "Workspace initialized",
        "conversation_id": conversation_id,
        "user_id": user["id"],
        "whatsapp_number": user["whatsapp_number"],
        "needs_link": False,
    }


def create_or_link_user(auth_context: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    if auth_context:
        user = sync_verified_phone_user(auth_context)
        return {
            "status": "success",
            "message": "Phone account synchronized",
            "user": user,
            "identity": {
                "clerk_user_id": auth_context.clerk_user_id,
                "linked_user": user,
                "needs_link": False,
            },
        }

    user = get_or_create_user_for_whatsapp(
        payload.get("whatsapp_number") or DEFAULT_WHATSAPP_NUMBER,
        name=payload.get("name"),
        email=payload.get("email"),
    )
    return {
        "status": "success",
        "message": "User created successfully" if user.get("is_new") else "User already exists",
        "user": user,
    }


def resolve_request_user(
    auth_context: Any,
    payload: Optional[Dict[str, Any]] = None,
) -> tuple[Optional[Dict[str, Any]], bool]:
    payload = payload or {}
    linked_user = get_linked_user(auth_context.clerk_user_id) if auth_context else None
    if linked_user:
        return serialize_user(linked_user), False
    if auth_context:
        try:
            return sync_verified_phone_user(auth_context), False
        except ValueError:
            return None, True
    if is_auth_required():
        return None, True
    if payload.get("user_id"):
        from database.connection import get_db_session
        from database.schemas import User

        session = get_db_session()
        try:
            user = session.query(User).filter(User.id == int(payload["user_id"])).first()
            if user:
                return serialize_user(user), False
        finally:
            session.close()
    return (
        get_or_create_user_for_whatsapp(
            payload.get("whatsapp_number") or DEFAULT_WHATSAPP_NUMBER
        ),
        False,
    )


def process_chat_message(auth_context: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    from workflows.api import process_text_message

    user, needs_link = resolve_request_user(auth_context, payload)
    if needs_link:
        return {
            "status": "error",
            "message": "Sign in with a verified phone number before querying receipts.",
            "needs_link": True,
            "needs_phone": True,
        }
    message = (payload.get("message") or "").strip()
    if not message:
        return {"status": "error", "message": "No message provided"}

    user_id = user["id"]
    key = _conversation_key(user_id)
    result = run_async(
        process_text_message(
            message=message,
            sender=f"whatsapp:{user['whatsapp_number']}",
            user_id=user_id,
            conversation_id=key,
        )
    )

    response_message = result.get("message") or result.get("content") or ""
    result.setdefault("status", "success")
    result.setdefault("message", response_message)
    result["whatsapp_number"] = user["whatsapp_number"]
    result["user_id"] = user_id
    return result


def process_upload(auth_context: Any, uploaded_file: Any, form: Dict[str, Any]) -> Dict[str, Any]:
    from workflows.api import process_file_message

    if not uploaded_file or not uploaded_file.filename:
        return {"status": "error", "message": "No file selected"}

    user, needs_link = resolve_request_user(auth_context, form)
    if needs_link:
        return {
            "status": "error",
            "message": "Sign in with a verified phone number before uploading receipts.",
            "needs_link": True,
            "needs_phone": True,
        }

    filename = secure_filename(uploaded_file.filename) or "receipt"
    temp_dir = Path(tempfile.mkdtemp(prefix="receipt_upload_"))
    temp_path = temp_dir / filename

    try:
        uploaded_file.save(temp_path)
        mime_type = (
            getattr(uploaded_file, "mimetype", None)
            or mimetypes.guess_type(filename)[0]
            or "application/octet-stream"
        )
        result = run_async(
            process_file_message(
                file_path=str(temp_path),
                file_name=filename,
                mime_type=mime_type,
                sender=f"whatsapp:{user['whatsapp_number']}",
                user_id=user["id"],
                conversation_id=_conversation_key(user["id"]),
            )
        )
        result.setdefault("status", "success")
        result["filename"] = filename
        result["type"] = "file"
        result["whatsapp_number"] = user["whatsapp_number"]
        result["user_id"] = user["id"]
        return result
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def process_twilio_webhook(form: Dict[str, Any]) -> Dict[str, Any]:
    from workflows.api import process_whatsapp_message

    return run_async(process_whatsapp_message(form))


def get_company_profile(user_id: Optional[str], auth_context: Any = None) -> Dict[str, Any]:
    from database.connection import get_db_session
    from database.schemas import User
    from services.generated_invoice_service import load_user_preferences

    user, needs_link = resolve_request_user(auth_context, {"user_id": user_id} if user_id else {})
    if needs_link:
        return {"status": "error", "message": VERIFIED_PHONE_REQUIRED_MESSAGE, "needs_link": True, "needs_phone": True}
    target_id = int(user["id"] if user else user_id)

    session = get_db_session()
    try:
        db_user = session.query(User).filter(User.id == target_id).first()
        if not db_user:
            return {"status": "error", "message": "User not found"}
        preferences = load_user_preferences(db_user)
        return {
            "status": "success",
            "preferences": preferences,
            "profile": preferences,
            "user_id": str(db_user.id),
        }
    finally:
        session.close()


def update_company_profile(payload: Dict[str, Any], auth_context: Any = None) -> Dict[str, Any]:
    from database.connection import get_db_session
    from services.generated_invoice_service import update_invoice_defaults

    user, needs_link = resolve_request_user(auth_context, payload)
    if needs_link:
        return {"status": "error", "message": VERIFIED_PHONE_REQUIRED_MESSAGE, "needs_link": True, "needs_phone": True}
    session = get_db_session()
    try:
        preferences = update_invoice_defaults(session, int(user["id"]), payload)
        return {
            "status": "success",
            "message": "Company profile saved",
            "preferences": preferences,
            "profile": preferences,
            "user_id": user["id"],
        }
    finally:
        session.close()


def list_generated(auth_context: Any, query: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from services.generated_invoice_service import (
        get_generated_invoice_stats,
        list_generated_invoices,
    )

    user, needs_link = resolve_request_user(auth_context, query or {})
    if needs_link:
        return {"status": "error", "message": VERIFIED_PHONE_REQUIRED_MESSAGE, "needs_link": True, "needs_phone": True}
    invoices = list_generated_invoices(int(user["id"]))
    analytics = get_generated_invoice_stats(int(user["id"]))
    return {
        "status": "success",
        "generated_invoices": invoices,
        "invoices": invoices,
        "analytics": analytics,
    }


def create_generated(auth_context: Any, payload: Dict[str, Any], source: str = "web") -> Dict[str, Any]:
    from services.generated_invoice_service import generate_and_persist_invoice

    user, needs_link = resolve_request_user(auth_context, payload)
    if needs_link:
        return {"status": "error", "message": VERIFIED_PHONE_REQUIRED_MESSAGE, "needs_link": True, "needs_phone": True}
    invoice = generate_and_persist_invoice(payload, user_id=int(user["id"]), source=source)
    return {
        "status": "success",
        "message": "Invoice generated",
        "generated_invoice": invoice,
        "invoice": invoice,
        "document_url": invoice.get("document_url"),
        "pdf_url": invoice.get("pdf_url"),
    }


def generated_analytics(auth_context: Any, query: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from services.generated_invoice_service import get_generated_invoice_stats

    user, needs_link = resolve_request_user(auth_context, query or {})
    if needs_link:
        return {"status": "error", "message": VERIFIED_PHONE_REQUIRED_MESSAGE, "needs_link": True, "needs_phone": True}
    return {
        "status": "success",
        "analytics": get_generated_invoice_stats(int(user["id"])),
    }


def list_history(auth_context: Any, query: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from services.history_service import list_user_history

    user, needs_link = resolve_request_user(auth_context, query or {})
    if needs_link:
        return {"status": "error", "message": VERIFIED_PHONE_REQUIRED_MESSAGE, "needs_link": True, "needs_phone": True}
    limit = (query or {}).get("limit") or 50
    return list_user_history(int(user["id"]), int(limit))


def delete_history(auth_context: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    from services.history_service import delete_user_history

    user, needs_link = resolve_request_user(auth_context, payload)
    if needs_link:
        return {"status": "error", "message": VERIFIED_PHONE_REQUIRED_MESSAGE, "needs_link": True, "needs_phone": True}
    return delete_user_history(int(user["id"]), payload)


async def review_history_upload(auth_context: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    from services.hitl_service import review_pending_upload_from_web

    user, needs_link = resolve_request_user(auth_context, payload)
    if needs_link:
        return {"status": "error", "message": VERIFIED_PHONE_REQUIRED_MESSAGE, "needs_link": True, "needs_phone": True}
    media_id = payload.get("media_id") or payload.get("id")
    if not media_id:
        return {"status": "error", "message": "Media ID is required"}
    return await review_pending_upload_from_web(
        int(user["id"]),
        int(media_id),
        payload.get("action"),
    )


def database_status(auth_context: Any = None) -> Dict[str, Any]:
    from sqlalchemy import func, text

    from database.connection import SessionLocal, engine, ensure_application_schema
    from database.schemas import GeneratedInvoice, Invoice, InvoiceEmbedding, Item, Media

    ensure_application_schema()
    user = None
    if auth_context:
        linked = get_linked_user(auth_context.clerk_user_id)
        user = serialize_user(linked) if linked else None

    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        vector_installed = conn.execute(
            text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        ).scalar()

    session = SessionLocal()
    try:
        total_invoices = session.query(func.count(Invoice.id)).scalar() or 0
        user_invoices = (
            session.query(func.count(Invoice.id)).filter(Invoice.user_id == int(user["id"])).scalar()
            if user
            else total_invoices
        ) or 0
        total_items = session.query(func.count(Item.id)).scalar() or 0
        user_items = (
            session.query(func.count(Item.id))
            .join(Invoice, Item.invoice_id == Invoice.id)
            .filter(Invoice.user_id == int(user["id"]))
            .scalar()
            if user
            else total_items
        ) or 0
        generated_count = (
            session.query(func.count(GeneratedInvoice.id))
            .filter(GeneratedInvoice.user_id == int(user["id"]))
            .scalar()
            if user
            else session.query(func.count(GeneratedInvoice.id)).scalar()
        ) or 0
        with_embeddings = session.query(func.count(InvoiceEmbedding.id)).scalar() or 0
        media_count = session.query(func.count(Media.id)).scalar() or 0
    finally:
        session.close()

    return {
        "status": "success",
        "connection_status": {
            "success": True,
            "message": "Connected to Supabase Postgres",
        },
        "counts": {
            "invoices": {"total": total_invoices, "user_specific": user_invoices},
            "items": total_items,
            "user_items": user_items,
            "generated_invoices": generated_count,
            "media_files": media_count,
        },
        "size_info": {
            "total_size": "available in Supabase dashboard",
            "tables_size": "available in Supabase dashboard",
        },
        "connection_info": {"database": {"provider": "supabase"}},
        "vector_info": {
            "installed": bool(vector_installed),
            "with_embeddings": with_embeddings,
            "without_embeddings": max(total_invoices - with_embeddings, 0),
        },
    }


def latest_file_storage(auth_context: Any = None) -> Dict[str, Any]:
    from sqlalchemy import text

    from database.connection import get_db_session, ensure_application_schema
    from storage import SupabaseStorageHandler

    ensure_application_schema()
    linked_user = get_linked_user(auth_context.clerk_user_id) if auth_context else None
    session = get_db_session()
    try:
        if linked_user:
            row = session.execute(
                text(
                    """
                    SELECT file_url, file_path, content_type, file_size, processing_metadata
                    FROM media
                    WHERE user_id = :user_id
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {"user_id": linked_user.id},
            ).first()
        else:
            row = session.execute(
                text(
                    """
                    SELECT file_url, file_path, content_type, file_size, processing_metadata
                    FROM media
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                )
            ).first()
    finally:
        session.close()

    if not row:
        return {
            "status": "not_found",
            "message": "No uploaded file metadata found",
            "file_storage": {},
        }

    file_url, file_path, content_type, file_size, metadata = row
    storage_info = metadata if isinstance(metadata, dict) else {}
    storage_info.update(
        {
            "provider": storage_info.get("provider", "supabase"),
            "file_key": storage_info.get("file_key") or file_path,
            "path": storage_info.get("path") or file_path,
            "url": file_url,
            "content_type": content_type,
            "file_size": file_size,
        }
    )
    if storage_info.get("file_key"):
        storage_info["url"] = SupabaseStorageHandler().generate_url(storage_info["file_key"])

    return {"status": "success", "file_storage": storage_info}


def normalize_whatsapp_number(value: Optional[str], default: Optional[str] = DEFAULT_WHATSAPP_NUMBER) -> str:
    return normalize_phone_number(value, default=default)


def _conversation_key(user_id: str) -> str:
    return f"user-{user_id}"


def _reset_or_current_conversation_id(user_id: str, reset_conversation: bool) -> str:
    if not reset_conversation:
        return _conversation_key(user_id)
    from services.conversation_memory import start_new_conversation

    conversation_id = start_new_conversation(user_id)
    return str(conversation_id) if conversation_id is not None else _conversation_key(user_id)


def _has_placeholder(value: str) -> bool:
    lowered = value.lower()
    return (
        "[your-password]" in lowered
        or "<your-password>" in lowered
        or "your_password" in lowered
        or "your-" in lowered
        or "placeholder" in lowered
    )


def _database_url_error(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    parsed = urlparse(value.strip().strip("'").strip('"'))
    if parsed.netloc.count("@") > 1:
        return (
            "DATABASE_URL contains an unescaped '@' in the password. "
            "URL-encode the password or set SUPABASE_DB_PASSWORD instead."
        )
    return None
