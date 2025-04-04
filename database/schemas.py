"""
Database schema definitions using SQLAlchemy ORM.

This module defines the database tables and their relationships for the WhatsApp Invoice Assistant.
"""
from datetime import datetime
from typing import List, Optional
import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, 
    Numeric, String, Text, Enum, Float, UUID
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()


class MessageRole(enum.Enum):
    """Enumeration for message roles."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class WhatsAppMessageStatus(enum.Enum):
    """Enumeration for WhatsApp message status."""
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class User(Base):
    """User model representing application users."""
    __tablename__ = "users"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    whatsapp_number = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=True)
    email = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    invoices = relationship("Invoice", back_populates="user")
    conversations = relationship("Conversation", back_populates="user")
    usage = relationship("Usage", back_populates="user")
    media_files = relationship("Media", back_populates="user")


class Invoice(Base):
    """Invoice model for storing invoice metadata."""
    __tablename__ = "invoices"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID, ForeignKey("users.id"), nullable=False)
    invoice_number = Column(String(50), nullable=True)
    invoice_date = Column(DateTime, nullable=True)
    due_date = Column(DateTime, nullable=True)
    vendor = Column(String(100), nullable=True)
    total_amount = Column(Numeric(10, 2), nullable=True)
    currency = Column(String(3), nullable=True)
    status = Column(String(20), default="pending")  # pending, processed, error
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="invoices")
    items = relationship("Item", back_populates="invoice")
    media_files = relationship("Media", back_populates="invoice")


class Item(Base):
    """Item model for invoice line items."""
    __tablename__ = "items"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    invoice_id = Column(UUID, ForeignKey("invoices.id"), nullable=False)
    description = Column(Text, nullable=True)
    quantity = Column(Numeric(10, 2), nullable=True)
    unit_price = Column(Numeric(10, 2), nullable=True)
    total_price = Column(Numeric(10, 2), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    invoice = relationship("Invoice", back_populates="items")


class Conversation(Base):
    """Conversation model for tracking user interactions."""
    __tablename__ = "conversations"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation")


class Message(Base):
    """Message model for conversation messages."""
    __tablename__ = "messages"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID, ForeignKey("users.id"), nullable=False)
    conversation_id = Column(UUID, ForeignKey("conversations.id"), nullable=False)
    content = Column(Text, nullable=False)
    role = Column(Enum(MessageRole), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    whatsapp_messages = relationship("WhatsAppMessage", back_populates="message")


class WhatsAppMessage(Base):
    """WhatsApp message model for tracking delivery status."""
    __tablename__ = "whatsapp_messages"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    message_id = Column(UUID, ForeignKey("messages.id"), nullable=False)
    whatsapp_message_id = Column(String(100), unique=True, nullable=True)
    status = Column(Enum(WhatsAppMessageStatus), default=WhatsAppMessageStatus.SENT)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    message = relationship("Message", back_populates="whatsapp_messages")


class Media(Base):
    """Media model for storing files related to invoices."""
    __tablename__ = "media"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID, ForeignKey("users.id"), nullable=False)
    invoice_id = Column(UUID, ForeignKey("invoices.id"), nullable=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    mime_type = Column(String(100), nullable=True)
    file_size = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="media_files")
    invoice = relationship("Invoice", back_populates="media_files")


class Usage(Base):
    """Usage model for tracking API usage and costs."""
    __tablename__ = "usage"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID, ForeignKey("users.id"), nullable=False)
    tokens_in = Column(Integer, default=0)
    tokens_out = Column(Integer, default=0)
    cost = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="usage") 