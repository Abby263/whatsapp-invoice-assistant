"""
Pydantic models for data validation and serialization.

This module defines the Pydantic models that correspond to SQLAlchemy schemas
and are used for request/response validation, serialization, and API documentation.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
import uuid

from pydantic import BaseModel, Field, validator, EmailStr


class UserBase(BaseModel):
    """Base user model with common attributes."""
    whatsapp_number: str = Field(..., min_length=10, max_length=20)
    name: Optional[str] = None
    email: Optional[str] = None

    class Config:
        from_attributes = True


class UserCreate(UserBase):
    """User creation model."""
    pass


class UserUpdate(BaseModel):
    """User update model with all fields optional."""
    whatsapp_number: Optional[str] = Field(None, min_length=10, max_length=20)
    name: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    """User response model with all fields including id and timestamps."""
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    is_active: bool


class ItemBase(BaseModel):
    """Base invoice item model."""
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    total_price: Optional[float] = None

    class Config:
        from_attributes = True


class ItemCreate(ItemBase):
    """Invoice item creation model."""
    invoice_id: uuid.UUID


class ItemUpdate(ItemBase):
    """Invoice item update model."""
    pass


class ItemResponse(ItemBase):
    """Invoice item response model."""
    id: uuid.UUID
    invoice_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class InvoiceBase(BaseModel):
    """Base invoice model."""
    invoice_number: Optional[str] = None
    invoice_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    vendor: Optional[str] = None
    total_amount: Optional[float] = None
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    status: Optional[str] = Field("pending", pattern="^(pending|processed|error)$")
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class InvoiceCreate(InvoiceBase):
    """Invoice creation model."""
    user_id: uuid.UUID
    items: Optional[List[ItemCreate]] = []


class InvoiceUpdate(InvoiceBase):
    """Invoice update model."""
    items: Optional[List[ItemCreate]] = None


class InvoiceResponse(InvoiceBase):
    """Invoice response model."""
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    items: List[ItemResponse] = []


class MediaBase(BaseModel):
    """Base media file model."""
    filename: str
    file_path: str
    mime_type: Optional[str] = None
    file_size: Optional[int] = None

    class Config:
        from_attributes = True


class MediaCreate(MediaBase):
    """Media file creation model."""
    user_id: uuid.UUID
    invoice_id: Optional[uuid.UUID] = None


class MediaUpdate(BaseModel):
    """Media file update model."""
    filename: Optional[str] = None
    file_path: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    invoice_id: Optional[uuid.UUID] = None


class MediaResponse(MediaBase):
    """Media file response model."""
    id: uuid.UUID
    user_id: uuid.UUID
    invoice_id: Optional[uuid.UUID] = None
    created_at: datetime


class MessageBase(BaseModel):
    """Base message model."""
    content: str
    # Use Literal to ensure valid enum values, only accept uppercase values for role
    role: Literal["USER", "ASSISTANT", "SYSTEM"] = Field(...)

    class Config:
        from_attributes = True
        use_enum_values = True

    @validator('role', pre=True)
    def validate_role(cls, v):
        """Validate and convert role to uppercase if needed."""
        if isinstance(v, str):
            return v.upper()
        return v


class MessageCreate(MessageBase):
    """Message creation model."""
    user_id: uuid.UUID
    conversation_id: uuid.UUID


class MessageResponse(MessageBase):
    """Message response model."""
    id: uuid.UUID
    user_id: uuid.UUID
    conversation_id: uuid.UUID
    created_at: datetime


class ConversationBase(BaseModel):
    """Base conversation model."""
    is_active: bool = True

    class Config:
        from_attributes = True


class ConversationCreate(ConversationBase):
    """Conversation creation model."""
    user_id: uuid.UUID


class ConversationUpdate(BaseModel):
    """Conversation update model."""
    is_active: Optional[bool] = None


class ConversationResponse(ConversationBase):
    """Conversation response model."""
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    messages: List[MessageResponse] = []


class WhatsAppMessageBase(BaseModel):
    """Base WhatsApp message model."""
    whatsapp_message_id: Optional[str] = None
    status: Literal["SENT", "DELIVERED", "READ", "FAILED"] = Field("SENT")
    error_message: Optional[str] = None

    class Config:
        from_attributes = True
        use_enum_values = True
        
    @validator('status', pre=True)
    def validate_status(cls, v):
        """Validate and convert status to uppercase if needed."""
        if isinstance(v, str):
            return v.upper()
        return v


class WhatsAppMessageCreate(WhatsAppMessageBase):
    """WhatsApp message creation model."""
    message_id: uuid.UUID


class WhatsAppMessageUpdate(BaseModel):
    """WhatsApp message update model."""
    whatsapp_message_id: Optional[str] = None
    status: Optional[Literal["SENT", "DELIVERED", "READ", "FAILED"]] = None
    error_message: Optional[str] = None


class WhatsAppMessageResponse(WhatsAppMessageBase):
    """WhatsApp message response model."""
    id: uuid.UUID
    message_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class UsageBase(BaseModel):
    """Base usage model."""
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0

    class Config:
        from_attributes = True


class UsageCreate(UsageBase):
    """Usage creation model."""
    user_id: uuid.UUID


class UsageResponse(UsageBase):
    """Usage response model."""
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime 