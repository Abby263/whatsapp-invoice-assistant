"""Tests for deterministic WhatsApp text UX routing."""

import pytest

from workflows import text_processing_workflow


@pytest.mark.asyncio
async def test_help_message_skips_llm_intent_classifier(monkeypatch):
    async def fail_classify(*_args, **_kwargs):
        raise AssertionError("help should not call the LLM classifier")

    monkeypatch.setattr(text_processing_workflow, "classify_intent", fail_classify)
    monkeypatch.setattr(
        text_processing_workflow, "count_pending_uploads", lambda user_id: 2
    )

    result = await text_processing_workflow.process_text_message("help", user_id="1")

    assert result["metadata"]["scope"] == "deterministic_help"
    assert "Receipt Intelligence" in result["content"]
    assert "Pending uploads: 2" in result["content"]


@pytest.mark.asyncio
async def test_status_message_skips_llm_intent_classifier(monkeypatch):
    async def fail_classify(*_args, **_kwargs):
        raise AssertionError("STATUS should not call the LLM classifier")

    monkeypatch.setattr(text_processing_workflow, "classify_intent", fail_classify)
    monkeypatch.setattr(
        text_processing_workflow,
        "build_pending_upload_status",
        lambda user_id: {
            "content": "*Pending Uploads*\n\n1. Cafe - APPROVE 77",
            "confidence": 0.95,
            "metadata": {"scope": "pending_uploads"},
        },
    )

    result = await text_processing_workflow.process_text_message("STATUS", user_id="1")

    assert result["metadata"]["scope"] == "pending_uploads"
    assert "APPROVE 77" in result["content"]
