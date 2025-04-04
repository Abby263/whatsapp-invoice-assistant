"""Tests for CRUD operations."""

import pytest
import uuid
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.schemas import Base, User, MessageRole
from database import crud, models


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


@pytest.fixture
def test_user(test_db):
    """Create a test user and return the User object."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        whatsapp_number="+1234567890",
        name="Test User",
        email="test@example.com",
        is_active=True
    )
    test_db.add(user)
    test_db.commit()
    return user


def test_create_user(test_db):
    """Test creating a new user."""
    user_data = models.UserCreate(
        whatsapp_number="+9876543210",
        name="New User",
        email="new@example.com"
    )
    user = crud.user.create(test_db, obj_in=user_data)
    
    assert user is not None
    assert user.whatsapp_number == "+9876543210"
    assert user.name == "New User"
    assert user.email == "new@example.com"
    assert user.is_active is True
    assert user.created_at is not None
    assert user.updated_at is not None


def test_get_user(test_db, test_user):
    """Test getting a user by ID."""
    user = crud.user.get(test_db, id=test_user.id)
    
    assert user is not None
    assert user.id == test_user.id
    assert user.whatsapp_number == test_user.whatsapp_number
    assert user.name == test_user.name
    assert user.email == test_user.email


def test_get_user_by_whatsapp_number(test_db, test_user):
    """Test getting a user by WhatsApp number."""
    user = crud.user.get_by_whatsapp_number(test_db, whatsapp_number=test_user.whatsapp_number)
    
    assert user is not None
    assert user.id == test_user.id
    assert user.whatsapp_number == test_user.whatsapp_number


def test_update_user(test_db, test_user):
    """Test updating a user."""
    # Get a fresh copy of the user to avoid stale data
    fresh_user = test_db.query(User).filter(User.id == test_user.id).first()
    
    update_data = models.UserUpdate(
        name="Updated User",
        email="updated@example.com"
    )
    updated_user = crud.user.update(test_db, db_obj=fresh_user, obj_in=update_data)
    
    assert updated_user is not None
    assert updated_user.id == test_user.id
    assert updated_user.whatsapp_number == test_user.whatsapp_number
    assert updated_user.name == "Updated User"
    assert updated_user.email == "updated@example.com"


def test_delete_user(test_db, test_user):
    """Test deleting a user."""
    deleted_user = crud.user.remove(test_db, id=test_user.id)
    
    assert deleted_user is not None
    assert deleted_user.id == test_user.id
    
    # Verify the user no longer exists
    user = crud.user.get(test_db, id=test_user.id)
    assert user is None


@pytest.fixture
def test_invoice_data(test_user):
    """Create test invoice data."""
    return models.InvoiceCreate(
        user_id=test_user.id,
        invoice_number="INV-001",
        invoice_date=datetime.utcnow(),
        vendor="Test Vendor",
        total_amount=100.0,
        currency="USD",
        status="pending",
        notes="Test invoice"
    )


def test_create_invoice(test_db, test_user, test_invoice_data):
    """Test creating a new invoice."""
    invoice = crud.invoice.create(test_db, obj_in=test_invoice_data)
    
    assert invoice is not None
    assert invoice.user_id == test_user.id
    assert invoice.invoice_number == "INV-001"
    assert invoice.vendor == "Test Vendor"
    assert float(invoice.total_amount) == 100.0
    assert invoice.currency == "USD"
    assert invoice.status == "pending"


def test_get_invoice(test_db, test_user, test_invoice_data):
    """Test getting an invoice by ID."""
    # Create the invoice
    invoice = crud.invoice.create(test_db, obj_in=test_invoice_data)
    
    # Get the invoice
    retrieved_invoice = crud.invoice.get(test_db, id=invoice.id)
    
    assert retrieved_invoice is not None
    assert retrieved_invoice.id == invoice.id
    assert retrieved_invoice.user_id == test_user.id
    assert retrieved_invoice.invoice_number == "INV-001"
    assert retrieved_invoice.vendor == "Test Vendor"


def test_get_invoices_by_user(test_db, test_user, test_invoice_data):
    """Test getting invoices by user ID."""
    # Create two invoices for the user
    invoice1 = crud.invoice.create(test_db, obj_in=test_invoice_data)
    
    # Create a second invoice
    invoice_data2 = models.InvoiceCreate(
        user_id=test_user.id,
        invoice_number="INV-002",
        vendor="Another Vendor",
        total_amount=50.0,
        currency="USD"
    )
    invoice2 = crud.invoice.create(test_db, obj_in=invoice_data2)
    
    # Get invoices for the user
    invoices = crud.invoice.get_by_user(test_db, user_id=test_user.id)
    
    assert len(invoices) == 2
    invoice_numbers = [inv.invoice_number for inv in invoices]
    assert "INV-001" in invoice_numbers
    assert "INV-002" in invoice_numbers


@pytest.fixture
def test_conversation(test_db, test_user):
    """Create a test conversation and return the Conversation object."""
    # Create conversation data
    conversation_data = models.ConversationCreate(
        user_id=test_user.id
    )
    
    # Create the conversation
    return crud.conversation.create(test_db, obj_in=conversation_data)


def test_create_conversation(test_db, test_user):
    """Test creating a new conversation."""
    conversation_data = models.ConversationCreate(
        user_id=test_user.id
    )
    conversation = crud.conversation.create(test_db, obj_in=conversation_data)
    
    assert conversation is not None
    assert conversation.user_id == test_user.id
    assert conversation.is_active is True
    assert conversation.created_at is not None
    assert conversation.updated_at is not None


def test_get_active_conversation_by_user(test_db, test_user, test_conversation):
    """Test getting the active conversation for a user."""
    active_conversation = crud.conversation.get_active_by_user(test_db, user_id=test_user.id)
    
    assert active_conversation is not None
    assert active_conversation.id == test_conversation.id
    assert active_conversation.user_id == test_user.id
    assert active_conversation.is_active is True


def test_create_message(test_db, test_user, test_conversation):
    """Test creating a new message."""
    message_data = models.MessageCreate(
        user_id=test_user.id,
        conversation_id=test_conversation.id,
        content="Test message content",
        role="USER"  # Use uppercase for enum value
    )
    message = crud.message.create(test_db, obj_in=message_data)
    
    assert message is not None
    assert message.user_id == test_user.id
    assert message.conversation_id == test_conversation.id
    assert message.content == "Test message content"
    assert message.role == MessageRole.USER
    assert message.created_at is not None


def test_get_messages_by_conversation(test_db, test_user, test_conversation):
    """Test getting messages for a conversation."""
    # Create two messages
    message_data1 = models.MessageCreate(
        user_id=test_user.id,
        conversation_id=test_conversation.id,
        content="User message",
        role="USER"  # Use uppercase for enum value
    )
    message1 = crud.message.create(test_db, obj_in=message_data1)
    
    message_data2 = models.MessageCreate(
        user_id=test_user.id,
        conversation_id=test_conversation.id,
        content="Assistant response",
        role="ASSISTANT"  # Use uppercase for enum value
    )
    message2 = crud.message.create(test_db, obj_in=message_data2)
    
    # Get messages for the conversation
    messages = crud.message.get_by_conversation(test_db, conversation_id=test_conversation.id)
    
    assert len(messages) == 2
    content_list = [msg.content for msg in messages]
    assert "User message" in content_list
    assert "Assistant response" in content_list


@pytest.fixture
def test_media_data(test_user):
    """Create test media data."""
    return models.MediaCreate(
        user_id=test_user.id,
        filename="test_file.pdf",
        file_path="s3://bucket/test_file.pdf",
        mime_type="application/pdf",
        file_size=2048
    )


def test_create_media(test_db, test_user, test_media_data):
    """Test creating new media."""
    media = crud.media.create(test_db, obj_in=test_media_data)
    
    assert media is not None
    assert media.user_id == test_user.id
    assert media.filename == "test_file.pdf"
    assert media.file_path == "s3://bucket/test_file.pdf"
    assert media.mime_type == "application/pdf"
    assert media.file_size == 2048
    assert media.created_at is not None


def test_get_media_by_user(test_db, test_user, test_media_data):
    """Test getting media files for a user."""
    # Create a media file
    media = crud.media.create(test_db, obj_in=test_media_data)
    
    # Get media for the user
    media_files = crud.media.get_by_user(test_db, user_id=test_user.id)
    
    assert len(media_files) == 1
    assert media_files[0].id == media.id
    assert media_files[0].user_id == test_user.id
    assert media_files[0].filename == "test_file.pdf"


@pytest.fixture
def test_usage_data(test_user):
    """Create test usage data."""
    return models.UsageCreate(
        user_id=test_user.id,
        tokens_in=100,
        tokens_out=150,
        cost=0.0025
    )


def test_create_usage(test_db, test_user, test_usage_data):
    """Test creating new usage record."""
    usage = crud.usage.create(test_db, obj_in=test_usage_data)
    
    assert usage is not None
    assert usage.user_id == test_user.id
    assert usage.tokens_in == 100
    assert usage.tokens_out == 150
    assert usage.cost == 0.0025
    assert usage.created_at is not None


def test_get_usage_by_user(test_db, test_user, test_usage_data):
    """Test getting usage records for a user."""
    # Create a usage record
    usage = crud.usage.create(test_db, obj_in=test_usage_data)
    
    # Get usage for the user
    usage_records = crud.usage.get_by_user(test_db, user_id=test_user.id)
    
    assert len(usage_records) == 1
    assert usage_records[0].id == usage.id
    assert usage_records[0].user_id == test_user.id
    assert usage_records[0].tokens_in == 100
    assert usage_records[0].tokens_out == 150
    assert usage_records[0].cost == 0.0025 