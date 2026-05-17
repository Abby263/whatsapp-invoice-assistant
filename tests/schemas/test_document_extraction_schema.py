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


def test_ledger_row_dates_override_wrong_page_heading_date_and_quality_is_recorded():
    raw = {
        "vendor": {"name": None},
        "transaction": {"date": "2026-02-15"},
        "items": [
            {
                "description": "15.5.26 - Transport BPMC unique ch",
                "amount": "225",
                "transaction_date": "2026-02-15",
                "entry_type": "expense",
            },
            {
                "description": "21.5.26 - Received LR",
                "amount": "1000",
                "entry_type": "income",
            },
        ],
        "financial": {"total": 99999, "currency": "INR"},
        "additional_info": {"document_type": "handwritten_ledger"},
        "extraction_quality": {
            "visible_financial_rows": 3,
            "extracted_financial_rows": 2,
            "needs_review": False,
            "warnings": [],
        },
        "confidence_score": 0.8,
    }

    result = normalize_document_extraction(raw)

    assert result["items"][0]["transaction_date"] == "2026-05-15"
    assert result["items"][0]["item_code"] == "2026-05-15"
    assert result["items"][1]["transaction_date"] == "2026-05-21"
    assert result["financial"]["total"] == 225.0
    assert result["extraction_quality"]["needs_review"] is True
    assert result["extraction_quality"]["visible_financial_rows"] == 3.0
    assert result["extraction_quality"]["extracted_financial_rows"] == 2.0
    assert any("visible financial rows" in warning for warning in result["extraction_quality"]["warnings"])
    assert any("Ledger total adjusted" in warning for warning in result["extraction_quality"]["warnings"])


def test_invalid_ledger_row_date_is_not_normalized():
    result = normalize_document_extraction({
        "items": [
            {
                "description": "31.2.26 - unreadable date row",
                "amount": "100",
                "entry_type": "expense",
            }
        ],
        "financial": {"currency": "INR"},
        "additional_info": {"document_type": "handwritten_ledger"},
    })

    assert result["items"][0].get("transaction_date") is None
    assert result["items"][0]["item_code"] == "31.2.26"
