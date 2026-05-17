"""Canonical LLM output contract for uploaded financial documents."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any, Dict


DOCUMENT_EXTRACTION_JSON_SCHEMA: Dict[str, Any] = {
    "vendor": {
        "name": "string|null",
        "address": "string|null",
        "phone": "string|null",
        "website": "string|null",
        "email": "string|null",
    },
    "transaction": {
        "invoice_number": "string|null",
        "receipt_no": "string|null",
        "date": "YYYY-MM-DD|null",
        "due_date": "YYYY-MM-DD|null",
        "page_number": "string|null",
        "payment_method": "string|null",
        "payment_details": "string|null",
    },
    "items": [
        {
            "description": "string",
            "quantity": "number",
            "unit": "string|null",
            "unit_price": "number",
            "total_price": "number",
            "item_category": "string|null",
            "item_code": "string|null",
            "transaction_date": "YYYY-MM-DD|null",
            "raw_date": "string|null",
            "entry_type": "expense|income|transfer|unknown",
        }
    ],
    "financial": {
        "subtotal": "number|null",
        "tax": {"total": "number|null", "details": []},
        "discount": "number|null",
        "shipping": "number|null",
        "total": "number|null",
        "amount_paid": "number|null",
        "amount_due": "number|null",
        "currency": "ISO-4217 code, default INR when unclear",
    },
    "additional_info": {
        "document_type": "invoice|receipt|handwritten_ledger|statement|unknown",
        "customer": "string|null",
        "store_details": "string|null",
        "notes": "string|null",
        "source_language": "string|null",
        "extraction_notes": "string|null",
    },
    "confidence_score": "number between 0 and 1",
    "error": "string|null",
}


DOCUMENT_EXTRACTION_PROMPT_CONTRACT = f"""
# REQUIRED DOCUMENT EXTRACTION JSON CONTRACT
Return ONLY valid JSON that conforms to this schema. Do not add Markdown,
comments, prose, or placeholder strings.

```json
{json.dumps(DOCUMENT_EXTRACTION_JSON_SCHEMA, indent=2)}
```

Rules:
- Use null when a field is not visible.
- Preserve the original text in item descriptions, including mixed Hindi/English.
- For handwritten ledgers, set additional_info.document_type to "handwritten_ledger".
- For handwritten ledger rows, extract every visible financial row as an item.
- For ledger rows, store the row date in transaction_date when normalized and raw_date when only the written form is visible.
- For ledger rows, set item_code to transaction_date when available so SQL can query row-level dates.
- Use quantity 1 and unit_price = total_price unless a quantity/unit is clearly written.
- Use entry_type "expense", "income", "transfer", or "unknown".
""".strip()


def normalize_document_extraction(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize LLM extraction output into the canonical document schema."""

    normalized = deepcopy(data if isinstance(data, dict) else {})
    vendor = _ensure_dict_section(normalized, "vendor")
    transaction = _ensure_dict_section(normalized, "transaction")
    additional_info = _ensure_dict_section(normalized, "additional_info")
    financial = _ensure_dict_section(normalized, "financial")

    items = normalized.get("items", [])
    if items is None:
        items = []
    elif not isinstance(items, list):
        items = [items]
    normalized["items"] = items

    ledger = is_ledger_document(normalized)
    if ledger:
        if not vendor.get("name"):
            vendor["name"] = "Handwritten ledger"
        if not additional_info.get("document_type"):
            additional_info["document_type"] = "handwritten_ledger"
        if not financial.get("currency"):
            financial["currency"] = "INR"

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            item = {"description": str(item) if item is not None else "Unknown item"}
            items[index] = item
        _normalize_item(item, ledger)
        if item.get("transaction_date") and not transaction.get("date"):
            transaction["date"] = item["transaction_date"]

    for key in ("subtotal", "discount", "shipping", "total", "amount_paid", "amount_due"):
        if financial.get(key) is not None:
            financial[key] = coerce_number(financial[key], 0.0)

    tax = financial.get("tax")
    if isinstance(tax, dict):
        if tax.get("total") is not None:
            tax["total"] = coerce_number(tax["total"], 0.0)
        details = tax.get("details")
        if isinstance(details, list):
            for detail in details:
                if isinstance(detail, dict) and detail.get("amount") is not None:
                    detail["amount"] = coerce_number(detail["amount"], 0.0)

    if is_ledger_document(normalized):
        financial.setdefault("currency", "INR")
        if financial.get("total") is None:
            financial["total"] = sum(
                coerce_number(item.get("total_price"), 0.0)
                for item in items
                if isinstance(item, dict)
                and str(item.get("entry_type", "")).lower() != "income"
            )

    return normalized


def is_ledger_document(data: Dict[str, Any]) -> bool:
    """Return whether extracted data represents a handwritten ledger document."""

    if not isinstance(data, dict):
        return False
    additional_info = data.get("additional_info", {})
    additional = additional_info if isinstance(additional_info, dict) else {}
    document_type = str(additional.get("document_type") or "").lower()
    if any(value in document_type for value in ("ledger", "account_book", "notebook")):
        return True

    vendor = data.get("vendor", {})
    vendor_name = vendor.get("name") if isinstance(vendor, dict) else vendor
    if "ledger" in str(vendor_name or "").lower():
        return True

    items = data.get("items") or []
    if not isinstance(items, list):
        return False
    dated_items = sum(
        1
        for item in items
        if isinstance(item, dict)
        and (item.get("transaction_date") or item.get("raw_date") or item.get("entry_type"))
    )
    return dated_items >= 2


def coerce_number(value: Any, default: float = 0.0) -> float:
    """Convert LLM number-like values into floats without raising."""

    if value in (None, ""):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^\d.\-]", "", str(value))
    if cleaned in ("", "-", ".", "-."):
        return default
    try:
        return float(cleaned)
    except (TypeError, ValueError):
        return default


def _ensure_dict_section(data: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = data.get(key, {})
    if isinstance(value, dict):
        data[key] = value
        return value
    data[key] = {"name": str(value)} if key == "vendor" and value else {}
    return data[key]


def _normalize_item(item: Dict[str, Any], ledger: bool) -> None:
    if item.get("amount") is not None and item.get("total_price") is None:
        item["total_price"] = item.get("amount")
    if item.get("price") is not None and item.get("unit_price") is None:
        item["unit_price"] = item.get("price")

    item["description"] = str(
        item.get("description") or ("Ledger entry" if ledger else "Unknown item")
    ).strip()
    item["quantity"] = coerce_number(item.get("quantity"), 1.0) or 1.0

    if item.get("total_price") is not None:
        item["total_price"] = coerce_number(item["total_price"], 0.0)
    if item.get("unit_price") is not None:
        item["unit_price"] = coerce_number(item["unit_price"], 0.0)
    if item.get("total_price") is None and item.get("unit_price") is not None:
        item["total_price"] = item["unit_price"] * item["quantity"]
    if item.get("unit_price") is None and item.get("total_price") is not None:
        item["unit_price"] = item["total_price"] / item["quantity"]

    if ledger:
        item.setdefault("entry_type", "unknown")
        item["entry_type"] = str(item["entry_type"]).lower()
        item.setdefault("unit", "entry")
        item.setdefault("item_category", item["entry_type"] or "ledger_entry")

        if item.get("transaction_date") and not item.get("item_code"):
            item["item_code"] = item["transaction_date"]
        elif item.get("raw_date") and not item.get("item_code"):
            item["item_code"] = item["raw_date"]
        if item.get("item_code"):
            item["item_code"] = str(item["item_code"])[:50]
        if item.get("item_category"):
            item["item_category"] = str(item["item_category"])[:50]

        prefixes = [
            str(item.get("transaction_date") or "").strip(),
            str(item.get("raw_date") or "").strip(),
        ]
        for prefix in reversed([value for value in prefixes if value]):
            if prefix not in item["description"]:
                item["description"] = f"{prefix} - {item['description']}"
