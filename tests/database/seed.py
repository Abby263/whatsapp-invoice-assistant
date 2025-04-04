"""
Database seeding utility for development and testing.

This module provides functions to seed the database with test data.
"""
import uuid
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from database.connection import engine, SessionLocal
from database.schemas import (
    Base, User, Invoice, Item, Conversation, 
    Message, WhatsAppMessage, Media, Usage,
    MessageRole, WhatsAppMessageStatus
)


def seed_users(db: Session) -> dict:
    """
    Seed users table with test data.
    
    Args:
        db: Database session
        
    Returns:
        dict: Dictionary of created users keyed by name
    """
    print("Seeding users...")
    users = {
        "john": User(
            id=uuid.uuid4(),
            whatsapp_number="+12025550001",
            name="John Doe",
            email="john.doe@example.com",
            is_active=True
        ),
        "jane": User(
            id=uuid.uuid4(),
            whatsapp_number="+12025550002",
            name="Jane Smith",
            email="jane.smith@example.com",
            is_active=True
        ),
        "bob": User(
            id=uuid.uuid4(),
            whatsapp_number="+12025550003",
            name="Bob Johnson",
            email="bob.johnson@example.com",
            is_active=False
        )
    }
    
    for user in users.values():
        db.add(user)
    
    db.commit()
    return users


def seed_invoices(db: Session, users: dict) -> dict:
    """
    Seed invoices table with test data.
    
    Args:
        db: Database session
        users: Dictionary of users
        
    Returns:
        dict: Dictionary of created invoices keyed by name
    """
    print("Seeding invoices...")
    now = datetime.utcnow()
    
    invoices = {
        "office_supplies": Invoice(
            id=uuid.uuid4(),
            user_id=users["john"].id,
            invoice_number="INV-001",
            invoice_date=now - timedelta(days=30),
            due_date=now - timedelta(days=15),
            vendor="Office Supplies Inc.",
            total_amount=125.50,
            currency="USD",
            status="processed",
            notes="Monthly office supplies"
        ),
        "software": Invoice(
            id=uuid.uuid4(),
            user_id=users["john"].id,
            invoice_number="INV-002",
            invoice_date=now - timedelta(days=15),
            due_date=now + timedelta(days=15),
            vendor="Software Solutions Ltd.",
            total_amount=499.99,
            currency="USD",
            status="pending",
            notes="Annual software subscription"
        ),
        "consulting": Invoice(
            id=uuid.uuid4(),
            user_id=users["jane"].id,
            invoice_number="INV-003",
            invoice_date=now - timedelta(days=5),
            due_date=now + timedelta(days=25),
            vendor="Consulting Experts LLC",
            total_amount=1500.00,
            currency="USD",
            status="pending",
            notes="Consulting services for Q2"
        )
    }
    
    for invoice in invoices.values():
        db.add(invoice)
    
    db.commit()
    return invoices


def seed_items(db: Session, invoices: dict) -> None:
    """
    Seed items table with test data.
    
    Args:
        db: Database session
        invoices: Dictionary of invoices
    """
    print("Seeding invoice items...")
    items = [
        # Items for office supplies invoice
        Item(
            id=uuid.uuid4(),
            invoice_id=invoices["office_supplies"].id,
            description="Paper Reams",
            quantity=5,
            unit_price=8.50,
            total_price=42.50
        ),
        Item(
            id=uuid.uuid4(),
            invoice_id=invoices["office_supplies"].id,
            description="Pens (Box)",
            quantity=2,
            unit_price=12.00,
            total_price=24.00
        ),
        Item(
            id=uuid.uuid4(),
            invoice_id=invoices["office_supplies"].id,
            description="Notebooks",
            quantity=10,
            unit_price=5.90,
            total_price=59.00
        ),
        
        # Items for software invoice
        Item(
            id=uuid.uuid4(),
            invoice_id=invoices["software"].id,
            description="Premium Software License",
            quantity=1,
            unit_price=499.99,
            total_price=499.99
        ),
        
        # Items for consulting invoice
        Item(
            id=uuid.uuid4(),
            invoice_id=invoices["consulting"].id,
            description="Strategy Consulting",
            quantity=10,
            unit_price=150.00,
            total_price=1500.00
        )
    ]
    
    for item in items:
        db.add(item)
    
    db.commit()


def seed_conversations(db: Session, users: dict) -> dict:
    """
    Seed conversations table with test data.
    
    Args:
        db: Database session
        users: Dictionary of users
        
    Returns:
        dict: Dictionary of created conversations keyed by name
    """
    print("Seeding conversations...")
    conversations = {
        "john_convo": Conversation(
            id=uuid.uuid4(),
            user_id=users["john"].id,
            is_active=True
        ),
        "jane_convo": Conversation(
            id=uuid.uuid4(),
            user_id=users["jane"].id,
            is_active=True
        )
    }
    
    for conversation in conversations.values():
        db.add(conversation)
    
    db.commit()
    return conversations


def seed_messages(db: Session, users: dict, conversations: dict) -> dict:
    """
    Seed messages table with test data.
    
    Args:
        db: Database session
        users: Dictionary of users
        conversations: Dictionary of conversations
        
    Returns:
        dict: Dictionary of created messages keyed by name
    """
    print("Seeding messages...")
    messages = {
        "john_msg1": Message(
            id=uuid.uuid4(),
            user_id=users["john"].id,
            conversation_id=conversations["john_convo"].id,
            content="Hello, I need help with my invoices",
            role=MessageRole.USER
        ),
        "john_response1": Message(
            id=uuid.uuid4(),
            user_id=users["john"].id,
            conversation_id=conversations["john_convo"].id,
            content="Hi John! I'd be happy to help with your invoices. What would you like to know?",
            role=MessageRole.ASSISTANT
        ),
        "john_msg2": Message(
            id=uuid.uuid4(),
            user_id=users["john"].id,
            conversation_id=conversations["john_convo"].id,
            content="Show me all my pending invoices",
            role=MessageRole.USER
        ),
        "john_response2": Message(
            id=uuid.uuid4(),
            user_id=users["john"].id,
            conversation_id=conversations["john_convo"].id,
            content="You have 1 pending invoice from Software Solutions Ltd. for $499.99 due in 15 days.",
            role=MessageRole.ASSISTANT
        ),
        "jane_msg1": Message(
            id=uuid.uuid4(),
            user_id=users["jane"].id,
            conversation_id=conversations["jane_convo"].id,
            content="Hi, can you help me understand my consulting invoice?",
            role=MessageRole.USER
        ),
        "jane_response1": Message(
            id=uuid.uuid4(),
            user_id=users["jane"].id,
            conversation_id=conversations["jane_convo"].id,
            content="Hello Jane! I'd be happy to help. You have a pending invoice from Consulting Experts LLC for $1,500.00 for Q2 consulting services.",
            role=MessageRole.ASSISTANT
        )
    }
    
    for message in messages.values():
        db.add(message)
    
    db.commit()
    return messages


def seed_whatsapp_messages(db: Session, messages: dict) -> None:
    """
    Seed WhatsApp messages table with test data.
    
    Args:
        db: Database session
        messages: Dictionary of messages
    """
    print("Seeding WhatsApp messages...")
    whatsapp_messages = [
        WhatsAppMessage(
            id=uuid.uuid4(),
            message_id=messages["john_msg1"].id,
            whatsapp_message_id="wamid.abcd1234",
            status=WhatsAppMessageStatus.READ
        ),
        WhatsAppMessage(
            id=uuid.uuid4(),
            message_id=messages["john_response1"].id,
            whatsapp_message_id="wamid.efgh5678",
            status=WhatsAppMessageStatus.DELIVERED
        ),
        WhatsAppMessage(
            id=uuid.uuid4(),
            message_id=messages["john_msg2"].id,
            whatsapp_message_id="wamid.ijkl9012",
            status=WhatsAppMessageStatus.READ
        ),
        WhatsAppMessage(
            id=uuid.uuid4(),
            message_id=messages["john_response2"].id,
            whatsapp_message_id="wamid.mnop3456",
            status=WhatsAppMessageStatus.SENT
        ),
        WhatsAppMessage(
            id=uuid.uuid4(),
            message_id=messages["jane_msg1"].id,
            whatsapp_message_id="wamid.qrst7890",
            status=WhatsAppMessageStatus.READ
        ),
        WhatsAppMessage(
            id=uuid.uuid4(),
            message_id=messages["jane_response1"].id,
            whatsapp_message_id="wamid.uvwx1234",
            status=WhatsAppMessageStatus.DELIVERED
        )
    ]
    
    for whatsapp_message in whatsapp_messages:
        db.add(whatsapp_message)
    
    db.commit()


def seed_media(db: Session, users: dict, invoices: dict) -> None:
    """
    Seed media table with test data.
    
    Args:
        db: Database session
        users: Dictionary of users
        invoices: Dictionary of invoices
    """
    print("Seeding media files...")
    media_files = [
        Media(
            id=uuid.uuid4(),
            user_id=users["john"].id,
            invoice_id=invoices["office_supplies"].id,
            filename="office_supplies.pdf",
            file_path="s3://whatsapp-invoice-assistant/john/office_supplies.pdf",
            mime_type="application/pdf",
            file_size=1024 * 250  # 250 KB
        ),
        Media(
            id=uuid.uuid4(),
            user_id=users["john"].id,
            invoice_id=invoices["software"].id,
            filename="software_invoice.pdf",
            file_path="s3://whatsapp-invoice-assistant/john/software_invoice.pdf",
            mime_type="application/pdf",
            file_size=1024 * 180  # 180 KB
        ),
        Media(
            id=uuid.uuid4(),
            user_id=users["jane"].id,
            invoice_id=invoices["consulting"].id,
            filename="consulting_invoice.pdf",
            file_path="s3://whatsapp-invoice-assistant/jane/consulting_invoice.pdf",
            mime_type="application/pdf",
            file_size=1024 * 320  # 320 KB
        )
    ]
    
    for media_file in media_files:
        db.add(media_file)
    
    db.commit()


def seed_usage(db: Session, users: dict) -> None:
    """
    Seed usage table with test data.
    
    Args:
        db: Database session
        users: Dictionary of users
    """
    print("Seeding usage records...")
    usage_records = [
        Usage(
            id=uuid.uuid4(),
            user_id=users["john"].id,
            tokens_in=150,
            tokens_out=350,
            cost=0.0075
        ),
        Usage(
            id=uuid.uuid4(),
            user_id=users["john"].id,
            tokens_in=200,
            tokens_out=450,
            cost=0.0095
        ),
        Usage(
            id=uuid.uuid4(),
            user_id=users["jane"].id,
            tokens_in=180,
            tokens_out=400,
            cost=0.0085
        )
    ]
    
    for usage_record in usage_records:
        db.add(usage_record)
    
    db.commit()


def seed_database(db: Session = None) -> None:
    """
    Seed the database with test data.
    
    Args:
        db: Database session (optional)
    """
    if db is None:
        # Create tables if they don't exist
        Base.metadata.create_all(engine)
        
        # Create a new session if one wasn't provided
        db = SessionLocal()
        should_close_session = True
    else:
        should_close_session = False
    
    try:
        users = seed_users(db)
        invoices = seed_invoices(db, users)
        seed_items(db, invoices)
        conversations = seed_conversations(db, users)
        messages = seed_messages(db, users, conversations)
        seed_whatsapp_messages(db, messages)
        seed_media(db, users, invoices)
        seed_usage(db, users)
        
        print("Database seeding completed successfully!")
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise
    finally:
        if should_close_session:
            db.close()


if __name__ == "__main__":
    seed_database() 