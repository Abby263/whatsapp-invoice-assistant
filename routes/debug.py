"""Diagnostic and maintenance endpoints for the hosted app."""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from . import shared


bp = Blueprint("debug", __name__)


@bp.get("/api/agent-flow")
def agent_flow():
    auth_context = shared._require_demo_auth()
    if shared._is_auth_response(auth_context):
        return auth_context
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
            "user_id": None,
            "whatsapp_number": None,
            "file_storage": {},
        }
    )


@bp.get("/api/step-logs/<step_name>")
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
        }
    )


@bp.post("/api/embeddings/update")
def embeddings_update():
    auth_context = shared._require_demo_auth()
    if shared._is_auth_response(auth_context):
        return auth_context
    if shared._live_backend_enabled():
        return jsonify(
            {
                "status": "error",
                "message": "Embedding maintenance is disabled on the hosted live backend.",
            }
        ), 403
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


@bp.get("/api/check-embeddings")
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


def _job_runner_authorized(settings, payload) -> bool:
    auth_header = request.headers.get("Authorization", "")
    if settings.cron_secret and auth_header == f"Bearer {settings.cron_secret}":
        return True
    supplied_secret = payload.get("secret") or payload.get("job_secret")
    if settings.async_job_secret and supplied_secret == settings.async_job_secret:
        return True
    return False


@bp.route("/api/jobs/run", methods=["GET", "POST"])
def jobs_run():
    payload = (
        request.get_json(silent=True) or {}
        if request.method == "POST"
        else request.args.to_dict(flat=True)
    )
    settings = shared.get_settings()
    auth_context = None
    runner_authorized = _job_runner_authorized(settings, payload)
    if request.method == "GET" and not runner_authorized:
        return jsonify({"status": "error", "message": "Unauthorized job runner"}), 401
    if not runner_authorized:
        auth_context = shared._require_demo_auth()
        if shared._is_auth_response(auth_context):
            return auth_context
    elif settings.async_job_secret and not payload.get("secret"):
        payload = {**payload, "secret": settings.async_job_secret}
    if not shared._live_backend_enabled():
        return jsonify(
            {
                "status": "success",
                "message": "No queued production jobs run in hosted UI demo.",
                "processed": [],
                "count": 0,
                "degraded": True,
            }
        )
    result = shared.live_backend.run_async_jobs(auth_context, payload)
    status_code = 403 if result.get("status") == "error" else 200
    return jsonify(result), status_code
