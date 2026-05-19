"""Tests for user-scoped history listing and deletion."""

from datetime import datetime
import sys
import types

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import database.schemas as schema_module
from database.schemas import (
    Base,
    Conversation,
    GeneratedInvoice,
    GeneratedInvoiceItem,
    Invoice,
    Item,
    Media,
    Message,
    MessageRole,
    Usage,
    User,
    WhatsAppMessage,
)
from services import history_service


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    Base.metadata.drop_all(engine)


def _patch_connection(monkeypatch, session_factory):
    fake_connection = types.SimpleNamespace(
        ensure_application_schema=lambda: None,
        get_db_session=lambda: session_factory(),
    )
    monkeypatch.setitem(sys.modules, "database.schemas", schema_module)
    monkeypatch.setitem(sys.modules, "database.connection", fake_connection)


class _FakeStorage:
    deleted_paths = []
    failed = False

    def generate_url(self, path):
        return f"https://signed.example/{path}"

    def delete_files(self, paths):
        self.__class__.deleted_paths.extend(paths)
        if self.__class__.failed:
            return {"deleted": [], "failed": list(paths)}
        return {"deleted": list(paths), "failed": []}


def _seed_history(session_factory):
    session = session_factory()
    user = User(whatsapp_number="+15551234567", name="Primary")
    other_user = User(whatsapp_number="+15557654321", name="Other")
    session.add_all([user, other_user])
    session.commit()

    invoice = Invoice(
        user_id=user.id,
        invoice_date=datetime(2026, 5, 15),
        vendor="Ledger Page",
        total_amount=725.0,
        currency="INR",
    )
    other_invoice = Invoice(
        user_id=other_user.id,
        vendor="Other User",
        total_amount=10.0,
        currency="INR",
    )
    session.add_all([invoice, other_invoice])
    session.commit()

    session.add_all([
        Item(invoice_id=invoice.id, description="Printing", quantity=1, unit_price=500, total_price=500),
        Media(
            user_id=user.id,
            invoice_id=invoice.id,
            filename="ledger.jpg",
            original_filename="ledger.jpg",
            file_path="users/1/invoices/ledger",
            file_url="",
            content_type="image/jpeg",
            status="processed",
            processing_metadata={"file_storage": {"file_key": "users/1/invoices/ledger"}},
        ),
        Media(
            user_id=user.id,
            invoice_id=None,
            filename="unprocessed.jpg",
            original_filename="unprocessed.jpg",
            file_path="users/1/invoices/unprocessed",
            file_url="",
            content_type="image/jpeg",
            status="uploaded",
            processing_metadata={
                "hitl_status": "awaiting_confirmation",
                "pending_extraction_summary": {
                    "document_type": "handwritten_ledger",
                    "vendor_name": "Handwritten ledger",
                    "transaction_date": "2026-05-16",
                    "total_amount": 2297270.0,
                    "currency": "INR",
                    "item_count": 28,
                    "item_label": "entries",
                    "needs_review": True,
                    "sample_items": ["no date | Dm Delhi | 400000.0 INR"],
                },
            },
        ),
        Media(
            user_id=other_user.id,
            invoice_id=other_invoice.id,
            filename="other.jpg",
            file_path="users/2/invoices/other",
            file_url="",
            content_type="image/jpeg",
            status="processed",
        ),
    ])

    generated = GeneratedInvoice(
        user_id=user.id,
        source="web",
        invoice_number="OUT-001",
        client_name="Acme",
        currency="INR",
        total_amount=1000.0,
        document_path="users/1/generated/out-001.docx",
        pdf_path="users/1/generated/out-001.pdf",
    )
    session.add(generated)
    session.commit()
    session.add(GeneratedInvoiceItem(
        generated_invoice_id=generated.id,
        description="Consulting",
        quantity=1,
        unit_price=1000,
        total_price=1000,
    ))

    conversation = Conversation(user_id=user.id)
    session.add(conversation)
    session.commit()
    message = Message(
        user_id=user.id,
        conversation_id=conversation.id,
        content="Hi",
        role=MessageRole.USER,
    )
    session.add(message)
    session.commit()
    session.add_all([
        WhatsAppMessage(message_id=message.id, whatsapp_message_id="SM123"),
        Usage(user_id=user.id, tokens_in=10, tokens_out=20, cost=0.01),
    ])
    session.commit()

    ids = {"user_id": user.id, "other_user_id": other_user.id, "invoice_id": invoice.id}
    session.close()
    return ids


def test_list_user_history_returns_documents_and_generated_invoices(monkeypatch, session_factory):
    _patch_connection(monkeypatch, session_factory)
    monkeypatch.setattr(history_service, "SupabaseStorageHandler", _FakeStorage)
    ids = _seed_history(session_factory)

    result = history_service.list_user_history(ids["user_id"])

    assert result["status"] == "success"
    assert result["counts"]["documents"] == 2
    assert result["counts"]["generated_invoices"] == 1
    assert {record["kind"] for record in result["documents"]} == {"invoice", "media"}
    pending_upload = next(record for record in result["documents"] if record["kind"] == "media")
    assert pending_upload["hitl_status"] == "awaiting_confirmation"
    assert pending_upload["approval_command"] == "APPROVE 2"
    assert pending_upload["rejection_command"] == "REJECT 2"
    assert pending_upload["content_type"] == "image/jpeg"
    assert pending_upload["file_url"] == "https://signed.example/users/1/invoices/unprocessed"
    assert pending_upload["total_amount"] == 2297270.0
    assert pending_upload["currency"] == "INR"
    assert pending_upload["item_count"] == 28
    assert pending_upload["review_summary"]["needs_review"] is True
    invoice_record = next(record for record in result["documents"] if record["kind"] == "invoice")
    assert invoice_record["file_url"] == "https://signed.example/users/1/invoices/ledger"
    assert result["generated_invoices"][0]["invoice_number"] == "OUT-001"


def test_delete_history_requires_confirmation(monkeypatch, session_factory):
    _patch_connection(monkeypatch, session_factory)
    ids = _seed_history(session_factory)

    result = history_service.delete_user_history(ids["user_id"], {"scope": "all"})

    assert result["status"] == "needs_confirmation"
    session = session_factory()
    try:
        assert session.query(Invoice).filter(Invoice.user_id == ids["user_id"]).count() == 1
        assert session.query(Media).filter(Media.user_id == ids["user_id"]).count() == 2
    finally:
        session.close()


def test_delete_all_history_removes_user_rows_and_storage_files(monkeypatch, session_factory):
    _patch_connection(monkeypatch, session_factory)
    monkeypatch.setattr(history_service, "SupabaseStorageHandler", _FakeStorage)
    _FakeStorage.deleted_paths = []
    _FakeStorage.failed = False
    ids = _seed_history(session_factory)

    result = history_service.delete_user_history(ids["user_id"], {"scope": "all", "confirmed": True})

    assert result["status"] == "success"
    assert result["deleted"]["documents"] == 1
    assert result["deleted"]["media"] == 2
    assert result["deleted"]["generated_invoices"] == 1
    assert result["deleted"]["messages"] == 1
    assert result["deleted"]["usage"] == 1
    assert set(_FakeStorage.deleted_paths) == {
        "users/1/invoices/ledger",
        "users/1/invoices/unprocessed",
        "users/1/generated/out-001.docx",
        "users/1/generated/out-001.pdf",
    }

    session = session_factory()
    try:
        assert session.query(Invoice).filter(Invoice.user_id == ids["user_id"]).count() == 0
        assert session.query(Media).filter(Media.user_id == ids["user_id"]).count() == 0
        assert session.query(GeneratedInvoice).filter(GeneratedInvoice.user_id == ids["user_id"]).count() == 0
        assert session.query(Message).filter(Message.user_id == ids["user_id"]).count() == 0
        assert session.query(Usage).filter(Usage.user_id == ids["user_id"]).count() == 0
        assert session.query(Invoice).filter(Invoice.user_id == ids["other_user_id"]).count() == 1
        assert session.query(Media).filter(Media.user_id == ids["other_user_id"]).count() == 1
    finally:
        session.close()


def test_delete_history_rolls_back_if_storage_delete_fails(monkeypatch, session_factory):
    _patch_connection(monkeypatch, session_factory)
    monkeypatch.setattr(history_service, "SupabaseStorageHandler", _FakeStorage)
    _FakeStorage.deleted_paths = []
    _FakeStorage.failed = True
    ids = _seed_history(session_factory)

    result = history_service.delete_user_history(
        ids["user_id"],
        {"scope": "document", "kind": "invoice", "id": ids["invoice_id"], "confirmed": True},
    )

    assert result["status"] == "error"
    session = session_factory()
    try:
        assert session.query(Invoice).filter(Invoice.id == ids["invoice_id"]).count() == 1
        assert session.query(Media).filter(Media.user_id == ids["user_id"]).count() == 2
    finally:
        session.close()
