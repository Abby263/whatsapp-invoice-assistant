"""Tests for WhatsApp media webhook handling."""

import hashlib
import io

import pytest
from PIL import Image

from workflows import api
from workflows import file_processing_workflow
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


def _image_bytes(image_format: str = "PNG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), color=(255, 255, 255)).save(buffer, format=image_format)
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_process_whatsapp_media_sends_ack_before_user_lookup(monkeypatch):
    _FakeAsyncClient.payloads = {
        "https://api.twilio.com/media/receipt": b"receipt-image",
    }
    events = []

    def fake_send_processing_ack(**kwargs):
        events.append("ack")
        return True

    def fake_extract_user_id_from_sender(sender):
        events.append("user_lookup")
        return "1"

    async def fake_load_conversation_history(user_id):
        events.append("history")
        return []

    async def fake_process_file_message(*args, **kwargs):
        events.append("process_file")
        return {
            "status": "success",
            "message": "saved",
            "metadata": {"stored_in_database": True, "invoice_id": "1"},
        }

    monkeypatch.setattr(api.httpx, "AsyncClient", _FakeAsyncClient, raising=False)
    monkeypatch.setattr(api, "send_processing_ack", fake_send_processing_ack)
    monkeypatch.setattr(api, "extract_user_id_from_sender", fake_extract_user_id_from_sender)
    monkeypatch.setattr(api, "load_conversation_history", fake_load_conversation_history)
    monkeypatch.setattr(api, "process_file_message", fake_process_file_message)
    monkeypatch.setenv("TWILIO_MEDIA_FINAL_REPLY_ENABLED", "false")

    result = await api.process_whatsapp_message(
        {
            "From": "whatsapp:+15551234567",
            "To": "whatsapp:+16473628073",
            "NumMedia": "1",
            "MessageSid": "SM123",
            "MediaUrl0": "https://api.twilio.com/media/receipt",
            "MediaContentType0": "image/jpeg",
        }
    )

    assert result["status"] == "success"
    assert events[:3] == ["ack", "user_lookup", "history"]
    assert events.index("ack") < events.index("process_file")


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
    assert "*Batch Processing Result*" in result["message"]
    assert "*Attachments received:* 3" in result["message"]
    assert "*Saved:* 2" in result["message"]
    assert "*Duplicate*" in result["message"]
    assert "forwarded more images" not in result["message"]
    assert len(processed) == 2
    assert processed[0]["file_metadata"]["twilio_media_index"] == 0
    assert processed[1]["file_metadata"]["twilio_media_index"] == 2


@pytest.mark.asyncio
async def test_process_whatsapp_message_sniffs_extensionless_twilio_images(monkeypatch):
    _FakeAsyncClient.payloads = {
        "https://api.twilio.com/2010-04-01/Accounts/AC/Messages/SM123/Media/ME123": _image_bytes("PNG"),
    }

    processed = []

    async def fake_process_file_message(file_path, file_name, mime_type, *args, **kwargs):
        processed.append({
            "file_path": file_path,
            "file_name": file_name,
            "mime_type": mime_type,
        })
        return {
            "status": "success",
            "message": "saved",
            "metadata": {"stored_in_database": True, "invoice_id": "1"},
        }

    async def fake_load_conversation_history(user_id):
        return []

    monkeypatch.setattr(api.httpx, "AsyncClient", _FakeAsyncClient, raising=False)
    monkeypatch.setattr(api, "extract_user_id_from_sender", lambda sender: "1")
    monkeypatch.setattr(api, "load_conversation_history", fake_load_conversation_history)
    monkeypatch.setattr(api, "process_file_message", fake_process_file_message)

    result = await api.process_whatsapp_message({
        "From": "whatsapp:+15551234567",
        "NumMedia": "1",
        "MessageSid": "SM123",
        "MediaUrl0": "https://api.twilio.com/2010-04-01/Accounts/AC/Messages/SM123/Media/ME123",
    })

    assert result["status"] == "success"
    assert len(processed) == 1
    assert processed[0]["mime_type"] == "image/png"
    assert processed[0]["file_name"].endswith(".png")
    assert processed[0]["file_path"].endswith(".png")


@pytest.mark.asyncio
async def test_process_whatsapp_media_sends_final_reply_out_of_band(monkeypatch):
    _FakeAsyncClient.payloads = {
        "https://api.twilio.com/media/receipt": b"receipt-image",
    }
    outbound_messages = []

    async def fake_process_file_message(*args, **kwargs):
        return {
            "status": "success",
            "message": "Saved receipt from Acme for INR 100.",
            "metadata": {"stored_in_database": True, "invoice_id": "1"},
        }

    async def fake_load_conversation_history(user_id):
        return []

    def fake_send_whatsapp_message(**kwargs):
        outbound_messages.append(kwargs)
        return True

    monkeypatch.setattr(api.httpx, "AsyncClient", _FakeAsyncClient, raising=False)
    monkeypatch.setattr(api, "extract_user_id_from_sender", lambda sender: "1")
    monkeypatch.setattr(api, "load_conversation_history", fake_load_conversation_history)
    monkeypatch.setattr(api, "process_file_message", fake_process_file_message)
    monkeypatch.setattr(api, "send_processing_ack", lambda **kwargs: True)
    monkeypatch.setattr(api, "send_whatsapp_message", fake_send_whatsapp_message)
    monkeypatch.setenv("TWILIO_MEDIA_FINAL_REPLY_ENABLED", "true")

    result = await api.process_whatsapp_message({
        "From": "whatsapp:+15551234567",
        "To": "whatsapp:+16473628073",
        "NumMedia": "1",
        "MessageSid": "SM123",
        "MediaUrl0": "https://api.twilio.com/media/receipt",
        "MediaContentType0": "image/jpeg",
    })

    assert result["suppress_twiml_response"] is True
    assert result["metadata"]["twilio_final_reply_sent"] is True
    assert outbound_messages == [{
        "to_number": "whatsapp:+15551234567",
        "from_number": "whatsapp:+16473628073",
        "body": "Saved receipt from Acme for INR 100.",
    }]


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


@pytest.mark.asyncio
async def test_format_extraction_response_uses_business_document_summary():
    result = await file_processing_workflow.format_extraction_response(
        {
            "data": {
                "vendor": {"name": "Handwritten ledger"},
                "transaction": {"date": "2026-02-15"},
                "financial": {"total": 7825.0, "currency": "INR"},
                "additional_info": {"document_type": "handwritten_ledger"},
                "items": [
                    {
                        "description": "Printing Aminabad Adv.",
                        "transaction_date": "2026-02-15",
                        "total_price": 500.0,
                        "entry_type": "expense",
                    }
                ],
            },
            "metadata": {"invoice_id": 7},
        },
        "ledger.jpg",
    )

    content = result["content"]
    assert "*Document Saved*" in content
    assert "*File:* ledger.jpg" in content
    assert "*Type:* Handwritten Ledger" in content
    assert "*Date:* 2026-02-15" in content
    assert "*Total:* 7,825.00 INR" in content
    assert "*Entries:* 1 extracted" in content
    assert "document_type:" not in content
    assert "vendor.name:" not in content
    assert "financial.total:" not in content


@pytest.mark.asyncio
async def test_format_extraction_response_requests_whatsapp_approval():
    result = await file_processing_workflow.format_extraction_response(
        {
            "data": {
                "vendor": {"name": "Handwritten ledger"},
                "transaction": {"date": "2026-02-15"},
                "financial": {"total": 7825.0, "currency": "INR"},
                "additional_info": {"document_type": "handwritten_ledger"},
                "items": [{"description": "Printing", "total_price": 500.0}],
            },
            "metadata": {
                "hitl_status": "awaiting_confirmation",
                "hitl_approval_command": "APPROVE 99",
                "hitl_rejection_command": "REJECT 99",
                "file_storage": {"file_key": "users/1/invoices/aa/checksum"},
            },
        },
        "ledger.jpg",
    )

    content = result["content"]
    assert "*Document Review*" in content
    assert "*Status:* Pending WhatsApp approval" in content
    assert "Analytics have not been updated yet." in content
    assert "Reply *APPROVE 99* to save this document." in content
    assert "Reply *REJECT 99* to discard it." in content
    assert "Saved history" not in content


@pytest.mark.asyncio
async def test_format_extraction_response_does_not_claim_metadata_only_storage_is_private():
    result = await file_processing_workflow.format_extraction_response(
        {
            "data": {
                "vendor": {"name": "Handwritten ledger"},
                "financial": {"total": 100.0, "currency": "INR"},
                "additional_info": {"document_type": "handwritten_ledger"},
                "items": [{"description": "Printing", "total_price": 100.0}],
            },
            "metadata": {
                "hitl_status": "awaiting_confirmation",
                "hitl_approval_command": "APPROVE 321",
                "hitl_rejection_command": "REJECT 321",
                "file_storage": {
                    "provider": "metadata",
                    "file_key": "pending://1/checksum",
                    "storage_class": "pending_extraction",
                    "access_scope": "metadata_only",
                },
            },
        },
        "ledger.jpg",
    )

    content = result["content"]
    assert "APPROVE 321" in content
    assert "storage:" not in content


@pytest.mark.asyncio
async def test_format_extraction_response_does_not_call_pending_entries_saved():
    result = await file_processing_workflow.format_extraction_response(
        {
            "data": {
                "vendor": {"name": "Handwritten ledger"},
                "transaction": {"date": "2026-02-15"},
                "financial": {"total": 7825.0, "currency": "INR"},
                "additional_info": {"document_type": "handwritten_ledger"},
                "items": [
                    {"description": "Printing", "total_price": 500.0},
                    {"description": "Paper", "total_price": 300.0},
                    {"description": "Ink", "total_price": 200.0},
                    {"description": "Courier", "total_price": 100.0},
                    {"description": "Fuel", "total_price": 50.0},
                ],
            },
            "metadata": {
                "hitl_status": "awaiting_confirmation",
                "hitl_approval_command": "APPROVE 99",
                "hitl_rejection_command": "REJECT 99",
            },
        },
        "ledger.jpg",
    )

    content = result["content"]
    assert "+ 1 more entries extracted" in content
    assert "+ 1 more entries saved" not in content


def test_mark_media_awaiting_approval_backfills_late_media_id(monkeypatch):
    calls = []

    def fake_record_media_upload(**kwargs):
        calls.append(kwargs)
        return {"media_id": "123", "status": kwargs["status"]}

    monkeypatch.setattr(file_processing_workflow, "record_media_upload", fake_record_media_upload)

    file_metadata = {
        "file_storage": {
            "file_key": "users/1/invoices/aa/checksum",
            "content_type": "image/jpeg",
        }
    }
    pending_metadata = file_processing_workflow._mark_media_awaiting_approval(
        user_id="1",
        file_metadata=file_metadata,
        extraction_result={
            "data": {
                "vendor": {"name": "Handwritten ledger"},
                "financial": {"total": 100, "currency": "INR"},
                "items": [{"description": "Printing", "total_price": 100}],
            },
            "metadata": {},
        },
    )

    assert pending_metadata["media_id"] == "123"
    assert pending_metadata["hitl_approval_command"] == "APPROVE 123"
    assert pending_metadata["hitl_rejection_command"] == "REJECT 123"
    assert file_metadata["file_storage"]["media_id"] == "123"
    assert calls[-1]["processing_metadata"]["hitl_approval_command"] == "APPROVE 123"


def test_mark_media_awaiting_approval_creates_metadata_only_pending_record(monkeypatch):
    calls = []

    def fake_record_media_upload(**kwargs):
        calls.append(kwargs)
        return {"media_id": "321", "status": kwargs["status"]}

    monkeypatch.setattr(file_processing_workflow, "record_media_upload", fake_record_media_upload)

    pending_metadata = file_processing_workflow._mark_media_awaiting_approval(
        user_id="1",
        file_metadata={
            "checksum_sha256": "checksum",
            "original_filename": "ledger.jpg",
            "storage_error": "storage unavailable",
        },
        extraction_result={
            "data": {
                "vendor": {"name": "Handwritten ledger"},
                "financial": {"total": 100, "currency": "INR"},
                "items": [{"description": "Printing", "total_price": 100}],
            },
            "metadata": {"storage_error": "storage unavailable"},
        },
    )

    first_call = calls[0]
    assert first_call["file_storage"]["file_key"].startswith("pending://1/")
    assert first_call["file_storage"]["storage_class"] == "pending_extraction"
    assert first_call["processing_metadata"]["pending_extraction_result"]["data"]["items"][0]["description"] == "Printing"
    assert pending_metadata["hitl_approval_command"] == "APPROVE 321"
    assert pending_metadata["hitl_rejection_command"] == "REJECT 321"


def test_mark_media_awaiting_approval_falls_back_when_private_registry_fails(monkeypatch):
    calls = []

    def fake_record_media_upload(**kwargs):
        calls.append(kwargs)
        if kwargs["file_storage"].get("provider") == "metadata":
            return {"media_id": "654", "status": kwargs["status"]}
        return None

    monkeypatch.setattr(file_processing_workflow, "record_media_upload", fake_record_media_upload)

    file_metadata = {
        "checksum_sha256": "checksum",
        "original_filename": "ledger.jpg",
        "file_storage": {
            "provider": "supabase",
            "file_key": "users/1/invoices/aa/checksum",
            "content_type": "image/jpeg",
            "checksum_sha256": "checksum",
            "original_filename": "ledger.jpg",
        },
    }

    pending_metadata = file_processing_workflow._mark_media_awaiting_approval(
        user_id="1",
        file_metadata=file_metadata,
        extraction_result={
            "data": {
                "vendor": {"name": "Handwritten ledger"},
                "financial": {"total": 100, "currency": "INR"},
                "items": [{"description": "Printing", "total_price": 100}],
            },
            "metadata": {
                "file_storage": file_metadata["file_storage"],
            },
        },
    )

    assert calls[0]["file_storage"]["provider"] == "supabase"
    assert any(call["file_storage"].get("provider") == "metadata" for call in calls)
    assert pending_metadata["hitl_approval_command"] == "APPROVE 654"
    assert file_metadata["file_storage"]["file_key"].startswith("pending://1/")


@pytest.mark.asyncio
async def test_process_file_message_stores_original_before_validation(tmp_path, monkeypatch):
    file_path = tmp_path / "receipt.jpg"
    file_path.write_bytes(b"receipt-bytes")
    calls = {"uploads": 0, "media": 0}

    def fake_store_user_upload(**kwargs):
        calls["uploads"] += 1
        return {
            "provider": "supabase",
            "file_key": "users/1/invoices/aa/checksum",
            "path": "users/1/invoices/aa/checksum",
            "url": "https://example.com/signed",
            "content_type": "image/jpeg",
            "file_size": 13,
            "checksum_sha256": kwargs["metadata"]["checksum_sha256"],
            "original_filename": kwargs["file_name"],
            "user_scope_prefix": "users/1/invoices",
            "access_scope": "user",
        }

    def fake_record_media_upload(**kwargs):
        calls["media"] += 1
        return {"media_id": "99", "status": kwargs["status"]}

    async def fake_validate_file(*args, **kwargs):
        return {"is_valid": False, "is_invoice": False, "reason": "not a financial document"}

    monkeypatch.setattr(file_processing_workflow, "store_user_upload", fake_store_user_upload)
    monkeypatch.setattr(file_processing_workflow, "record_media_upload", fake_record_media_upload)
    monkeypatch.setattr(file_processing_workflow, "validate_file", fake_validate_file)
    monkeypatch.setattr(file_processing_workflow, "_find_existing_media_by_checksum", lambda *args, **kwargs: None)

    result = await file_processing_workflow.process_file_message(
        str(file_path),
        "image/jpeg",
        "receipt.jpg",
        "1",
    )

    assert calls == {"uploads": 1, "media": 2}
    assert "Document Not Processed" in result["content"]
    assert "*Reason:* not a financial document" in result["content"]


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
    assert result["file_key"].startswith("users/1/invoices/")
    assert checksum[:16] in result["file_key"]
    assert result["access_scope"] == "user"
    assert result["user_scope_prefix"] == "users/1/invoices"


def test_supabase_upload_creates_missing_private_bucket_and_retries(monkeypatch):
    class _FakeSyncResponse:
        def __init__(self, status_code=200, text="", payload=None):
            self.status_code = status_code
            self.text = text
            self._payload = payload or {}

        def json(self):
            return self._payload

    class _FakeSyncClient:
        requests = []
        object_attempts = 0

        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, **kwargs):
            self.__class__.requests.append((url, kwargs))
            if "/storage/v1/object/sign/" in url:
                return _FakeSyncResponse(200, payload={"signedURL": "/signed/receipt.jpg"})
            if url.endswith("/storage/v1/bucket"):
                return _FakeSyncResponse(200)

            self.__class__.object_attempts += 1
            if self.__class__.object_attempts == 1:
                return _FakeSyncResponse(
                    400,
                    text='{"statusCode":"404","error":"Bucket not found","message":"Bucket not found"}',
                )
            return _FakeSyncResponse(200)

    monkeypatch.setattr("storage.supabase_storage_handler.httpx.Client", _FakeSyncClient)

    handler = SupabaseStorageHandler(
        supabase_url="https://example.supabase.co",
        api_key="service-role-key",
        bucket_name="receipts",
    )

    result = handler.upload_file(
        file_content=b"receipt-bytes",
        file_name="receipt.jpg",
        user_id=1,
        content_type="image/jpeg",
    )

    assert result["bucket"] == "receipts"
    assert result["url"] == "https://example.supabase.co/signed/receipt.jpg"
    assert _FakeSyncClient.object_attempts == 2
    bucket_request = next(request for request in _FakeSyncClient.requests if request[0].endswith("/storage/v1/bucket"))
    assert bucket_request[1]["json"] == {"id": "receipts", "name": "receipts", "public": False}


def test_supabase_user_path_sanitizes_segments():
    handler = SupabaseStorageHandler(
        supabase_url="https://example.supabase.co",
        api_key="service-role-key",
        bucket_name="receipts",
    )

    assert handler.generate_user_path("../user/1", "invoice files") == "users/user-1/invoice-files"


def test_supabase_download_private_object_uses_authenticated_url(monkeypatch):
    class _FakeSyncResponse:
        status_code = 200
        text = ""
        content = b"file-bytes"

    class _FakeSyncClient:
        requests = []

        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, **kwargs):
            self.__class__.requests.append((url, kwargs))
            return _FakeSyncResponse()

    monkeypatch.setattr("storage.supabase_storage_handler.httpx.Client", _FakeSyncClient)

    handler = SupabaseStorageHandler(
        supabase_url="https://example.supabase.co",
        api_key="service-role-key",
        bucket_name="receipts",
    )

    content = handler.download_file("users/1/invoices/a")

    assert content == b"file-bytes"
    assert _FakeSyncClient.requests[0][0] == (
        "https://example.supabase.co/storage/v1/object/authenticated/receipts/users/1/invoices/a"
    )
    assert _FakeSyncClient.requests[0][1]["headers"]["Authorization"] == "Bearer service-role-key"


def test_supabase_delete_files_batches_and_deduplicates(monkeypatch):
    class _FakeSyncResponse:
        status_code = 200
        text = ""

    class _FakeSyncClient:
        requests = []

        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def delete(self, url, **kwargs):
            self.__class__.requests.append((url, kwargs))
            return _FakeSyncResponse()

    monkeypatch.setattr("storage.supabase_storage_handler.httpx.Client", _FakeSyncClient)

    handler = SupabaseStorageHandler(
        supabase_url="https://example.supabase.co",
        api_key="service-role-key",
        bucket_name="receipts",
    )

    result = handler.delete_files([
        "/users/1/invoices/a",
        "users/1/invoices/a",
        "https://example.com/signed",
        "users/1/invoices/b",
    ])

    assert result == {
        "deleted": ["users/1/invoices/a", "users/1/invoices/b"],
        "failed": [],
    }
    assert _FakeSyncClient.requests[0][0] == "https://example.supabase.co/storage/v1/object/receipts"
    assert _FakeSyncClient.requests[0][1]["json"] == {
        "prefixes": ["users/1/invoices/a", "users/1/invoices/b"],
    }
