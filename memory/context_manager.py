"""
Context Manager for the WhatsApp Invoice Assistant.

This module implements a context manager for maintaining conversation history,
with integration to the database for persistence.
"""

import logging
import datetime
from typing import Dict, List, Any, Optional, Tuple, Union
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from database import crud
from database.schemas import Conversation, Message
from database import models
from memory.langgraph_memory import memory_manager, MemoryEntry
from langchain_app.state import ConversationHistory, WorkflowState

logger = logging.getLogger(__name__)


class ContextManager:
    """
    Context manager for maintaining conversation history with database integration.
    
    This class provides functionality for retrieving, storing, and managing
    conversation context across multiple sessions, with database persistence.
    """
    
    def __init__(self, expiration_hours: int = 24):
        """
        Initialize the context manager.
        
        Args:
            expiration_hours: Hours after which a conversation is considered expired (default: 24)
        """
        self.expiration_hours = expiration_hours
        logger.info(f"Initialized ContextManager with expiration_hours={expiration_hours}")
    
    async def get_or_create_conversation(
        self, db: Session, user_id: Union[str, UUID], whatsapp_number: Optional[str] = None
    ) -> Tuple[Conversation, bool]:
        """
        Get the active conversation for a user or create a new one.
        
        Args:
            db: Database session
            user_id: User ID
            whatsapp_number: WhatsApp number (optional, for new user creation)
            
        Returns:
            Tuple of (conversation, created) where created is True if a new conversation was created
        """
        # Convert string user_id to UUID if needed
        if isinstance(user_id, str):
            try:
                user_id = UUID(user_id)
            except ValueError:
                logger.error(f"Invalid user_id format: {user_id}")
                raise ValueError(f"Invalid user_id format: {user_id}")
        
        # Try to get active conversation
        active_conversation = crud.conversation.get_active_by_user(db, user_id)
        
        if active_conversation:
            # Check if the conversation has expired
            if self._is_conversation_expired(active_conversation):
                # Mark as inactive and create a new one
                crud.conversation.update(
                    db, 
                    db_obj=active_conversation, 
                    obj_in=models.ConversationUpdate(is_active=False)
                )
                return self._create_new_conversation(db, user_id), True
            
            return active_conversation, False
        
        # Create a new conversation
        return self._create_new_conversation(db, user_id), True
    
    def _create_new_conversation(self, db: Session, user_id: UUID) -> Conversation:
        """
        Create a new conversation for a user.
        
        Args:
            db: Database session
            user_id: User ID
            
        Returns:
            Newly created conversation
        """
        conversation_data = models.ConversationCreate(
            user_id=user_id,
            is_active=True
        )
        
        conversation = crud.conversation.create(db, obj_in=conversation_data)
        logger.info(f"Created new conversation {conversation.id} for user {user_id}")
        
        return conversation
    
    def _is_conversation_expired(self, conversation: Conversation) -> bool:
        """
        Check if a conversation has expired based on the last message time.
        
        Args:
            conversation: Conversation to check
            
        Returns:
            True if the conversation has expired, False otherwise
        """
        if not conversation.updated_at:
            return False
        
        expiration_time = datetime.datetime.now() - datetime.timedelta(hours=self.expiration_hours)
        return conversation.updated_at < expiration_time
    
    async def add_message(
        self, 
        db: Session, 
        conversation_id: UUID, 
        content: str, 
        role: str = "user",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Message:
        """
        Add a message to a conversation.
        
        Args:
            db: Database session
            conversation_id: Conversation ID
            content: Message content
            role: Message role (user or assistant)
            metadata: Optional message metadata
            
        Returns:
            Created message
        """
        message_data = models.MessageCreate(
            conversation_id=conversation_id,
            content=content,
            role=role,
            metadata=metadata or {}
        )
        
        message = crud.message.create(db, obj_in=message_data)
        logger.debug(f"Added message to conversation {conversation_id}")
        
        return message
    
    async def get_conversation_history(
        self, db: Session, conversation_id: UUID, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get the conversation history for a conversation.
        
        Args:
            db: Database session
            conversation_id: Conversation ID
            limit: Maximum number of messages to return
            
        Returns:
            List of messages in the conversation
        """
        messages = crud.message.get_by_conversation(db, conversation_id, limit=limit)
        
        # Convert to format expected by agents
        history = []
        for message in messages:
            history.append({
                "role": message.role,
                "content": message.content,
                "timestamp": message.created_at.isoformat() if message.created_at else None,
                "metadata": message.metadata
            })
        
        return history
    
    async def sync_memory_to_db(
        self, db: Session, conversation_id: str, user_id: Union[str, UUID]
    ) -> bool:
        """
        Sync in-memory conversation history to the database.
        
        Args:
            db: Database session
            conversation_id: Conversation ID (string)
            user_id: User ID
            
        Returns:
            True if sync was successful, False otherwise
        """
        # Get memory entry
        memory_entry = memory_manager.retrieve(conversation_id)
        if not memory_entry:
            logger.warning(f"No memory entry found for conversation {conversation_id}")
            return False
        
        # Convert string IDs to UUIDs if needed
        db_conversation_id = UUID(conversation_id) if isinstance(conversation_id, str) else conversation_id
        db_user_id = UUID(user_id) if isinstance(user_id, str) else user_id
        
        # Get or create conversation
        conversation, created = await self.get_or_create_conversation(db, db_user_id)
        
        if created:
            logger.info(f"Created new conversation {conversation.id} during sync")
            
        # Add messages that aren't already in the database
        db_messages = await self.get_conversation_history(db, conversation.id)
        db_message_timestamps = {
            msg.get("timestamp"): True for msg in db_messages if msg.get("timestamp")
        }
        
        for message in memory_entry.messages:
            # Skip messages already in the database
            if message.get("timestamp") in db_message_timestamps:
                continue
                
            # Add new message
            await self.add_message(
                db,
                conversation.id,
                content=message.get("content", ""),
                role=message.get("role", "user"),
                metadata={"timestamp": message.get("timestamp"), "source": "memory_sync"}
            )
            
        logger.info(f"Synced memory to database for conversation {conversation_id}")
        return True
    
    async def load_state_with_history(
        self, db: Session, user_id: Union[str, UUID], conversation_id: Optional[str] = None
    ) -> Tuple[str, ConversationHistory]:
        """
        Load conversation history into a state object, getting or creating conversation as needed.
        
        Args:
            db: Database session
            user_id: User ID
            conversation_id: Optional conversation ID (if None, get active or create new)
            
        Returns:
            Tuple of (conversation_id, conversation_history)
        """
        # Convert string user_id to UUID if needed
        db_user_id = UUID(user_id) if isinstance(user_id, str) else user_id
        
        # If conversation_id provided, try to retrieve from memory
        if conversation_id:
            memory_entry = memory_manager.retrieve(conversation_id)
            if memory_entry:
                # Found in memory, return
                return conversation_id, ConversationHistory(messages=memory_entry.messages)
        
        # Get or create conversation from DB
        conversation, created = await self.get_or_create_conversation(db, db_user_id)
        conv_id = str(conversation.id)
        
        # If already in memory, return that
        memory_entry = memory_manager.retrieve(conv_id)
        if memory_entry:
            return conv_id, ConversationHistory(messages=memory_entry.messages)
        
        # Load from database and populate memory
        history_list = await self.get_conversation_history(db, conversation.id)
        history = ConversationHistory(messages=history_list)
        
        # Store in memory for future use
        initial_state = WorkflowState(conversation_history=history)
        memory_manager.store(conv_id, str(db_user_id), initial_state)
        
        return conv_id, history


# Create a singleton instance
context_manager = ContextManager() 