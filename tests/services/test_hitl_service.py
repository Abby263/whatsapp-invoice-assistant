"""Tests for WhatsApp human-in-the-loop approval commands."""

from pathlib import Path

import pytest

from langchain_app import file_processing_workflow
from services import hitl_service


@pytest.mark.asyncio
async def test_delete_request_requires_whatsapp_confirmation(monkeypatch):
    async def fake_classify_hitl_intent(*args, **kwargs):
        return {"action": "request_delete", "target_scope": "all", "target_id": None}

    monkeypatch.setattr(hitl_service, "classify_hitl_intent", fake_classify_hitl_intent)

    result = await hitl_service.handle_human_confirmation_message(
        "delete all my receipt history",
        "1",
    )

    assert result is not None
    assert "Deletion needs WhatsApp confirmation" in result["content"]
    assert "CONFIRM DELETE ALL" in result["content"]
    assert result["metadata"]["confirmation_required"] is True


@pytest.mark.asyncio
async def test_delete_all_records_requires_exact_whatsapp_confirmation(monkeypatch):
    async def fake_classify_hitl_intent(*args, **kwargs):
        return {"action": "request_delete", "target_scope": "all", "target_id": None}

    monkeypatch.setattr(hitl_service, "classify_hitl_intent", fake_classify_hitl_intent)

    result = await hitl_service.handle_human_confirmation_message(
        "delete all my records",
        "1",
    )

    assert result is not None
    assert "Deletion needs WhatsApp confirmation" in result["content"]
    assert "CONFIRM DELETE ALL" in result["content"]
    assert result["metadata"]["confirmation_command"] == "CONFIRM DELETE ALL"


@pytest.mark.asyncio
async def test_all_reply_reminds_exact_delete_confirmation_command(monkeypatch):
    async def fake_classify_hitl_intent(*args, **kwargs):
        return {"action": "select_delete_scope", "target_scope": "all", "target_id": None}

    monkeypatch.setattr(hitl_service, "classify_hitl_intent", fake_classify_hitl_intent)

    result = await hitl_service.handle_human_confirmation_message(
        "All",
        "1",
    )

    assert result is not None
    assert "CONFIRM DELETE ALL" in result["content"]
    assert result["metadata"]["confirmation_required"] is True
    assert result["metadata"]["confirmation_command"] == "CONFIRM DELETE ALL"


@pytest.mark.asyncio
async def test_confirm_delete_executes_with_confirmation(monkeypatch):
    captured = {}

    async def fake_classify_hitl_intent(*args, **kwargs):
        return {"action": "confirm_delete", "target_scope": "receipt", "target_id": 12}

    def fake_delete_user_history(user_id, payload):
        captured["user_id"] = user_id
        captured["payload"] = payload
        return {
            "status": "success",
            "deleted": {
                "documents": 1,
                "media": 1,
                "generated_invoices": 0,
                "storage_files": 1,
            },
        }

    monkeypatch.setattr(hitl_service, "classify_hitl_intent", fake_classify_hitl_intent)
    monkeypatch.setattr(hitl_service, "delete_user_history", fake_delete_user_history)

    result = await hitl_service.handle_human_confirmation_message(
        "CONFIRM DELETE RECEIPT 12",
        "7",
    )

    assert captured == {
        "user_id": 7,
        "payload": {
            "scope": "document",
            "kind": "invoice",
            "id": 12,
            "confirmed": True,
        },
    }
    assert "Deletion confirmed" in result["content"]


@pytest.mark.asyncio
async def test_approve_pending_extraction_downloads_and_reprocesses(monkeypatch):
    class FakeStorage:
        def __init__(self, bucket_name=None):
            self.bucket_name = bucket_name

        def download_file(self, file_key):
            assert file_key == "users/1/invoices/aa/checksum"
            return b"receipt-image"

    async def fake_process_invoice_file(
        file_path,
        file_type,
        file_name,
        user_id,
        conversation_history,
        validation_result=None,
        file_metadata=None,
        hitl_confirmed=False,
    ):
        assert Path(file_path).exists()
        assert file_type == "image"
        assert file_name == "receipt.jpg"
        assert user_id == "1"
        assert hitl_confirmed is True
        assert file_metadata["media_record"]["media_id"] == "77"
        assert file_metadata["file_storage"]["file_key"] == "users/1/invoices/aa/checksum"
        return {
            "content": "Document extraction result\nstatus: saved",
            "metadata": {"stored_in_database": True, "invoice_id": "101"},
            "confidence": 0.85,
        }

    async def fake_classify_hitl_intent(*args, **kwargs):
        return {"action": "approve_upload", "target_scope": "upload", "target_id": 77}

    monkeypatch.setattr(hitl_service, "classify_hitl_intent", fake_classify_hitl_intent)
    monkeypatch.setattr(hitl_service, "SupabaseStorageHandler", FakeStorage)
    monkeypatch.setattr(
        hitl_service,
        "_load_user_media",
        lambda user_id, media_id: {
            "status": "success",
            "media_id": media_id,
            "invoice_id": None,
            "filename": "receipt.jpg",
            "original_filename": "receipt.jpg",
            "file_path": "users/1/invoices/aa/checksum",
            "content_type": "image/jpeg",
            "content_hash": "checksum",
            "file_storage": {
                "bucket": "receipts",
                "file_key": "users/1/invoices/aa/checksum",
                "content_type": "image/jpeg",
                "media_id": "77",
            },
        },
    )
    monkeypatch.setattr(file_processing_workflow, "detect_file_type", lambda *args: "image")
    monkeypatch.setattr(file_processing_workflow, "process_invoice_file", fake_process_invoice_file)

    result = await hitl_service.handle_human_confirmation_message("APPROVE 77", "1")

    assert result["metadata"]["hitl_status"] == "confirmed"
    assert result["metadata"]["approved_media_id"] == "77"
    assert result["metadata"]["invoice_id"] == "101"


@pytest.mark.asyncio
async def test_review_pending_upload_from_web_requires_whatsapp(monkeypatch):
    async def fake_approve(*_args, **_kwargs):
        raise AssertionError("web approval must not approve pending uploads")

    def fake_reject(*_args, **_kwargs):
        raise AssertionError("web approval must not reject pending uploads")

    monkeypatch.setattr(hitl_service, "approve_pending_extraction", fake_approve)
    monkeypatch.setattr(hitl_service, "reject_pending_upload", fake_reject)

    result = await hitl_service.review_pending_upload_from_web("7", 77, "approve")

    assert result["status"] == "error"
    assert result["metadata"]["hitl_status"] == "whatsapp_required"
    assert "APPROVE 77" in result["message"]
    assert "REJECT 77" in result["message"]
