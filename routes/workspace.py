"""Workspace API routes for chat, uploads, history, and generated invoices."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from flask import Blueprint, Response, jsonify, request

from demo import (
    DEMO_GENERATED_INVOICES,
    DEMO_LINKS,
    DEFAULT_USER,
    DEFAULT_WHATSAPP_NUMBER,
    demo_db_status,
    demo_generated_invoice,
    demo_generated_invoice_stats,
    demo_metadata,
)

from . import shared


bp = Blueprint("workspace", __name__)


@bp.get("/api/init")
def initialize():
    auth_context = shared._require_demo_auth()
    if shared._is_auth_response(auth_context):
        return auth_context
    if shared._live_backend_enabled():
        try:
            return jsonify(
                shared.live_backend.initialize_workspace(
                    auth_context,
                    request.args.get("whatsapp_number"),
                    reset_conversation=request.args.get("reset") == "1",
                )
            )
        except Exception as exc:
            return shared._live_error(exc)
    linked_user = DEMO_LINKS.get(auth_context.clerk_user_id) if auth_context else None
    whatsapp_number = request.args.get("whatsapp_number")
    return jsonify(
        {
            "status": "success",
            "message": "Hosted UI demo initialized.",
            "conversation_id": str(uuid4()),
            "user_id": linked_user["id"] if linked_user else None,
            "whatsapp_number": linked_user["whatsapp_number"] if linked_user else whatsapp_number,
            "needs_link": bool(auth_context and not linked_user),
            "degraded": True,
        }
    )


@bp.get("/api/users")
def get_users():
    auth_context = shared._require_demo_auth()
    if shared._is_auth_response(auth_context):
        return auth_context
    if shared._live_backend_enabled():
        try:
            return jsonify(shared.live_backend.list_users(auth_context))
        except Exception as exc:
            return shared._live_error(exc)
    linked_user = DEMO_LINKS.get(auth_context.clerk_user_id) if auth_context else None
    users = [linked_user] if linked_user else []
    return jsonify(
        {
            "status": "success",
            "users": users,
            "needs_link": bool(auth_context and not linked_user),
            "degraded": True,
        }
    )


@bp.post("/api/users/create")
def create_user():
    data = request.get_json(silent=True) or {}
    auth_context = shared._require_demo_auth()
    if shared._is_auth_response(auth_context):
        return auth_context
    if shared._live_backend_enabled():
        try:
            return jsonify(shared.live_backend.create_or_link_user(auth_context, data))
        except ValueError as exc:
            return jsonify({"status": "error", "message": str(exc), "needs_phone": True}), 409
        except Exception as exc:
            return shared._live_error(exc)
    whatsapp_number = shared.live_backend.normalize_whatsapp_number(
        data.get("whatsapp_number"),
        default="",
    )
    if not whatsapp_number:
        return jsonify({"status": "error", "message": "WhatsApp number is required"}), 400
    user = {
        "id": f"demo-{whatsapp_number.replace('+', '').replace(' ', '')}",
        "name": data.get("name") or "Demo User",
        "email": data.get("email") or "demo@example.com",
        "whatsapp_number": whatsapp_number,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "is_new": True,
    }
    return jsonify(
        {
            "status": "success",
            "message": "Demo user created for this UI session",
            "user": user,
        }
    )


@bp.get("/api/users/company-profile")
@bp.get("/api/users/company-profile/<user_id>")
def get_company_profile(user_id: str | None = None):
    auth_context = shared._require_demo_auth()
    if shared._is_auth_response(auth_context):
        return auth_context
    if shared._live_backend_enabled():
        try:
            result = shared.live_backend.get_company_profile(user_id, auth_context)
            return jsonify(result), 400 if result.get("status") == "error" else 200
        except Exception as exc:
            return shared._live_error(exc)
    return jsonify(
        {
            "status": "success",
            "preferences": {},
            "profile": {},
            "user_id": user_id or DEFAULT_USER["id"],
            "degraded": True,
        }
    )


@bp.post("/api/users/company-profile")
def update_company_profile():
    data = request.get_json(silent=True) or {}
    auth_context = shared._require_demo_auth()
    if shared._is_auth_response(auth_context):
        return auth_context
    if shared._live_backend_enabled():
        try:
            result = shared.live_backend.update_company_profile(data, auth_context)
            return jsonify(result), 400 if result.get("status") == "error" else 200
        except Exception as exc:
            return shared._live_error(exc)
    return jsonify(
        {
            "status": "success",
            "message": "Company profile accepted in demo mode",
            "preferences": data,
            "degraded": True,
        }
    )


@bp.post("/api/message")
def message():
    auth_context = shared._require_demo_auth()
    if shared._is_auth_response(auth_context):
        return auth_context
    if shared._live_backend_enabled():
        try:
            result = shared.live_backend.process_chat_message(
                auth_context,
                request.get_json(silent=True) or {},
            )
            return jsonify(result), 403 if result.get("needs_link") else 200
        except Exception as exc:
            return shared._live_error(exc)
    linked_user = DEMO_LINKS.get(auth_context.clerk_user_id) if auth_context else None
    if auth_context and shared.is_auth_required() and not linked_user:
        return jsonify(
            {
                "status": "error",
                "message": "Sign in with a verified phone number before querying receipts.",
                "needs_link": True,
                "needs_phone": True,
            }
        ), 403

    data = request.get_json(silent=True) or {}
    prompt = (data.get("message") or "").strip()
    whatsapp_number = (
        linked_user["whatsapp_number"]
        if linked_user
        else data.get("whatsapp_number") or DEFAULT_WHATSAPP_NUMBER
    )

    if not prompt:
        return jsonify({"status": "error", "message": "No message provided"}), 400

    lower_prompt = prompt.lower()
    if "spend" in lower_prompt or "month" in lower_prompt:
        intent = "summary_query"
        response = (
            "Demo response: this workspace would summarize monthly spend from "
            "stored receipts, then cite matching invoice records from Supabase."
        )
    elif "receipt" in lower_prompt or "search" in lower_prompt:
        intent = "semantic_search"
        response = (
            "Demo response: semantic receipt search would embed your query, run "
            "pgvector similarity search, and return the most relevant receipts."
        )
    elif "invoice" in lower_prompt or "draft" in lower_prompt:
        intent = "invoice_generation"
        invoice = demo_generated_invoice(linked_user or DEFAULT_USER, source="demo_chat")
        DEMO_GENERATED_INVOICES.insert(0, invoice)
        response = (
            "Demo response: generated a sample outgoing invoice from your "
            "saved company defaults. In production this is saved to Supabase "
            "Storage and appears in the website invoice list."
        )
    else:
        intent = "general_finance_query"
        response = (
            "Demo response: the hosted UI is live. Connect Supabase, OpenAI, "
            "and WhatsApp credentials in Vercel to enable real processing."
        )

    return jsonify(
        {
            "status": "success",
            "message": response,
            "metadata": demo_metadata(intent),
            "generated_invoice": DEMO_GENERATED_INVOICES[0] if intent == "invoice_generation" else None,
            "whatsapp_number": whatsapp_number,
            "user_id": (
                linked_user["id"]
                if linked_user
                else data.get("user_id") or DEFAULT_USER["id"]
            ),
        }
    )


@bp.get("/api/generated-invoices")
def generated_invoices():
    auth_context = shared._require_demo_auth()
    if shared._is_auth_response(auth_context):
        return auth_context
    if shared._live_backend_enabled():
        try:
            result = shared.live_backend.list_generated(auth_context, request.args.to_dict())
            return jsonify(result), 403 if result.get("needs_link") else 200
        except Exception as exc:
            return shared._live_error(exc)
    linked_user = DEMO_LINKS.get(auth_context.clerk_user_id) if auth_context else None
    user = linked_user or DEFAULT_USER
    invoices = [
        invoice for invoice in DEMO_GENERATED_INVOICES
        if invoice.get("user_id") == user["id"]
    ]
    return jsonify(
        {
            "status": "success",
            "generated_invoices": invoices,
            "invoices": invoices,
            "analytics": demo_generated_invoice_stats(invoices),
            "degraded": True,
        }
    )


@bp.post("/api/generated-invoices")
@bp.post("/api/generate-pdf-invoice")
def generated_invoice_create():
    auth_context = shared._require_demo_auth()
    if shared._is_auth_response(auth_context):
        return auth_context
    if shared._live_backend_enabled():
        try:
            result = shared.live_backend.create_generated(
                auth_context,
                request.get_json(silent=True) or {},
                source="web",
            )
            return jsonify(result), 403 if result.get("needs_link") else 200
        except Exception as exc:
            return shared._live_error(exc)
    linked_user = DEMO_LINKS.get(auth_context.clerk_user_id) if auth_context else None
    user = linked_user or DEFAULT_USER
    invoice = demo_generated_invoice(
        user,
        source="demo_web",
        payload=request.get_json(silent=True) or {},
    )
    DEMO_GENERATED_INVOICES.insert(0, invoice)
    return jsonify(
        {
            "status": "success",
            "message": "Demo invoice generated",
            "generated_invoice": invoice,
            "invoice": invoice,
            "document_url": invoice["document_url"],
            "pdf_url": invoice["pdf_url"],
            "degraded": True,
        }
    )


@bp.get("/api/generated-invoices/analytics")
def generated_invoice_analytics():
    auth_context = shared._require_demo_auth()
    if shared._is_auth_response(auth_context):
        return auth_context
    if shared._live_backend_enabled():
        try:
            result = shared.live_backend.generated_analytics(auth_context, request.args.to_dict())
            return jsonify(result), 403 if result.get("needs_link") else 200
        except Exception as exc:
            return shared._live_error(exc)
    linked_user = DEMO_LINKS.get(auth_context.clerk_user_id) if auth_context else None
    user = linked_user or DEFAULT_USER
    invoices = [
        invoice for invoice in DEMO_GENERATED_INVOICES
        if invoice.get("user_id") == user["id"]
    ]
    return jsonify(
        {
            "status": "success",
            "analytics": demo_generated_invoice_stats(invoices),
            "degraded": True,
        }
    )


@bp.get("/api/history")
def history_list():
    auth_context = shared._require_demo_auth()
    if shared._is_auth_response(auth_context):
        return auth_context
    if shared._live_backend_enabled():
        try:
            result = shared.live_backend.list_history(auth_context, request.args.to_dict())
            return jsonify(result), 403 if result.get("needs_link") else 200
        except Exception as exc:
            return shared._live_error(exc)
    return jsonify(
        {
            "status": "success",
            "documents": [],
            "generated_invoices": [],
            "counts": {"documents": 0, "generated_invoices": 0},
            "degraded": True,
        }
    )


@bp.delete("/api/history")
def history_delete():
    auth_context = shared._require_demo_auth()
    if shared._is_auth_response(auth_context):
        return auth_context
    payload = request.get_json(silent=True) or {}
    if shared._live_backend_enabled():
        try:
            result = shared.live_backend.delete_history(auth_context, payload)
            if result.get("needs_link"):
                return jsonify(result), 403
            if result.get("status") == "not_found":
                return jsonify(result), 404
            if result.get("status") == "needs_confirmation":
                return jsonify(result), 428
            if result.get("status") == "error":
                return jsonify(result), 409
            return jsonify(result)
        except ValueError as exc:
            return shared._live_error(exc, 400)
        except Exception as exc:
            return shared._live_error(exc)
    return jsonify(
        {
            "status": "success",
            "message": "Demo history cleared for this UI session.",
            "deleted": {"documents": 0, "generated_invoices": 0, "storage_files": 0},
            "degraded": True,
        }
    )


@bp.post("/api/history/approval")
def history_approval():
    auth_context = shared._require_demo_auth()
    if shared._is_auth_response(auth_context):
        return auth_context
    payload = request.get_json(silent=True) or {}
    if shared._live_backend_enabled():
        try:
            result = shared.live_backend.run_async(shared.live_backend.review_history_upload(auth_context, payload))
            if result.get("needs_link"):
                return jsonify(result), 403
            if result.get("metadata", {}).get("hitl_status") == "not_found":
                return jsonify(result), 404
            if result.get("metadata", {}).get("hitl_status") == "invalid_action":
                return jsonify(result), 400
            if result.get("status") == "error":
                return jsonify(result), 409
            return jsonify(result)
        except ValueError as exc:
            return shared._live_error(exc, 400)
        except Exception as exc:
            return shared._live_error(exc)
    return jsonify(
        {
            "status": "error",
            "message": "Pending upload approval requires the live Supabase backend.",
            "degraded": True,
        }
    ), 409


@bp.get("/api/generated-invoices/demo-invoice.txt")
def generated_invoice_demo_download():
    return Response(
        "Demo invoice file. Configure Supabase Storage to generate durable DOCX/PDF files.",
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=demo-invoice.txt"},
    )


@bp.post("/api/upload")
def upload():
    auth_context = shared._require_demo_auth()
    if shared._is_auth_response(auth_context):
        return auth_context
    if shared._live_backend_enabled():
        try:
            result = shared.live_backend.process_upload(
                auth_context,
                request.files.get("file"),
                request.form.to_dict(),
            )
            status_code = 403 if result.get("needs_link") else 400 if result.get("status") == "error" else 200
            return jsonify(result), status_code
        except Exception as exc:
            return shared._live_error(exc)
    linked_user = DEMO_LINKS.get(auth_context.clerk_user_id) if auth_context else None
    if auth_context and shared.is_auth_required() and not linked_user:
        return jsonify(
            {
                "status": "error",
                "message": "Sign in with a verified phone number before uploading receipts.",
                "needs_link": True,
                "needs_phone": True,
            }
        ), 403

    uploaded_file = request.files.get("file")
    filename = uploaded_file.filename if uploaded_file else "receipt"
    return jsonify(
        {
            "status": "success",
            "message": (
                f"Demo upload received for {filename}. In production this file "
                "is stored in Supabase Storage, extracted by the AI workflow, "
                "and indexed for semantic search."
            ),
            "metadata": demo_metadata("receipt_upload"),
            "type": "file",
            "whatsapp_number": linked_user["whatsapp_number"]
            if linked_user
            else request.form.get("whatsapp_number", DEFAULT_WHATSAPP_NUMBER),
            "user_id": linked_user["id"]
            if linked_user
            else request.form.get("user_id", DEFAULT_USER["id"]),
        }
    )


@bp.get("/api/db-status")
def db_status():
    auth_context = shared._require_demo_auth()
    if shared._is_auth_response(auth_context):
        return auth_context
    if shared._live_backend_enabled():
        try:
            return jsonify(shared.live_backend.database_status(auth_context))
        except Exception as exc:
            return shared._live_error(exc)
    return jsonify(demo_db_status())


@bp.get("/api/file-storage-info")
def file_storage_info():
    auth_context = shared._require_demo_auth()
    if shared._is_auth_response(auth_context):
        return auth_context
    if shared._live_backend_enabled():
        try:
            result = shared.live_backend.latest_file_storage(auth_context)
            return jsonify(result), 404 if result.get("status") == "not_found" else 200
        except Exception as exc:
            return shared._live_error(exc)
    return jsonify(
        {
            "status": "not_found",
            "message": "No files are persisted in the hosted UI demo.",
            "file_storage": {},
        }
    ), 404


@bp.get("/uploads/<path:filename>")
def uploaded_file(filename: str):
    return jsonify(
        {
            "status": "not_found",
            "message": f"{filename} is not persisted in the hosted UI demo.",
        }
    ), 404
