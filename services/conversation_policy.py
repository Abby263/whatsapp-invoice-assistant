"""Conversation guardrails and WhatsApp response shaping."""

from __future__ import annotations

import os
import re


DEFAULT_MAX_WHATSAPP_CHARS = 1400

IN_SCOPE_TERMS = {
    "invoice",
    "receipt",
    "ledger",
    "bill",
    "expense",
    "expenses",
    "spend",
    "spent",
    "purchase",
    "purchases",
    "paid",
    "payment",
    "vendor",
    "total",
    "tax",
    "gst",
    "create invoice",
    "generate invoice",
    "upload",
}

GREETING_TERMS = {"hi", "hey", "hello", "help", "start", "menu"}

OFF_TOPIC_TERMS = {
    "weather",
    "president",
    "prime minister",
    "capital of",
    "cricket",
    "football",
    "movie",
    "recipe",
    "stock price",
    "news",
    "write code",
    "homework",
    "history of",
    "who is",
    "what is",
    "tell me about",
}


def is_off_topic_message(text: str) -> bool:
    """Conservatively detect messages outside the assistant scope."""

    normalized = " ".join((text or "").strip().lower().split())
    if not normalized:
        return False
    if normalized in GREETING_TERMS:
        return False
    if any(term in normalized for term in IN_SCOPE_TERMS):
        return False
    if any(term in normalized for term in OFF_TOPIC_TERMS):
        return True

    years = [int(value) for value in re.findall(r"\b(1[0-9]{3}|20[0-9]{2}|21[0-9]{2})\b", normalized)]
    if years and all(year < 2020 or year > 2030 for year in years):
        return True
    return False


def off_topic_response() -> str:
    return (
        "📌 *Business Assistant*\n\n"
        "I can help with receipts, invoices, handwritten expense ledgers, "
        "invoice generation, and questions over saved spending data.\n\n"
        "Send a receipt photo/PDF, or ask: "
        "\"What did I spend on transport in March?\""
    )


def media_processing_ack(media_count: int) -> str:
    try:
        media_count = max(1, int(media_count or 1))
    except (TypeError, ValueError):
        media_count = 1
    noun = "file" if media_count == 1 else "files"
    pronoun = "it" if media_count == 1 else "them"
    article_or_count = "a" if media_count == 1 else str(media_count)
    return (
        "📎 *File Received*\n\n"
        f"Received {article_or_count} {noun}. I am processing {pronoun} now and will send the result here."
    )


def compact_whatsapp_message(message: str, max_chars: int | None = None) -> str:
    """Keep WhatsApp replies readable and bounded."""

    try:
        configured_limit = int(os.environ.get("WHATSAPP_MAX_REPLY_CHARS", DEFAULT_MAX_WHATSAPP_CHARS))
    except (TypeError, ValueError):
        configured_limit = DEFAULT_MAX_WHATSAPP_CHARS
    limit = max_chars or configured_limit
    text = (message or "").strip()
    if len(text) <= limit:
        return text

    suffix = "\n\nSummary truncated. Ask for details if you want the full breakdown."
    truncated = text[: max(0, limit - len(suffix))]
    if "\n" in truncated:
        truncated = truncated.rsplit("\n", 1)[0]
    return truncated.rstrip() + suffix
