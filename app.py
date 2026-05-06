"""Vercel entrypoint for the hosted Receipt Intelligence UI.

The production worker/API paths in this repository need Supabase, OpenAI, and
WhatsApp credentials. This adapter keeps the public Vercel deployment focused
on the operator UI so reviewers can inspect the workflow without provisioning
private infrastructure.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, render_template, request

from utils.clerk_auth import (
    ClerkAuthError,
    get_auth_config,
    is_auth_required,
    is_clerk_enabled,
    verify_clerk_request,
)


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_WHATSAPP_NUMBER = "+1234567890"
DEFAULT_USER = {
    "id": "demo-user",
    "name": "Demo Operator",
    "email": "demo@example.com",
    "whatsapp_number": DEFAULT_WHATSAPP_NUMBER,
}
MEMORY_CONFIG = {
    "max_messages": 50,
    "message_window": 10,
    "max_memory_age": 3600,
    "enable_context_window": True,
    "persist_memory": False,
    "use_mongodb": False,
}
DEMO_LINKS: dict[str, dict] = {}


app = Flask(
    __name__,
    template_folder=str(PROJECT_ROOT / "ui" / "templates"),
    static_folder=str(PROJECT_ROOT / "ui" / "static"),
    static_url_path="/static",
)


def _demo_metadata(intent: str) -> dict:
    return {
        "intent": intent,
        "token_usage": {
            "input_tokens": 128,
            "output_tokens": 224,
            "total_tokens": 352,
        },
        "environment": "vercel-ui-demo",
    }


def _demo_db_status() -> dict:
    return {
        "status": "success",
        "connection_status": {
            "success": False,
            "message": "Hosted UI demo is not connected to a private Supabase database.",
        },
        "counts": {
            "invoices": {
                "total": 0,
                "user_specific": 0,
            },
            "items": 0,
            "user_items": 0,
        },
        "size_info": {
            "total_size": "Demo mode",
            "tables_size": "Demo mode",
        },
        "connection_info": {
            "mongodb": {
                "host": "disabled",
                "port": "n/a",
                "database": "demo",
            }
        },
        "vector_info": {
            "installed": False,
            "with_embeddings": 0,
            "without_embeddings": 0,
        },
    }


def _require_demo_auth():
    """Verify Clerk auth when auth is configured for the hosted demo."""

    if not is_clerk_enabled():
        return None

    try:
        return verify_clerk_request(request)
    except ClerkAuthError as exc:
        if is_auth_required():
            return jsonify({"status": "error", "message": str(exc)}), 401
        return None


def _auth_identity_payload(auth_context):
    if not auth_context:
        return None
    linked_user = DEMO_LINKS.get(auth_context.clerk_user_id)
    return {
        "clerk_user_id": auth_context.clerk_user_id,
        "session_id": auth_context.session_id,
        "linked_user": linked_user,
        "needs_link": linked_user is None,
    }


def _is_auth_response(value) -> bool:
    return isinstance(value, tuple)


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify({"status": "ok", "runtime": "vercel-ui-demo"})


@app.get("/api/auth/config")
def auth_config():
    return jsonify({"status": "success", "auth": get_auth_config()})


@app.get("/api/auth/me")
def auth_me():
    auth_context = _require_demo_auth()
    if _is_auth_response(auth_context):
        return auth_context
    return jsonify(
        {
            "status": "success",
            "auth": get_auth_config(),
            "identity": _auth_identity_payload(auth_context),
        }
    )


@app.post("/api/auth/sync")
def auth_sync():
    auth_context = _require_demo_auth()
    if _is_auth_response(auth_context):
        return auth_context

    data = request.get_json(silent=True) or {}
    linked_user = DEMO_LINKS.get(auth_context.clerk_user_id) if auth_context else None
    return jsonify(
        {
            "status": "success",
            "message": "Clerk session synchronized in demo mode",
            "identity": _auth_identity_payload(auth_context),
            "linked_user": linked_user,
            "suggested_whatsapp_number": data.get("whatsapp_number")
            or DEFAULT_WHATSAPP_NUMBER,
        }
    )


@app.post("/api/auth/link-whatsapp")
def auth_link_whatsapp():
    auth_context = _require_demo_auth()
    if _is_auth_response(auth_context):
        return auth_context
    if not auth_context:
        return jsonify(
            {
                "status": "success",
                "message": "Auth is not configured; demo user remains active.",
                "user": DEFAULT_USER,
                "degraded": True,
            }
        )

    data = request.get_json(silent=True) or {}
    whatsapp_number = data.get("whatsapp_number") or DEFAULT_WHATSAPP_NUMBER
    linked_user = {
        "id": f"demo-{auth_context.clerk_user_id}",
        "name": data.get("name") or "Authenticated User",
        "email": data.get("email") or "",
        "whatsapp_number": whatsapp_number,
        "clerk_user_id": auth_context.clerk_user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "is_new": False,
    }
    DEMO_LINKS[auth_context.clerk_user_id] = linked_user

    return jsonify(
        {
            "status": "success",
            "message": "Linked Clerk account to WhatsApp number in demo mode",
            "user": linked_user,
            "identity": _auth_identity_payload(auth_context),
            "degraded": True,
        }
    )


@app.get("/api/init")
def initialize():
    auth_context = _require_demo_auth()
    if _is_auth_response(auth_context):
        return auth_context
    linked_user = (
        DEMO_LINKS.get(auth_context.clerk_user_id) if auth_context else DEFAULT_USER
    )
    whatsapp_number = request.args.get("whatsapp_number", DEFAULT_WHATSAPP_NUMBER)
    return jsonify(
        {
            "status": "success",
            "message": "Hosted UI demo initialized.",
            "conversation_id": str(uuid4()),
            "user_id": linked_user["id"] if linked_user else DEFAULT_USER["id"],
            "whatsapp_number": (
                linked_user["whatsapp_number"] if linked_user else whatsapp_number
            ),
            "needs_link": bool(auth_context and not linked_user),
            "degraded": True,
        }
    )


@app.get("/api/users")
def get_users():
    auth_context = _require_demo_auth()
    if _is_auth_response(auth_context):
        return auth_context
    linked_user = DEMO_LINKS.get(auth_context.clerk_user_id) if auth_context else None
    users = [linked_user] if linked_user else [DEFAULT_USER]
    return jsonify(
        {
            "status": "success",
            "users": users,
            "needs_link": bool(auth_context and not linked_user),
            "degraded": True,
        }
    )


@app.post("/api/users/create")
def create_user():
    data = request.get_json(silent=True) or {}
    whatsapp_number = data.get("whatsapp_number") or DEFAULT_WHATSAPP_NUMBER
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


@app.get("/api/users/company-profile")
@app.get("/api/users/company-profile/<user_id>")
def get_company_profile(user_id: str | None = None):
    return jsonify(
        {
            "status": "success",
            "preferences": {},
            "profile": {},
            "user_id": user_id or DEFAULT_USER["id"],
            "degraded": True,
        }
    )


@app.post("/api/users/company-profile")
def update_company_profile():
    data = request.get_json(silent=True) or {}
    return jsonify(
        {
            "status": "success",
            "message": "Company profile accepted in demo mode",
            "preferences": data,
            "degraded": True,
        }
    )


@app.post("/api/message")
def message():
    auth_context = _require_demo_auth()
    if _is_auth_response(auth_context):
        return auth_context
    linked_user = DEMO_LINKS.get(auth_context.clerk_user_id) if auth_context else None
    if auth_context and is_auth_required() and not linked_user:
        return jsonify(
            {
                "status": "error",
                "message": "Link your WhatsApp number before querying receipts.",
                "needs_link": True,
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
        response = (
            "Demo response: invoice drafting would use extracted receipt data "
            "and company profile fields to prepare an invoice document."
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
            "metadata": _demo_metadata(intent),
            "whatsapp_number": whatsapp_number,
            "user_id": (
                linked_user["id"]
                if linked_user
                else data.get("user_id") or DEFAULT_USER["id"]
            ),
        }
    )


@app.post("/api/upload")
def upload():
    auth_context = _require_demo_auth()
    if _is_auth_response(auth_context):
        return auth_context
    linked_user = DEMO_LINKS.get(auth_context.clerk_user_id) if auth_context else None
    if auth_context and is_auth_required() and not linked_user:
        return jsonify(
            {
                "status": "error",
                "message": "Link your WhatsApp number before uploading receipts.",
                "needs_link": True,
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
            "metadata": _demo_metadata("receipt_upload"),
            "type": "file",
            "whatsapp_number": linked_user["whatsapp_number"]
            if linked_user
            else request.form.get("whatsapp_number", DEFAULT_WHATSAPP_NUMBER),
            "user_id": linked_user["id"]
            if linked_user
            else request.form.get("user_id", DEFAULT_USER["id"]),
        }
    )


@app.get("/api/db-status")
def db_status():
    return jsonify(_demo_db_status())


@app.get("/api/agent-flow")
def agent_flow():
    return jsonify(
        {
            "status": "success",
            "intent": "demo_workflow",
            "nodes": [
                "InputRouter",
                "DataExtractorAgent",
                "SupabaseStorage",
                "EmbeddingGenerator",
                "ResponseFormatter",
            ],
            "user_id": DEFAULT_USER["id"],
            "whatsapp_number": DEFAULT_WHATSAPP_NUMBER,
            "file_storage": {},
            "s3_storage": {},
        }
    )


@app.get("/api/step-logs/<step_name>")
def step_logs(step_name: str):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
    return jsonify(
        {
            "status": "success",
            "logs": [
                f"{timestamp} - vercel-demo - INFO - {step_name} ready in hosted UI demo",
                f"{timestamp} - vercel-demo - INFO - Production execution requires configured backend services",
            ],
            "file_storage": {},
            "s3_storage": {},
        }
    )


@app.route("/api/memory/config", methods=["GET", "POST"])
def memory_config():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        MEMORY_CONFIG.update(
            {key: value for key, value in data.items() if key in MEMORY_CONFIG}
        )

    return jsonify({"status": "success", "config": MEMORY_CONFIG, "degraded": True})


@app.get("/api/file-storage-info")
@app.get("/api/s3-info")
def file_storage_info():
    return jsonify(
        {
            "status": "not_found",
            "message": "No files are persisted in the hosted UI demo.",
            "file_storage": {},
            "s3_storage": {},
        }
    ), 404


@app.post("/api/embeddings/update")
def embeddings_update():
    return jsonify(
        {
            "status": "success",
            "message": "Embedding update simulated in hosted UI demo.",
            "result": {
                "item_embeddings": {"updated_count": 0},
                "invoice_embeddings": {"updated_count": 0},
                "force_update": bool((request.get_json(silent=True) or {}).get("force")),
            },
        }
    )


@app.get("/api/check-embeddings")
def check_embeddings():
    return jsonify(
        {
            "status": "success",
            "data": {
                "items_with_embeddings": 0,
                "invoices_with_embeddings": 0,
                "message": "Hosted UI demo is not connected to pgvector.",
            },
        }
    )


@app.post("/api/generate-pdf-invoice")
def generate_pdf_invoice():
    return jsonify(
        {
            "status": "error",
            "message": "Document generation is disabled in the hosted UI demo.",
        }
    ), 501


@app.get("/uploads/<path:filename>")
def uploaded_file(filename: str):
    return jsonify(
        {
            "status": "not_found",
            "message": f"{filename} is not persisted in the hosted UI demo.",
        }
    ), 404
