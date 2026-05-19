"""HTML, favicon, and health routes for the hosted app."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, render_template

from . import shared


bp = Blueprint("web", __name__)


@bp.get("/")
def home():
    return render_template("index.html")


@bp.get("/overview")
@bp.get("/chat")
@bp.get("/receipts")
@bp.get("/inspector")
@bp.get("/settings")
def workspace_route():
    return render_template("index.html")


@bp.get("/favicon.ico")
def favicon():
    return current_app.send_static_file("favicon.ico")


@bp.get("/health")
def health():
    backend_config = shared.live_backend.backend_configuration_status()
    return jsonify(
        {
            "status": "ok",
            "runtime": "vercel-production" if backend_config["enabled"] else "vercel-ui-demo",
            "backend_enabled": backend_config["enabled"],
            "backend_config": backend_config,
            "webhook_path": "/webhook",
        }
    )
