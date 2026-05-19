"""Stable WhatsApp-facing copy for commands and status messages."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional


HELP_COMMANDS = {"hi", "hey", "hello", "help", "start", "menu"}
STATUS_COMMANDS = {"status", "pending", "uploads"}


def normalize_command(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def is_help_message(text: str) -> bool:
    return normalize_command(text) in HELP_COMMANDS


def is_status_message(text: str) -> bool:
    return normalize_command(text) in STATUS_COMMANDS


def build_help_message(pending_count: Optional[int] = None) -> str:
    lines = [
        "*Receipt Intelligence*",
        "",
        "• Send a photo or PDF of a receipt or invoice",
        "• Send a handwritten expense page",
        "• Ask: What did I spend on coffee this month?",
        "• Create invoice for Acme, $500 consulting, due Friday",
        "",
        "After upload, reply with APPROVE <id> or REJECT <id>.",
    ]
    if pending_count is not None:
        lines.extend(["", f"Pending uploads: {pending_count} (reply STATUS)"])
    return "\n".join(lines)


def build_pending_uploads_message(pending_uploads: Iterable[Dict[str, Any]]) -> str:
    uploads = list(pending_uploads)
    if not uploads:
        return (
            "*Pending Uploads*\n\n"
            "No uploads are waiting for approval.\n\n"
            "Send a receipt photo, invoice PDF, or handwritten expense page to begin."
        )

    lines = ["*Pending Uploads*", ""]
    for index, upload in enumerate(uploads, start=1):
        upload_id = upload.get("media_id") or upload.get("id")
        title = str(upload.get("title") or upload.get("filename") or "Upload").strip()
        total = format_money(
            upload.get("total_amount"), upload.get("currency") or "INR"
        )
        date = str(
            upload.get("transaction_date") or upload.get("date") or "date not visible"
        ).strip()
        approval = upload.get("approval_command") or f"APPROVE {upload_id}"
        lines.append(f"{index}. {title} - {date} - {total}")
        lines.append(f"   Reply {approval}")
    if len(uploads) >= 8:
        lines.extend(["", "Showing the most recent 8 pending uploads."])
    return "\n".join(lines)


def format_money(value: Any, currency: str) -> str:
    if value in (None, ""):
        return "total not visible"
    try:
        return f"{float(value):,.2f} {str(currency or '').upper()}".strip()
    except (TypeError, ValueError):
        return f"{value} {str(currency or '').upper()}".strip()
