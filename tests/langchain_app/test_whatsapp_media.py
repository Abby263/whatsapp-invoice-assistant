"""Tests for WhatsApp media webhook handling."""

import hashlib

import pytest

from langchain_app import api
from langchain_app import file_processing_workflow
from storage.supabase_storage_handler import SupabaseStorageHandler


class _FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200):
        self.content = content
        self.status_code = status_code


class _FakeAsyncClient:
    payloads = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, auth=None, follow_redirects=True):
        payload = self.payloads.get(url)
        if payload is None:
            return _FakeResponse(b"", status_code=404)
        return _FakeResponse(payload)


@pytest.mark.asyncio
async def test_process_whatsapp_message_handles_multiple_media_and_batch_duplicates(monkeypatch):
    _FakeAsyncClient.payloads = {
        "https://api.twilio.com/media/one": b"same-image",
        "https://api.twilio.com/media/two": b"same-image",
        "https://api.twilio.com/media/three": b"different-image",
    }

    processed = []

    async def fake_process_file_message(*args, **kwargs):
        processed.append(kwargs)
        return {
            "status": "success",
            "message": "saved",
            "metadata": {
                "stored_in_database": True,
                "invoice_id": str(len(processed)),
            },
        }

    async def fake_load_conversation_history(user_id):
        return []

    monkeypatch.setattr(api.httpx, "AsyncClient", _FakeAsyncClient, raising=False)
    monkeypatch.setattr(api, "extract_user_id_from_sender", lambda sender: "1")
    monkeypatch.setattr(api, "load_conversation_history", fake_load_conversation_history)
    monkeypatch.setattr(api, "process_file_message", fake_process_file_message)

    result = await api.process_whatsapp_message({
        "From": "whatsapp:+15551234567",
        "NumMedia": "3",
        "MessageSid": "SM123",
        "MediaUrl0": "https://api.twilio.com/media/one",
        "MediaContentType0": "image/jpeg",
        "MediaUrl1": "https://api.twilio.com/media/two",
        "MediaContentType1": "image/jpeg",
        "MediaUrl2": "https://api.twilio.com/media/three",
        "MediaContentType2": "image/png",
    })

    assert result["status"] == "success"
    assert result["metadata"]["media_count"] == 3
    assert result["metadata"]["saved_count"] == 2
    assert result["metadata"]["duplicate_count"] == 1
    assert len(processed) == 2
    assert processed[0]["file_metadata"]["twilio_media_index"] == 0
    assert processed[1]["file_metadata"]["twilio_media_index"] == 2


@pytest.mark.asyncio
async def test_process_file_message_short_circuits_previous_duplicate(tmp_path, monkeypatch):
    file_bytes = b"already-saved-image"
    checksum = hashlib.sha256(file_bytes).hexdigest()
    file_path = tmp_path / "receipt.jpg"
    file_path.write_bytes(file_bytes)

    duplicate_media = {
        "id": 42,
        "invoice_id": 7,
        "filename": "receipt.jpg",
        "file_path": "1/invoices/receipt.jpg",
        "file_url": "https://example.com/signed",
        "content_type": "image/jpeg",
        "file_size": len(file_bytes),
        "content_hash": checksum,
        "processing_metadata": {"checksum_sha256": checksum},
        "created_at": "2026-05-17T00:00:00",
    }

    def fake_find_existing_media(user_id, file_metadata):
        assert user_id == "1"
        assert file_metadata["checksum_sha256"] == checksum
        return duplicate_media

    async def fail_validate(*args, **kwargs):
        raise AssertionError("duplicate uploads should not be revalidated")

    monkeypatch.setattr(
        file_processing_workflow,
        "_find_existing_media_by_checksum",
        fake_find_existing_media,
    )
    monkeypatch.setattr(file_processing_workflow, "validate_file", fail_validate)

    result = await file_processing_workflow.process_file_message(
        str(file_path),
        "image/jpeg",
        "receipt.jpg",
        "1",
    )

    assert result["metadata"]["duplicate"] is True
    assert result["metadata"]["storage_status"] == "duplicate"
    assert result["metadata"]["invoice_id"] == "7"


def test_supabase_upload_is_idempotent_for_existing_content_addressed_object(monkeypatch):
    class _FakeSyncResponse:
        def __init__(self, status_code=200, text="", payload=None):
            self.status_code = status_code
            self.text = text
            self._payload = payload or {}

        def json(self):
            return self._payload

    class _FakeSyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, **kwargs):
            if "/storage/v1/object/sign/" in url:
                return _FakeSyncResponse(200, payload={"signedURL": "/signed/receipt.jpg"})
            return _FakeSyncResponse(409, text="The resource already exists")

    monkeypatch.setattr("storage.supabase_storage_handler.httpx.Client", _FakeSyncClient)

    handler = SupabaseStorageHandler(
        supabase_url="https://example.supabase.co",
        api_key="service-role-key",
        bucket_name="receipts",
    )
    file_bytes = b"same-receipt"
    checksum = hashlib.sha256(file_bytes).hexdigest()

    result = handler.upload_file(
        file_content=file_bytes,
        file_name="receipt.jpg",
        user_id=1,
        content_type="image/jpeg",
        metadata={"checksum_sha256": checksum},
    )

    assert result["existing_object"] is True
    assert result["checksum_sha256"] == checksum
    assert checksum[:16] in result["file_key"]
