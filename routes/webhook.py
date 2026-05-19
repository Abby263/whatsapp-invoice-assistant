"""Twilio WhatsApp webhook routes."""

from __future__ import annotations

from flask import Blueprint, request

from . import shared


bp = Blueprint("webhook", __name__)


@bp.post("/webhook")
@bp.post("/api/webhook")
def whatsapp_webhook():
    form_data = request.form.to_dict(flat=True)
    shared.logger.info(
        "Twilio webhook received from %s with NumMedia=%s and Body length=%s",
        shared._mask_number(form_data.get("From")),
        form_data.get("NumMedia", "0"),
        len(form_data.get("Body", "")),
    )
    if not shared._live_backend_enabled():
        backend_config = shared.live_backend.backend_configuration_status()
        shared.logger.warning(
            "Twilio webhook rejected because backend is not configured: %s",
            backend_config.get("reason"),
        )
        return shared._twilio_message_response(
            f"The WhatsApp backend is not configured yet: {backend_config.get('reason')}.",
            status_code=503,
        )
    if not shared._twilio_request_is_valid():
        shared.logger.warning("Twilio webhook rejected because request signature was invalid")
        return shared._twilio_message_response("Invalid Twilio request signature.", status_code=403)

    try:
        result = shared.live_backend.process_twilio_webhook(form_data)
        metadata = result.get("metadata", {}) if isinstance(result.get("metadata"), dict) else {}
        if result.get("suppress_twiml_response") or metadata.get("twilio_final_reply_sent"):
            shared.logger.info("Twilio webhook processed with outbound final reply")
            return shared._twilio_empty_response()

        message = (
            result.get("message")
            or result.get("content")
            or "I received your message, but could not produce a response."
        )
        message = shared.compact_whatsapp_message(message)
        shared.logger.info("Twilio webhook processed with status=%s", result.get("status", "unknown"))
        return shared._twilio_message_response(message)
    except Exception:
        shared.logger.exception(
            "Twilio webhook failed message_sid=%s from=%s num_media=%s",
            form_data.get("MessageSid") or form_data.get("SmsMessageSid"),
            shared._mask_number(form_data.get("From")),
            form_data.get("NumMedia", "0"),
        )
        return shared._twilio_message_response(
            "Something went wrong. Please try again.",
            status_code=500,
        )
