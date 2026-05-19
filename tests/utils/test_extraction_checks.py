"""Tests for deterministic extraction quality checks."""

from utils.extraction_checks import apply_extraction_checks


def test_extraction_checks_warn_when_items_do_not_match_total():
    data = {
        "vendor": {"name": "Cafe"},
        "transaction": {"date": "2026-05-18"},
        "financial": {"total": 1450, "currency": "INR"},
        "items": [
            {"description": "Latte", "total_price": 120},
            {"description": "Sandwich", "total_price": 280},
        ],
    }

    result = apply_extraction_checks(data)

    quality = result["extraction_quality"]
    assert quality["needs_review"] is True
    assert any("Line items add up" in warning for warning in quality["warnings"])


def test_extraction_checks_accept_matching_totals():
    data = {
        "transaction": {"date": "2026-05-18"},
        "financial": {"total": 400, "currency": "INR"},
        "items": [
            {"description": "Latte", "total_price": 120},
            {"description": "Sandwich", "total_price": 280},
        ],
    }

    result = apply_extraction_checks(data)

    assert result["extraction_quality"]["needs_review"] is False
    assert result["extraction_quality"]["warnings"] == []
