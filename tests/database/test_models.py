"""Tests for database models and their relationships."""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.schemas import (
    Base, User, Invoice, Item, Conversation,
    Message, WhatsAppMessage, WebhookEvent, Media, Usage,
    GeneratedInvoice, GeneratedInvoiceItem,
    MessageRole, WhatsAppMessageStatus
)


@pytest.fixture
def test_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    # Create a test session
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    # Teardown
    transaction.rollback()
    connection.close()
    session.close()


def test_user_model(test_db):
    """Test the User model and its relationships."""
    # Create a user
    user = User(
        whatsapp_number="+1234567890",
        name="Test User",
        email="test@example.com"
    )
    test_db.add(user)
    test_db.commit()

    # Query the user
    saved_user = test_db.query(User).filter(User.whatsapp_number == "+1234567890").first()

    assert saved_user is not None
    assert saved_user.name == "Test User"
    assert saved_user.email == "test@example.com"
    assert saved_user.is_active is True
    assert saved_user.created_at is not None
    assert saved_user.updated_at is not None


def test_invoice_model_with_items(test_db):
    """Test the Invoice model with related items."""
    # Create a user
    user = User(
        whatsapp_number="+1234567890",
        name="Test User"
    )
    test_db.add(user)
    test_db.commit()

    # Create an invoice
    invoice = Invoice(
        user_id=user.id,
        invoice_number="INV-001",
        invoice_date=datetime.utcnow(),
        vendor="Test Vendor",
        total_amount=100.00,
        currency="USD",
        notes="Test invoice"
    )
    test_db.add(invoice)
    test_db.commit()

    # Create items for the invoice
    item1 = Item(
        invoice_id=invoice.id,
        description="Item 1",
        quantity=2,
        unit_price=25.00,
        total_price=50.00
    )
    item2 = Item(
        invoice_id=invoice.id,
        description="Item 2",
        quantity=1,
        unit_price=50.00,
        total_price=50.00
    )
    test_db.add_all([item1, item2])
    test_db.commit()

    # Query the invoice with items
    saved_invoice = test_db.query(Invoice).filter(Invoice.invoice_number == "INV-001").first()

    assert saved_invoice is not None
    assert saved_invoice.user_id == user.id
    assert saved_invoice.invoice_number == "INV-001"
    assert saved_invoice.vendor == "Test Vendor"
    assert saved_invoice.total_amount == 100.00
    assert saved_invoice.currency == "USD"

    # Check items
    assert len(saved_invoice.items) == 2
    # Items should be related to this invoice
    for item in saved_invoice.items:
        assert item.invoice_id == saved_invoice.id

    # Check total amount matches sum of items
    item_total = sum(float(item.total_price) for item in saved_invoice.items)
    assert float(saved_invoice.total_amount) == item_total


def test_generated_invoice_model_with_items(test_db):
    """Test outgoing generated invoice records and item relationships."""
    user = User(
        whatsapp_number="+1234567890",
        name="Test User"
    )
    test_db.add(user)
    test_db.commit()

    invoice = GeneratedInvoice(
        user_id=user.id,
        source="web",
        status="generated",
        invoice_number="OUT-001",
        invoice_date=datetime.utcnow(),
        client_name="Acme Operations",
        currency="USD",
        subtotal=350.00,
        tax_amount=0.00,
        total_amount=350.00,
        document_path="1/generated-invoices/out-001.docx",
    )
    test_db.add(invoice)
    test_db.commit()

    item = GeneratedInvoiceItem(
        generated_invoice_id=invoice.id,
        description="Consulting services",
        quantity=1,
        unit_price=350.00,
        total_price=350.00,
        sort_order=0,
    )
    test_db.add(item)
    test_db.commit()

    saved_invoice = (
        test_db.query(GeneratedInvoice)
        .filter(GeneratedInvoice.invoice_number == "OUT-001")
        .first()
    )

    assert saved_invoice is not None
    assert saved_invoice.user_id == user.id
    assert saved_invoice.user.whatsapp_number == "+1234567890"
    assert saved_invoice.client_name == "Acme Operations"
    assert len(saved_invoice.items) == 1
    assert saved_invoice.items[0].description == "Consulting services"


def test_conversation_with_messages(test_db):
    """Test the Conversation model with related messages."""
    # Create a user
    user = User(
        whatsapp_number="+1234567890",
        name="Test User"
    )
    test_db.add(user)
    test_db.commit()

    # Create a conversation
    conversation = Conversation(
        user_id=user.id,
        is_active=True
    )
    test_db.add(conversation)
    test_db.commit()

    # Create messages in the conversation
    message1 = Message(
        user_id=user.id,
        conversation_id=conversation.id,
        content="Hello, this is a test message",
        role=MessageRole.USER
    )
    message2 = Message(
        user_id=user.id,
        conversation_id=conversation.id,
        content="This is a response from the assistant",
        role=MessageRole.ASSISTANT
    )
    test_db.add_all([message1, message2])
    test_db.commit()

    # Query the conversation with messages
    saved_conversation = test_db.query(Conversation).filter(Conversation.id == conversation.id).first()

    assert saved_conversation is not None
    assert saved_conversation.user_id == user.id
    assert saved_conversation.is_active is True

    # Check messages
    assert len(saved_conversation.messages) == 2

    # Check message roles
    roles = [message.role for message in saved_conversation.messages]
    assert MessageRole.USER in roles
    assert MessageRole.ASSISTANT in roles


def test_whatsapp_message(test_db):
    """Test WhatsAppMessage model and its relationship to Message."""
    # Create a user
    user = User(
        whatsapp_number="+1234567890",
        name="Test User"
    )
    test_db.add(user)
    test_db.commit()

    # Create a conversation
    conversation = Conversation(
        user_id=user.id
    )
    test_db.add(conversation)
    test_db.commit()

    # Create a message
    message = Message(
        user_id=user.id,
        conversation_id=conversation.id,
        content="Test message",
        role=MessageRole.USER
    )
    test_db.add(message)
    test_db.commit()

    # Create a WhatsApp message
    whatsapp_message = WhatsAppMessage(
        message_id=message.id,
        whatsapp_message_id="wamid.test123",
        status=WhatsAppMessageStatus.SENT
    )
    test_db.add(whatsapp_message)
    test_db.commit()

    # Query the WhatsApp message
    saved_whatsapp_message = test_db.query(WhatsAppMessage).filter(
        WhatsAppMessage.whatsapp_message_id == "wamid.test123"
    ).first()

    assert saved_whatsapp_message is not None
    assert saved_whatsapp_message.message_id == message.id
    assert saved_whatsapp_message.status == WhatsAppMessageStatus.SENT

    # Verify relationship with message
    assert saved_whatsapp_message.message.content == "Test message"
    assert saved_whatsapp_message.message.role == MessageRole.USER


def test_webhook_event_model(test_db):
    """Test WebhookEvent model for webhook replay tracking."""
    event = WebhookEvent(
        event_id="SM123",
        source="twilio_whatsapp",
        status="processed",
        response_payload={"status": "success", "message": "ok"},
        response_hash="abc123",
    )
    test_db.add(event)
    test_db.commit()

    saved_event = (
        test_db.query(WebhookEvent)
        .filter(WebhookEvent.event_id == "SM123")
        .first()
    )

    assert saved_event is not None
    assert saved_event.status == "processed"
    assert saved_event.response_payload["message"] == "ok"


def test_media_model(test_db):
    """Test Media model and its relationships."""
    # Create a user
    user = User(
        whatsapp_number="+1234567890",
        name="Test User"
    )
    test_db.add(user)
    test_db.commit()

    # Create an invoice
    invoice = Invoice(
        user_id=user.id,
        invoice_number="INV-002"
    )
    test_db.add(invoice)
    test_db.commit()

    # Create a media file
    media = Media(
        user_id=user.id,
        invoice_id=invoice.id,
        filename="test_invoice.pdf",
        file_path="supabase://receipts/test_invoice.pdf",
        file_url="supabase://receipts/test_invoice.pdf",
        mime_type="application/pdf",
        file_size=1024
    )
    test_db.add(media)
    test_db.commit()

    # Query the media
    saved_media = test_db.query(Media).filter(Media.filename == "test_invoice.pdf").first()

    assert saved_media is not None
    assert saved_media.user_id == user.id
    assert saved_media.invoice_id == invoice.id
    assert saved_media.file_path == "supabase://receipts/test_invoice.pdf"
    assert saved_media.mime_type == "application/pdf"
    assert saved_media.file_size == 1024

    # Verify relationships
    assert saved_media.user.whatsapp_number == "+1234567890"
    assert saved_media.invoice.invoice_number == "INV-002"


def test_usage_model(test_db):
    """Test Usage model and its relationship to User."""
    # Create a user
    user = User(
        whatsapp_number="+1234567890",
        name="Test User"
    )
    test_db.add(user)
    test_db.commit()

    # Create a usage record
    usage = Usage(
        user_id=user.id,
        tokens_in=100,
        tokens_out=150,
        cost=0.0025
    )
    test_db.add(usage)
    test_db.commit()

    # Query the usage
    saved_usage = test_db.query(Usage).filter(Usage.user_id == user.id).first()

    assert saved_usage is not None
    assert saved_usage.tokens_in == 100
    assert saved_usage.tokens_out == 150
    assert saved_usage.cost == 0.0025

    # Verify relationship with user
    assert saved_usage.user.whatsapp_number == "+1234567890"
