"""Outbound Twilio helper messages."""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def send_processing_ack(to_number: str, body: str, from_number: Optional[str] = None) -> bool:
    """Send an optional out-of-band acknowledgement before long media processing."""

    if os.environ.get("TWILIO_PROCESSING_ACK_ENABLED", "true").lower() not in {"1", "true", "yes"}:
        return False

    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    sender = from_number or os.environ.get("TWILIO_PHONE_NUMBER")
    if not account_sid or not auth_token or not sender or not to_number:
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
        logger.warning("Could not send Twilio processing acknowledgement: %s", exc)
        return False
