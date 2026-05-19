"""Outbound Twilio helper messages."""

from __future__ import annotations

import logging
import hashlib
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


def _recent_ack_key(
    to_number: str,
    from_number: Optional[str],
    dedupe_key: Optional[str] = None,
) -> str:
    key = f"{from_number or ''}->{to_number or ''}"
    if dedupe_key:
        return f"{key}:{dedupe_key}"
    return key


def _persistent_ack_key(
    to_number: str,
    from_number: Optional[str],
    cooldown: int,
    dedupe_key: Optional[str] = None,
) -> str:
    if dedupe_key:
        pair = f"{_recent_ack_key(to_number, from_number)}:{dedupe_key}"
        pair_hash = hashlib.sha256(pair.encode("utf-8")).hexdigest()[:32]
        return f"processing_ack:{pair_hash}"
    slot = int(time.time() // max(cooldown, 1))
    pair = _recent_ack_key(to_number, from_number)
    pair_hash = hashlib.sha256(pair.encode("utf-8")).hexdigest()[:24]
    return f"processing_ack:{pair_hash}:{slot}"


def _processing_ack_recent(
    to_number: str,
    from_number: Optional[str],
    dedupe_key: Optional[str] = None,
) -> bool:
    cooldown = _processing_ack_cooldown_seconds()
    if cooldown <= 0:
        return False

    now = time.monotonic()
    expired_before = now - (cooldown * 2)
    for key, timestamp in list(_RECENT_PROCESSING_ACKS.items()):
        if timestamp < expired_before:
            _RECENT_PROCESSING_ACKS.pop(key, None)

    last_sent = _RECENT_PROCESSING_ACKS.get(
        _recent_ack_key(to_number, from_number, dedupe_key)
    )
    return last_sent is not None and now - last_sent < cooldown


def _mark_processing_ack_sent(
    to_number: str,
    from_number: Optional[str],
    dedupe_key: Optional[str] = None,
) -> None:
    _RECENT_PROCESSING_ACKS[
        _recent_ack_key(to_number, from_number, dedupe_key)
    ] = time.monotonic()


def _claim_processing_ack_in_database(
    to_number: str,
    from_number: Optional[str],
    dedupe_key: Optional[str] = None,
) -> Optional[bool]:
    """Return whether this request owns the shared acknowledgement slot.

    Vercel can run simultaneous webhook requests on different function
    instances, so the in-memory cooldown is only a fallback. The unique
    whatsapp_message_id claim makes rapid media webhooks from the same sender
    dedupe across instances without adding another table.
    """

    if not _truthy_env("TWILIO_PROCESSING_ACK_DATABASE_DEDUPE_ENABLED"):
        return None

    cooldown = _processing_ack_cooldown_seconds()
    if cooldown <= 0:
        return True

    try:
        from sqlalchemy import text

        from database.connection import ensure_application_schema, get_db_session

        ensure_application_schema()
        session = get_db_session()
        try:
            result = session.execute(
                text(
                    """
                    INSERT INTO whatsapp_messages
                        (whatsapp_message_id, status, created_at, updated_at)
                    VALUES
                        (:dedupe_key, 'SENT', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (whatsapp_message_id) DO NOTHING
                    """
                ),
                {
                    "dedupe_key": _persistent_ack_key(
                        to_number,
                        from_number,
                        cooldown,
                        dedupe_key=dedupe_key,
                    )
                },
            )
            session.commit()
            return result.rowcount == 1
        finally:
            session.close()
    except Exception as exc:
        logger.info("Falling back to in-memory Twilio ack debounce: %s", exc)
        return None


def send_processing_ack(
    to_number: str,
    body: str,
    from_number: Optional[str] = None,
    dedupe_key: Optional[str] = None,
) -> bool:
    """Send an optional out-of-band acknowledgement before long media processing."""

    if not _truthy_env("TWILIO_PROCESSING_ACK_ENABLED"):
        return False
    if _processing_ack_recent(to_number, from_number, dedupe_key=dedupe_key):
        logger.info(
            "Skipping duplicate Twilio processing acknowledgement during cooldown"
        )
        return False

    database_claimed = _claim_processing_ack_in_database(
        to_number,
        from_number,
        dedupe_key=dedupe_key,
    )
    if database_claimed is False:
        logger.info(
            "Skipping duplicate Twilio processing acknowledgement from shared cooldown"
        )
        return False

    sent = send_whatsapp_message(
        to_number=to_number, body=body, from_number=from_number
    )
    if sent:
        _mark_processing_ack_sent(to_number, from_number, dedupe_key=dedupe_key)
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
