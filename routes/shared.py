"""Shared route helpers for the hosted Flask application."""

from __future__ import annotations

import logging
from xml.sax.saxutils import escape

from flask import Response, jsonify, request

from config.settings import get_settings
from demo import DEMO_LINKS
from services import live_backend
from services.conversation_policy import compact_whatsapp_message
from utils.clerk_auth import (
    ClerkAuthError,
    get_auth_config,
    is_auth_required,
    is_clerk_enabled,
    verify_clerk_request,
)


logger = logging.getLogger("app")


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


def _live_backend_enabled() -> bool:
    return live_backend.is_live_backend_enabled()


def _live_error(exc: Exception, status_code: int = 500):
    return jsonify({"status": "error", "message": str(exc)}), status_code


def _twilio_message_response(message: str, status_code: int = 200):
    try:
        from twilio.twiml.messaging_response import MessagingResponse

        twiml = MessagingResponse()
        twiml.message(message)
        body = str(twiml)
    except Exception:
        body = f"<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response><Message>{escape(message)}</Message></Response>"
    return Response(body, status=status_code, mimetype="application/xml")


def _twilio_empty_response(status_code: int = 200):
    return Response(
        '<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        status=status_code,
        mimetype="application/xml",
    )


def _mask_number(value: str | None) -> str:
    value = value or ""
    if len(value) <= 6:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _twilio_request_is_valid() -> bool:
    raw_setting = get_settings().twilio_validate_requests
    live_backend_enabled = _live_backend_enabled()
    if raw_setting is None or raw_setting.strip() == "":
        should_validate = live_backend_enabled
    else:
        normalized_setting = raw_setting.strip().lower()
        should_validate = normalized_setting in {"1", "true", "yes", "on"}
        if live_backend_enabled and not should_validate:
            logger.warning(
                "Twilio request signature validation is explicitly disabled while the live backend is enabled"
            )

    if not should_validate:
        return True

    try:
        from twilio.request_validator import RequestValidator

        token = get_settings().twilio_auth_token
        signature = request.headers.get("X-Twilio-Signature", "")
        if not token or not signature:
            return False
        url = request.url
        forwarded_proto = request.headers.get("X-Forwarded-Proto")
        forwarded_host = request.headers.get("X-Forwarded-Host") or request.headers.get("Host")
        if forwarded_proto and forwarded_host:
            url = f"{forwarded_proto}://{forwarded_host}{request.full_path.rstrip('?')}"
        return RequestValidator(token).validate(url, request.form.to_dict(flat=True), signature)
    except Exception:
        return False


def _warn_if_twilio_validation_disabled_at_startup() -> None:
    raw_setting = get_settings().twilio_validate_requests
    if raw_setting is None or raw_setting.strip().lower() not in {"0", "false", "no", "off"}:
        return
    if _live_backend_enabled():
        logger.warning(
            "Twilio request signature validation is disabled at startup while the live backend is enabled"
        )
