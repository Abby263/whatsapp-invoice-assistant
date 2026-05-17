"""Phone number normalization helpers."""

from __future__ import annotations

import re
from typing import Optional


def normalize_whatsapp_number(value: Optional[str], default: Optional[str] = None) -> str:
    """Return a canonical WhatsApp number for DB lookups and linking."""

    raw_value = value if value not in {None, ""} else default
    normalized = (raw_value or "").strip()
    if normalized.startswith("whatsapp:"):
        normalized = normalized.replace("whatsapp:", "", 1)

    normalized = re.sub(r"[^\d+]", "", normalized)
    if normalized.startswith("00"):
        normalized = f"+{normalized[2:]}"
    if normalized and not normalized.startswith("+"):
        normalized = f"+{normalized}"

    return normalized
