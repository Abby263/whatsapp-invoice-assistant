"""Twilio WhatsApp webhook routes."""

from __future__ import annotations

from flask import Blueprint, request

from utils import observability

from . import shared


bp = Blueprint("webhook", __name__)


@bp.post("/webhook")
@bp.post("/api/webhook")
def whatsapp_webhook():
    form_data = request.form.to_dict(flat=True)
    request_id = observability.request_id_from_headers(request.headers) or observability.new_request_id()
    message_sid = form_data.get("MessageSid") or form_data.get("SmsMessageSid")
    with observability.request_context(
        request_id=request_id,
        message_sid=message_sid,
        from_number=shared._mask_number(form_data.get("From")),
    ):
        observability.log_event(
            shared.logger,
            "twilio_webhook_received",
            media_count=form_data.get("NumMedia", "0"),
            body_length=len(form_data.get("Body", "")),
        )
        if not shared._live_backend_enabled():
            backend_config = shared.live_backend.backend_configuration_status()
            observability.log_event(
                shared.logger,
                "twilio_webhook_backend_unconfigured",
                level=shared.logging.WARNING,
                reason=backend_config.get("reason"),
            )
            response = shared._twilio_message_response(
                f"The WhatsApp backend is not configured yet: {backend_config.get('reason')}.",
                status_code=503,
            )
            response.headers["X-Request-ID"] = request_id
            return response
        if not shared._twilio_request_is_valid():
            observability.log_event(
                shared.logger,
                "twilio_webhook_invalid_signature",
                level=shared.logging.WARNING,
            )
            response = shared._twilio_message_response("Invalid Twilio request signature.", status_code=403)
            response.headers["X-Request-ID"] = request_id
            return response

        try:
            result = shared.live_backend.process_twilio_webhook({**form_data, "RequestId": request_id})
            metadata = result.get("metadata", {}) if isinstance(result.get("metadata"), dict) else {}
            if result.get("suppress_twiml_response") or metadata.get("twilio_final_reply_sent"):
                observability.log_event(
                    shared.logger,
                    "twilio_webhook_processed",
                    status=result.get("status", "unknown"),
                    outbound_final_reply_sent=True,
                )
                response = shared._twilio_empty_response()
                response.headers["X-Request-ID"] = request_id
                return response

            message = (
                result.get("message")
                or result.get("content")
                or "I received your message, but could not produce a response."
            )
            message = shared.compact_whatsapp_message(message)
            observability.log_event(
                shared.logger,
                "twilio_webhook_processed",
                status=result.get("status", "unknown"),
            )
            response = shared._twilio_message_response(message)
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            observability.log_event(
                shared.logger,
                "twilio_webhook_failed",
                level=shared.logging.ERROR,
                num_media=form_data.get("NumMedia", "0"),
            )
            shared.logger.exception(
                "Twilio webhook failed message_sid=%s from=%s num_media=%s",
                message_sid,
                shared._mask_number(form_data.get("From")),
                form_data.get("NumMedia", "0"),
            )
            response = shared._twilio_message_response(
                "Something went wrong. Please try again.",
                status_code=500,
            )
            response.headers["X-Request-ID"] = request_id
            return response
