"""
CRUD operations for database models.

This module provides Create, Read, Update, Delete operations for all database models.
"""
from typing import List, Optional, Dict, Any, Union, Type, TypeVar, Generic
from uuid import UUID

from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import schemas
from database import models

# Generic type for SQLAlchemy model
ModelType = TypeVar("ModelType")
# Generic type for Pydantic model used for creating entries
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
# Generic type for Pydantic model used for updating entries
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """
    Base class for CRUD operations on a SQLAlchemy model.
    
    Provides generic Create, Read, Update, Delete operations.
    """
    
    def __init__(self, model: Type[ModelType]):
        """
        Initialize CRUD instance with SQLAlchemy model.
        
        Args:
            model: SQLAlchemy model class
        """
        self.model = model
    
    def get(self, db: Session, id: UUID) -> Optional[ModelType]:
        """
        Get a single record by ID.
        
        Args:
            db: Database session
            id: UUID of the record to get
            
        Returns:
            Record if found, None otherwise
        """
        return db.query(self.model).filter(self.model.id == id).first()
    
    def get_multi(
        self, db: Session, *, skip: int = 0, limit: int = 100
    ) -> List[ModelType]:
        """
        Get multiple records with pagination.
        
        Args:
            db: Database session
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of records
        """
        return db.query(self.model).offset(skip).limit(limit).all()
    
    def create(self, db: Session, *, obj_in: CreateSchemaType) -> ModelType:
        """
        Create a new record.
        
        Args:
            db: Database session
            obj_in: Pydantic model with data to create
            
        Returns:
            Created record
        """
        # Use model_dump for Pydantic v2 compatibility
        obj_in_data = obj_in.model_dump() if hasattr(obj_in, "model_dump") else dict(obj_in)
        db_obj = self.model(**obj_in_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update(
        self, 
        db: Session, 
        *, 
        db_obj: ModelType, 
        obj_in: Union[UpdateSchemaType, Dict[str, Any]]
    ) -> ModelType:
        """
        Update a record.
        
        Args:
            db: Database session
            db_obj: SQLAlchemy model instance to update
            obj_in: Pydantic model with data to update
            
        Returns:
            Updated record
        """
        obj_data = dict(db_obj.__dict__)
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            # Use model_dump for Pydantic v2 compatibility
            update_data = obj_in.model_dump(exclude_unset=True) if hasattr(obj_in, "model_dump") else obj_in.dict(exclude_unset=True)
        for field in obj_data:
            if field in update_data and field != 'id' and not field.startswith('_'):
                setattr(db_obj, field, update_data[field])
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def remove(self, db: Session, *, id: UUID) -> ModelType:
        """
        Delete a record by ID.
        
        Args:
            db: Database session
            id: UUID of the record to delete
            
        Returns:
            Deleted record
        """
        # Use first() and filter for SQLAlchemy 2.0 compatibility
        obj = db.query(self.model).filter(self.model.id == id).first()
        if obj:
            db.delete(obj)
            db.commit()
        return obj


# User CRUD operations
class CRUDUser(CRUDBase[schemas.User, models.UserCreate, models.UserUpdate]):
    """CRUD operations for User model."""
    
    def get_by_whatsapp_number(self, db: Session, whatsapp_number: str) -> Optional[schemas.User]:
        """
        Get a user by WhatsApp number.
        
        Args:
            db: Database session
            whatsapp_number: WhatsApp number to search for
            
        Returns:
            User if found, None otherwise
        """
        return db.query(self.model).filter(self.model.whatsapp_number == whatsapp_number).first()


# Invoice CRUD operations
class CRUDInvoice(CRUDBase[schemas.Invoice, models.InvoiceCreate, models.InvoiceUpdate]):
    """CRUD operations for Invoice model."""
    
    def get_by_user(self, db: Session, user_id: UUID, skip: int = 0, limit: int = 100) -> List[schemas.Invoice]:
        """
        Get invoices by user ID.
        
        Args:
            db: Database session
            user_id: User UUID
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of user's invoices
        """
        return (
            db.query(self.model)
            .filter(self.model.user_id == user_id)
            .offset(skip)
            .limit(limit)
            .all()
        )


# Item CRUD operations
class CRUDItem(CRUDBase[schemas.Item, models.ItemCreate, models.ItemUpdate]):
    """CRUD operations for Item model."""
    
    def get_by_invoice(self, db: Session, invoice_id: UUID) -> List[schemas.Item]:
        """
        Get items by invoice ID.
        
        Args:
            db: Database session
            invoice_id: Invoice UUID
            
        Returns:
            List of invoice items
        """
        return db.query(self.model).filter(self.model.invoice_id == invoice_id).all()


# Conversation CRUD operations
class CRUDConversation(CRUDBase[schemas.Conversation, models.ConversationCreate, models.ConversationUpdate]):
    """CRUD operations for Conversation model."""
    
    def get_active_by_user(self, db: Session, user_id: UUID) -> Optional[schemas.Conversation]:
        """
        Get active conversation by user ID.
        
        Args:
            db: Database session
            user_id: User UUID
            
        Returns:
            Active conversation if found, None otherwise
        """
        return (
            db.query(self.model)
            .filter(self.model.user_id == user_id, self.model.is_active == True)
            .first()
        )


# Message CRUD operations
class CRUDMessage(CRUDBase[schemas.Message, models.MessageCreate, models.MessageResponse]):
    """CRUD operations for Message model."""
    
    def get_by_conversation(
        self, db: Session, conversation_id: UUID, skip: int = 0, limit: int = 100
    ) -> List[schemas.Message]:
        """
        Get messages by conversation ID.
        
        Args:
            db: Database session
            conversation_id: Conversation UUID
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of conversation messages
        """
        return (
            db.query(self.model)
            .filter(self.model.conversation_id == conversation_id)
            .order_by(self.model.created_at)
            .offset(skip)
            .limit(limit)
            .all()
        )


# WhatsApp message CRUD operations
class CRUDWhatsAppMessage(
    CRUDBase[schemas.WhatsAppMessage, models.WhatsAppMessageCreate, models.WhatsAppMessageUpdate]
):
    """CRUD operations for WhatsAppMessage model."""
    
    def get_by_whatsapp_id(self, db: Session, whatsapp_message_id: str) -> Optional[schemas.WhatsAppMessage]:
        """
        Get WhatsApp message by WhatsApp message ID.
        
        Args:
            db: Database session
            whatsapp_message_id: WhatsApp message ID
            
        Returns:
            WhatsApp message if found, None otherwise
        """
        return (
            db.query(self.model)
            .filter(self.model.whatsapp_message_id == whatsapp_message_id)
            .first()
        )


# Media CRUD operations
class CRUDMedia(CRUDBase[schemas.Media, models.MediaCreate, models.MediaUpdate]):
    """CRUD operations for Media model."""
    
    def get_by_user(self, db: Session, user_id: UUID, skip: int = 0, limit: int = 100) -> List[schemas.Media]:
        """
        Get media files by user ID.
        
        Args:
            db: Database session
            user_id: User UUID
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of user's media files
        """
        return (
            db.query(self.model)
            .filter(self.model.user_id == user_id)
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_by_invoice(self, db: Session, invoice_id: UUID) -> List[schemas.Media]:
        """
        Get media files by invoice ID.
        
        Args:
            db: Database session
            invoice_id: Invoice UUID
            
        Returns:
            List of invoice media files
        """
        return db.query(self.model).filter(self.model.invoice_id == invoice_id).all()


# Usage CRUD operations
class CRUDUsage(CRUDBase[schemas.Usage, models.UsageCreate, models.UsageResponse]):
    """CRUD operations for Usage model."""
    
    def get_by_user(self, db: Session, user_id: UUID, skip: int = 0, limit: int = 100) -> List[schemas.Usage]:
        """
        Get usage records by user ID.
        
        Args:
            db: Database session
            user_id: User UUID
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of user's usage records
        """
        return (
            db.query(self.model)
            .filter(self.model.user_id == user_id)
            .order_by(self.model.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )


# Create instances of CRUD classes
user = CRUDUser(schemas.User)
invoice = CRUDInvoice(schemas.Invoice)
item = CRUDItem(schemas.Item)
conversation = CRUDConversation(schemas.Conversation)
message = CRUDMessage(schemas.Message)
whatsapp_message = CRUDWhatsAppMessage(schemas.WhatsAppMessage)
media = CRUDMedia(schemas.Media)
usage = CRUDUsage(schemas.Usage) 