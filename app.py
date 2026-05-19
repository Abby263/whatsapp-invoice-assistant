"""Vercel entrypoint for the hosted Receipt Intelligence UI.

The production worker/API paths in this repository need Supabase, OpenAI, and
WhatsApp credentials. This adapter keeps the public Vercel deployment focused
on the operator UI so reviewers can inspect the workflow without provisioning
private infrastructure.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify

from demo import (
    DEMO_GENERATED_INVOICES,
    DEMO_LINKS,
    DEFAULT_USER,
    DEFAULT_WHATSAPP_NUMBER,
    demo_db_status as _demo_db_status,
    demo_float as _demo_float,
    demo_generated_invoice as _demo_generated_invoice,
    demo_generated_invoice_stats as _demo_generated_invoice_stats,
    demo_metadata as _demo_metadata,
)
from routes import register_blueprints
from routes import shared


PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")


app = Flask(
    __name__,
    template_folder=str(PROJECT_ROOT / "ui" / "templates"),
    static_folder=str(PROJECT_ROOT / "ui" / "static"),
    static_url_path="/static",
)
register_blueprints(app)
shared._warn_if_twilio_validation_disabled_at_startup()


live_backend = shared.live_backend
get_auth_config = shared.get_auth_config
is_auth_required = shared.is_auth_required
is_clerk_enabled = shared.is_clerk_enabled
verify_clerk_request = shared.verify_clerk_request
_require_demo_auth = shared._require_demo_auth
_auth_identity_payload = shared._auth_identity_payload
_is_auth_response = shared._is_auth_response
_live_backend_enabled = shared._live_backend_enabled
_live_error = shared._live_error
_twilio_message_response = shared._twilio_message_response
_twilio_empty_response = shared._twilio_empty_response
_mask_number = shared._mask_number
_twilio_request_is_valid = shared._twilio_request_is_valid
_warn_if_twilio_validation_disabled_at_startup = shared._warn_if_twilio_validation_disabled_at_startup
