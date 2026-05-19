"""Tests for WhatsApp conversation guardrails."""

from services.conversation_policy import (
    compact_whatsapp_message,
    is_off_topic_message,
    media_processing_ack,
    off_topic_response,
)
from services.whatsapp_copy import (
    build_greeting_message,
    build_help_message,
    build_pending_uploads_message,
    is_help_message,
)


def test_off_topic_message_is_steered_back_to_receipts():
    assert is_off_topic_message("Who was president in 1960?") is True
    assert "receipts" in off_topic_response().lower()
    assert "*Business Assistant*" in off_topic_response()


def test_invoice_and_greeting_messages_stay_in_scope():
    assert is_off_topic_message("Hey") is False
    assert is_off_topic_message("How are you?") is False
    assert is_off_topic_message("What did I spend on printing in March?") is False
    assert is_off_topic_message("What is the pending status?") is False


def test_only_command_words_are_deterministic_help_messages():
    assert is_help_message("help") is True
    assert is_help_message("menu") is True
    assert is_help_message("start") is True
    assert is_help_message("How are you") is False
    assert is_help_message("What's up?") is False
    assert is_help_message("What can you do?") is False
    assert is_help_message("How much did I spend?") is False


def test_compact_whatsapp_message_truncates_readably():
    message = "line one\n" + ("x" * 200)

    result = compact_whatsapp_message(message, max_chars=80)

    assert len(result) <= 80
    assert "Summary truncated" in result


def test_media_processing_ack_mentions_attachment_count():
    assert media_processing_ack(1) == (
        "📎 *File Received*\n\n"
        "Received a file. I am processing it now and will send the result here."
    )
    assert "forwarded multiple images" not in media_processing_ack(1)
    assert media_processing_ack(2) == (
        "📎 *File Received*\n\n"
        "Received 2 files. I am processing them now and will send the result here."
    )


def test_help_message_is_deterministic_and_mentions_status():
    message = build_help_message(pending_count=2)

    assert "Receipt Intelligence" in message
    assert "APPROVE <id>" in message
    assert "Pending uploads: 2" in message


def test_greeting_message_answers_naturally_without_showing_help_menu():
    message = build_greeting_message()

    assert "doing well" in message
    assert "ready to help" in message
    assert "Receipt Intelligence" not in message
    assert "Business Assistant" not in message


def test_pending_uploads_message_lists_approval_commands():
    message = build_pending_uploads_message(
        [
            {
                "media_id": "77",
                "title": "Cafe receipt",
                "transaction_date": "2026-05-18",
                "total_amount": 450,
                "currency": "INR",
                "approval_command": "APPROVE 77",
            }
        ]
    )

    assert "Cafe receipt" in message
    assert "450.00 INR" in message
    assert "Reply APPROVE 77" in message
