"""Tests for WhatsApp conversation guardrails."""

from services.conversation_policy import (
    compact_whatsapp_message,
    is_off_topic_message,
    media_processing_ack,
    off_topic_response,
)


def test_off_topic_message_is_steered_back_to_receipts():
    assert is_off_topic_message("Who was president in 1960?") is True
    assert "receipts" in off_topic_response().lower()


def test_invoice_and_greeting_messages_stay_in_scope():
    assert is_off_topic_message("Hey") is False
    assert is_off_topic_message("What did I spend on printing in March?") is False


def test_compact_whatsapp_message_truncates_readably():
    message = "line one\n" + ("x" * 200)

    result = compact_whatsapp_message(message, max_chars=80)

    assert len(result) <= 80
    assert "Summary truncated" in result


def test_media_processing_ack_mentions_attachment_count():
    assert "WhatsApp may deliver them one at a time" in media_processing_ack(1)
    assert media_processing_ack(2) == "Received 2 files. I am processing them now and will send a short summary when done."
