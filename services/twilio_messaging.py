"""Outbound Twilio helper messages."""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)
_RECENT_PROCESSING_ACKS: dict[str, float] = {}


def _truthy_env(name: str, default: str = "true") -> bool:
    return os.environ.get(name, default).lower() in {"1", "true", "yes"}


def _processing_ack_cooldown_seconds() -> int:
    try:
        return max(0, int(os.environ.get("TWILIO_PROCESSING_ACK_COOLDOWN_SECONDS", "75")))
    except (TypeError, ValueError):
        return 75


def _recent_ack_key(to_number: str, from_number: Optional[str]) -> str:
    return f"{from_number or ''}->{to_number or ''}"


def _processing_ack_recent(to_number: str, from_number: Optional[str]) -> bool:
    cooldown = _processing_ack_cooldown_seconds()
    if cooldown <= 0:
        return False

    now = time.monotonic()
    expired_before = now - (cooldown * 2)
    for key, timestamp in list(_RECENT_PROCESSING_ACKS.items()):
        if timestamp < expired_before:
            _RECENT_PROCESSING_ACKS.pop(key, None)

    last_sent = _RECENT_PROCESSING_ACKS.get(_recent_ack_key(to_number, from_number))
    return last_sent is not None and now - last_sent < cooldown


def _mark_processing_ack_sent(to_number: str, from_number: Optional[str]) -> None:
    _RECENT_PROCESSING_ACKS[_recent_ack_key(to_number, from_number)] = time.monotonic()


def send_processing_ack(to_number: str, body: str, from_number: Optional[str] = None) -> bool:
    """Send an optional out-of-band acknowledgement before long media processing."""

    if not _truthy_env("TWILIO_PROCESSING_ACK_ENABLED"):
        return False
    if _processing_ack_recent(to_number, from_number):
        logger.info("Skipping duplicate Twilio processing acknowledgement during cooldown")
        return False

    sent = send_whatsapp_message(to_number=to_number, body=body, from_number=from_number)
    if sent:
        _mark_processing_ack_sent(to_number, from_number)
    return sent


def send_whatsapp_message(to_number: str, body: str, from_number: Optional[str] = None) -> bool:
    """Send an outbound WhatsApp message through Twilio."""

    if not _truthy_env("TWILIO_OUTBOUND_MESSAGES_ENABLED"):
        return False

    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    sender = from_number or os.environ.get("TWILIO_PHONE_NUMBER")
    if not account_sid or not auth_token or not sender or not to_number or not body:
        return False

    try:
        from twilio.rest import Client

        Client(account_sid, auth_token).messages.create(
            from_=sender,
            to=to_number,
            body=body,
        )
        return True
    except Exception as exc:
        logger.warning("Could not send Twilio outbound message: %s", exc)
        return False
