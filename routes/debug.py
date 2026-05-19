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
