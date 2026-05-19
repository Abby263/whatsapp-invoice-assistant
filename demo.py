"""Hosted demo state and helpers for the Vercel Flask app."""

from __future__ import annotations

from datetime import datetime, timezone


DEFAULT_WHATSAPP_NUMBER = "+1234567890"
DEFAULT_USER = {
    "id": "demo-user",
    "name": "Demo Operator",
    "email": "demo@example.com",
    "whatsapp_number": DEFAULT_WHATSAPP_NUMBER,
}
DEMO_LINKS: dict[str, dict] = {}
DEMO_GENERATED_INVOICES: list[dict] = []


def demo_metadata(intent: str) -> dict:
    return {
        "intent": intent,
        "token_usage": {
            "input_tokens": 128,
            "output_tokens": 224,
            "total_tokens": 352,
        },
        "environment": "vercel-ui-demo",
    }


def demo_db_status() -> dict:
    return {
        "status": "success",
        "connection_status": {
            "success": False,
            "message": "Hosted UI demo is not connected to a private Supabase database.",
        },
        "counts": {
            "invoices": {
                "total": 0,
                "user_specific": 0,
            },
            "items": 0,
            "user_items": 0,
        },
        "size_info": {
            "total_size": "Demo mode",
            "tables_size": "Demo mode",
        },
        "connection_info": {"database": {"provider": "demo"}},
        "vector_info": {
            "installed": False,
            "with_embeddings": 0,
            "without_embeddings": 0,
        },
    }


def demo_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def demo_generated_invoice(user: dict, source: str, payload: dict | None = None) -> dict:
    invoice_id = len(DEMO_GENERATED_INVOICES) + 1
    now = datetime.now(timezone.utc)
    payload = payload or {}
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    if not items:
        items = [
            {
                "description": payload.get("description") or "Consulting services",
                "quantity": 1,
                "unit_price": 500,
                "total_price": 500,
            }
        ]
    normalized_items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        quantity = demo_float(item.get("quantity"), 1)
        unit_price = demo_float(item.get("unit_price") or item.get("price"), 0)
        total_price = demo_float(item.get("total_price") or item.get("amount"), quantity * unit_price)
        normalized_items.append(
            {
                "description": item.get("description") or "Service",
                "quantity": quantity,
                "unit_price": unit_price,
                "total_price": total_price,
            }
        )
    subtotal = sum(item["total_price"] for item in normalized_items)
    tax_rate = demo_float(payload.get("tax_rate") or 0)
    tax_amount = subtotal * tax_rate / 100
    total_amount = subtotal + tax_amount
    return {
        "id": invoice_id,
        "user_id": user["id"],
        "source": source,
        "status": "generated",
        "invoice_number": f"INV-DEMO-{invoice_id:04d}",
        "invoice_date": now.date().isoformat(),
        "due_date": payload.get("due_date") or now.date().isoformat(),
        "client_name": payload.get("client_name") or "Demo Client",
        "client_company": payload.get("client_company") or "Demo Client LLC",
        "client_email": payload.get("client_email") or "client@example.com",
        "currency": (payload.get("currency") or "USD").upper()[:3],
        "subtotal": subtotal,
        "tax_amount": tax_amount,
        "discount_amount": 0,
        "total_amount": total_amount,
        "payment_terms": payload.get("payment_terms") or "Due on receipt",
        "document_url": "/api/generated-invoices/demo-invoice.txt",
        "pdf_url": None,
        "items": normalized_items,
        "created_at": now.isoformat(),
    }


def demo_generated_invoice_stats(invoices: list[dict]) -> dict:
    return {
        "count": len(invoices),
        "total_amount": sum(float(invoice.get("total_amount") or 0) for invoice in invoices),
        "by_status": {
            "generated": len([invoice for invoice in invoices if invoice.get("status") == "generated"])
        },
        "recent": invoices[:5],
    }
