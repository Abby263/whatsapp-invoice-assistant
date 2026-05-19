"""Tests for WhatsApp human-in-the-loop approval commands."""

from pathlib import Path

import pytest

from workflows import file_processing_workflow
from services import hitl_service


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("APPROVE 77", {"action": "approve_upload", "target_scope": "upload", "target_id": 77}),
        ("reject 88", {"action": "reject_upload", "target_scope": "upload", "target_id": 88}),
        ("CONFIRM DELETE ALL", {"action": "confirm_delete", "target_scope": "all", "target_id": None}),
        ("confirm delete receipt 12", {"action": "confirm_delete", "target_scope": "receipt", "target_id": 12}),
        ("CONFIRM DELETE UPLOAD 13", {"action": "confirm_delete", "target_scope": "upload", "target_id": 13}),
        ("CONFIRM DELETE GENERATED 14", {"action": "confirm_delete", "target_scope": "generated_invoice", "target_id": 14}),
    ],
)
def test_parse_hitl_command_matches_exact_commands(text, expected):
    parsed = hitl_service.parse_hitl_command(text)

    assert parsed is not None
    assert {key: parsed[key] for key in expected} == expected
    assert parsed["confidence"] == 1.0


def test_parse_hitl_command_rejects_ambiguous_text():
    assert hitl_service.parse_hitl_command("approve the latest one") is None
    assert hitl_service.parse_hitl_command("CONFIRM DELETE RECEIPT") is None


@pytest.mark.asyncio
async def test_exact_approve_command_skips_llm_classifier(monkeypatch):
    captured = {}

    async def fail_classify(*_args, **_kwargs):
        raise AssertionError("exact APPROVE commands must not call the LLM classifier")

    async def fake_approve(user_id, media_id, conversation_history=None):
        captured["user_id"] = user_id
        captured["media_id"] = media_id
        captured["conversation_history"] = conversation_history
        return {
            "content": "Document Saved",
            "metadata": {"hitl_status": "confirmed", "media_id": str(media_id)},
        }

    monkeypatch.setattr(hitl_service, "classify_hitl_intent", fail_classify)
    monkeypatch.setattr(hitl_service, "approve_pending_extraction", fake_approve)

    result = await hitl_service.handle_human_confirmation_message(
        " approve 77 ",
        "1",
        conversation_history=[{"role": "user", "content": "previous"}],
    )

    assert result["metadata"]["hitl_status"] == "confirmed"
    assert captured == {
        "user_id": "1",
        "media_id": 77,
        "conversation_history": [{"role": "user", "content": "previous"}],
    }


@pytest.mark.asyncio
async def test_exact_confirm_delete_command_skips_llm_classifier(monkeypatch):
    captured = {}

    async def fail_classify(*_args, **_kwargs):
        raise AssertionError("exact delete confirmations must not call the LLM classifier")

    def fake_delete_user_history(user_id, payload):
        captured["user_id"] = user_id
        captured["payload"] = payload
        return {
            "status": "success",
            "deleted": {
                "documents": 0,
                "media": 0,
                "generated_invoices": 1,
                "storage_files": 1,
            },
        }

    monkeypatch.setattr(hitl_service, "classify_hitl_intent", fail_classify)
    monkeypatch.setattr(hitl_service, "delete_user_history", fake_delete_user_history)

    result = await hitl_service.handle_human_confirmation_message(
        "CONFIRM DELETE GENERATED 14",
        "7",
    )

    assert "Deletion Confirmed" in result["content"]
    assert captured == {
        "user_id": 7,
        "payload": {
            "scope": "generated_invoice",
            "id": 14,
            "confirmed": True,
        },
    }


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
    assert "Deletion Needs WhatsApp Confirmation" in result["content"]
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
    assert "Deletion Needs WhatsApp Confirmation" in result["content"]
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
    assert "Deletion Confirmed" in result["content"]


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
            "content": "✅ *Document Saved*\n\n*Status:* Saved to analytics",
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
async def test_approve_pending_extraction_uses_metadata_payload_when_file_is_not_stored(monkeypatch):
    captured = {}

    class FakeStorage:
        def __init__(self, bucket_name=None):
            self.bucket_name = bucket_name

        def download_file(self, file_key):
            raise AssertionError("metadata-only approval must not download a file")

    class FakeStorageAgent:
        async def process(self, agent_input, context):
            captured["payload"] = agent_input.content
            captured["metadata"] = agent_input.metadata
            captured["user_id"] = context.user_id

            class Output:
                status = "success"
                error = None
                content = {
                    "status": "success",
                    "invoice_id": "101",
                    "item_ids": ["1", "2"],
                    "media_id": "77",
                }

            return Output()

    monkeypatch.setattr(hitl_service, "SupabaseStorageHandler", FakeStorage)
    monkeypatch.setattr("agents.database_storage_agent.DatabaseStorageAgent", FakeStorageAgent)
    monkeypatch.setattr(
        hitl_service,
        "_load_user_media",
        lambda user_id, media_id: {
            "status": "success",
            "media_id": media_id,
            "invoice_id": None,
            "filename": "ledger.jpg",
            "original_filename": "ledger.jpg",
            "file_path": "pending://1/checksum",
            "content_type": "image/jpeg",
            "content_hash": "checksum",
            "file_storage": {
                "provider": "metadata",
                "file_key": "pending://1/checksum",
                "content_type": "image/jpeg",
                "media_id": "77",
                "storage_class": "pending_extraction",
                "access_scope": "metadata_only",
            },
            "metadata": {
                "pending_extraction_result": {
                    "data": {
                        "vendor": {"name": "Handwritten ledger"},
                        "financial": {"total": 100, "currency": "INR"},
                        "items": [
                            {"description": "Printing", "total_price": 60},
                            {"description": "Seeds", "total_price": 40},
                        ],
                    },
                    "metadata": {
                        "file_storage": {
                            "provider": "metadata",
                            "file_key": "pending://1/checksum",
                            "storage_class": "pending_extraction",
                        }
                    },
                }
            },
        },
    )

    result = await hitl_service.approve_pending_extraction("1", 77)

    assert result["metadata"]["hitl_status"] == "confirmed"
    assert result["metadata"]["stored_from_pending_extraction"] is True
    assert result["metadata"]["invoice_id"] == "101"
    assert "Document Saved" in result["content"]
    assert "*Upload:* #77" in result["content"]
    assert "*Status:* Analytics updated." in result["content"]
    assert '"hitl_confirmed": true' in captured["payload"]
    assert captured["metadata"]["hitl_confirmed"] is True
    assert captured["user_id"] == "1"


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
    assert "WhatsApp Approval Required" in result["message"]
