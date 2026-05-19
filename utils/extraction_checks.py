"""Post-extraction validation checks used before showing WhatsApp review copy."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def apply_extraction_checks(document_data: Dict[str, Any]) -> Dict[str, Any]:
    """Annotate extraction quality with deterministic business-rule warnings."""

    if not isinstance(document_data, dict):
        return {}

    quality = document_data.get("extraction_quality")
    if not isinstance(quality, dict):
        quality = {}
        document_data["extraction_quality"] = quality

    warnings = quality.get("warnings")
    if not isinstance(warnings, list):
        warnings = []
    quality["warnings"] = [str(warning) for warning in warnings if str(warning).strip()]

    financial = (
        document_data.get("financial")
        if isinstance(document_data.get("financial"), dict)
        else {}
    )
    total = _first_number(
        financial.get("total"),
        financial.get("total_amount"),
        document_data.get("total_amount"),
        document_data.get("total"),
    )
    items = (
        document_data.get("items")
        if isinstance(document_data.get("items"), list)
        else []
    )
    item_amounts = [_item_total(item) for item in items if isinstance(item, dict)]
    item_amounts = [amount for amount in item_amounts if amount is not None]

    if total not in (None, 0) and not item_amounts:
        _append_warning(
            quality,
            "No line items were extracted even though a document total was found.",
        )

    if total is not None and item_amounts:
        item_sum = sum(item_amounts)
        tolerance = max(abs(total) * 0.05, 1.0)
        if abs(item_sum - total) > tolerance:
            _append_warning(
                quality,
                (
                    "Line items add up to "
                    f"{item_sum:,.2f}, but the document total shows {total:,.2f}."
                ),
            )

    if not _is_ledger(document_data) and not _visible_date(document_data):
        _append_warning(quality, "Transaction date is not visible.")

    quality["needs_review"] = bool(quality.get("needs_review")) or bool(
        quality["warnings"]
    )
    return document_data


def _append_warning(quality: Dict[str, Any], warning: str) -> None:
    warnings: List[str] = quality.setdefault("warnings", [])
    if warning not in warnings:
        warnings.append(warning)


def _first_number(*values: Any) -> Optional[float]:
    for value in values:
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _item_total(item: Dict[str, Any]) -> Optional[float]:
    total = _first_number(item.get("total_price"), item.get("amount"))
    if total is not None:
        return total
    unit_price = _first_number(item.get("unit_price"))
    if unit_price is None:
        return None
    quantity = _first_number(item.get("quantity")) or 1.0
    return unit_price * quantity


def _is_ledger(document_data: Dict[str, Any]) -> bool:
    additional_info = (
        document_data.get("additional_info")
        if isinstance(document_data.get("additional_info"), dict)
        else {}
    )
    document_type = str(additional_info.get("document_type") or "").lower()
    return "ledger" in document_type


def _visible_date(document_data: Dict[str, Any]) -> bool:
    transaction = (
        document_data.get("transaction")
        if isinstance(document_data.get("transaction"), dict)
        else {}
    )
    value = (
        transaction.get("date")
        or document_data.get("date")
        or document_data.get("invoice_date")
    )
    return bool(str(value or "").strip())
