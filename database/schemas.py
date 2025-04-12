"""
Database schema definitions using SQLAlchemy ORM.

This module defines the database tables and their relationships for the WhatsApp Invoice Assistant.
"""
from datetime import datetime
from typing import List, Optional
import uuid
import logging

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, 
    Numeric, String, Text, Enum, Float, UUID, JSON, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

# Try to import pgvector, fallback to a placeholder if not installed
try:
    from pgvector.sqlalchemy import Vector
    has_pgvector = True
    logging.info("pgvector extension available, using Vector type")
except ImportError:
    # Define a placeholder Vector type for compatibility
    logging.warning("pgvector not installed, using TEXT as fallback for VECTOR")
    from sqlalchemy.types import UserDefinedType, TEXT
    class Vector(UserDefinedType):
        def __init__(self, dim=None):
            self.dim = dim
        
        def get_col_spec(self, **kw):
            return "TEXT"
            
        def bind_processor(self, dialect):
            def process(value):
                if value is None:
                    return None
                return str(value)
            return process
            
        def result_processor(self, dialect, coltype):
            def process(value):
                if value is None:
                    return None
                return value
            return process
    has_pgvector = False

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

    id = Column(Integer, primary_key=True, autoincrement=True)
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
    invoice_embeddings = relationship("InvoiceEmbedding", back_populates="user")


class Invoice(Base):
    """Invoice model for storing invoice metadata."""
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    invoice_number = Column(String(50), nullable=True)
    invoice_date = Column(DateTime, nullable=True)
    vendor = Column(String(100), nullable=True)
    total_amount = Column(Float, nullable=True)
    tax_amount = Column(Float, nullable=True)
    currency = Column(String(3), nullable=True)
    file_url = Column(String(255), nullable=True)
    file_content_type = Column(String(50), nullable=True)
    raw_data = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="invoices")
    items = relationship("Item", back_populates="invoice")
    media_files = relationship("Media", back_populates="invoice")
    embeddings = relationship("InvoiceEmbedding", back_populates="invoice", cascade="all, delete-orphan")


class InvoiceEmbedding(Base):
    """Model for storing vector embeddings of invoices for semantic search."""
    __tablename__ = "invoice_embeddings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)  # For security filtering
    
    # Text that was used to generate the embedding
    content_text = Column(Text, nullable=True)
    
    # The embedding vector
    embedding = Column(Vector(1536), nullable=True)
    
    # Metadata about the embedding
    model_name = Column(String(100), nullable=True)
    embedding_type = Column(String(50), default="invoice_full")  # Type of embedding (full invoice, item, etc.)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    invoice = relationship("Invoice", back_populates="embeddings")
    user = relationship("User", back_populates="invoice_embeddings")
    
    # Add indices and constraints
    __table_args__ = (
        UniqueConstraint('invoice_id', 'embedding_type', name='uix_invoice_embedding_type'),
    )


class Item(Base):
    """Item model for invoice line items."""
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True, index=True)
    description = Column(String(255), nullable=False)
    quantity = Column(Float, nullable=True)
    unit_price = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)
    item_category = Column(String(50), nullable=True, index=True)
    item_code = Column(String(50), nullable=True)
    description_embedding = Column(Vector(1536), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    invoice = relationship("Invoice", back_populates="items")


class Conversation(Base):
    """Conversation model for tracking user interactions."""
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation")


class Message(Base):
    """Message model for conversation messages."""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True)
    content = Column(Text, nullable=False)
    role = Column(Enum(MessageRole), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    whatsapp_messages = relationship("WhatsAppMessage", back_populates="message")


class WhatsAppMessage(Base):
    """WhatsApp message model for tracking delivery status."""
    __tablename__ = "whatsapp_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
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

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=True)
    file_path = Column(String(255), nullable=False)
    file_url = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=True)
    content_type = Column(String(50), nullable=False)
    file_type = Column(Enum('image', 'pdf', 'excel', 'word', 'text', 'other', name='filetype'), nullable=True)
    status = Column(Enum('uploaded', 'processed', 'error', name='filestatus'), nullable=True)
    ocr_text = Column(Text, nullable=True)
    processing_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="media_files")
    invoice = relationship("Invoice", back_populates="media_files")


class Usage(Base):
    """Usage model for tracking API usage and costs."""
    __tablename__ = "usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    tokens_in = Column(Integer, default=0)
    tokens_out = Column(Integer, default=0)
    cost = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="usage") 