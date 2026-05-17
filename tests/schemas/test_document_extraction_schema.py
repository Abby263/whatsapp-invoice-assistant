"""Tests for canonical LLM document extraction schema helpers."""

from schemas.llm_outputs import is_ledger_document, normalize_document_extraction


def test_normalize_handwritten_ledger_rows_for_storage_and_sql():
    raw = {
        "vendor": {"name": None},
        "transaction": {},
        "items": [
            {
                "description": "Printing Aminabad Adv.",
                "amount": "500",
                "transaction_date": "2026-02-15",
                "raw_date": "15.2.26",
                "entry_type": "expense",
            },
            {
                "description": "Received from DM Delhi",
                "amount": "10000",
                "transaction_date": "2026-03-12",
                "entry_type": "income",
            },
        ],
        "financial": {"currency": "INR"},
        "additional_info": {"document_type": "handwritten_ledger"},
    }

    result = normalize_document_extraction(raw)

    assert is_ledger_document(result) is True
    assert result["vendor"]["name"] == "Handwritten ledger"
    assert result["financial"]["total"] == 500.0
    assert result["items"][0]["unit_price"] == 500.0
    assert result["items"][0]["total_price"] == 500.0
    assert result["items"][0]["item_code"] == "2026-02-15"
    assert result["items"][0]["item_category"] == "expense"
    assert "15.2.26" in result["items"][0]["description"]
