"""
LangGraph Memory for the WhatsApp Invoice Assistant.

This module implements stateful memory management for the LangGraph workflow,
providing functionality to store, retrieve, and manage conversation context.
"""

import logging
import datetime
import time
import os
from typing import Dict, List, Any, Optional, Set, Tuple
from uuid import UUID
import json

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import crud
from database.schemas import Conversation, Message
from langchain_app.state import ConversationHistory, WorkflowState
from utils.config import config

logger = logging.getLogger(__name__)


class MemoryEntry(BaseModel):
    """A single entry in memory, representing a specific conversation state."""
    conversation_id: str
    user_id: str
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    last_accessed: float = Field(default_factory=time.time)
    

class LangGraphMemory:
    """
    Memory management system for LangGraph workflows.
    
    This class provides functionality for storing, retrieving, and managing
    conversation history and context across multiple interactions.
    """
    
    def __init__(self):
        """
        Initialize the memory manager with configuration from environment/config file.
        """
        # Load configuration from config file or environment variables with defaults
        try:
            self.max_memory_age = int(os.environ.get(
                "MONGODB_MAX_MEMORY_AGE", 
                config.get("mongodb", key="memory", default={}).get("max_memory_age", 3600)
            ))
            self.max_messages = int(os.environ.get(
                "MONGODB_MAX_MESSAGES", 
                config.get("mongodb", key="memory", default={}).get("max_messages", 50)
            ))
            self.message_window = int(os.environ.get(
                "MONGODB_MESSAGE_WINDOW", 
                config.get("mongodb", key="memory", default={}).get("message_window", 10)
            ))
            self.enable_context_window = os.environ.get(
                "MONGODB_ENABLE_CONTEXT_WINDOW", 
                config.get("mongodb", key="memory", default={}).get("enable_context_window", "true")
            ).lower() == "true"
            self.persist_memory = os.environ.get(
                "MONGODB_PERSIST_MEMORY", 
                config.get("mongodb", key="memory", default={}).get("persist_memory", "true")
            ).lower() == "true"
        except Exception as e:
            logger.warning(f"Error loading memory configuration: {str(e)}. Using defaults.")
            # Default values if loading fails
            self.max_memory_age = 3600  # 1 hour
            self.max_messages = 50
            self.message_window = 10
            self.enable_context_window = True
            self.persist_memory = True

        self._memory: Dict[str, MemoryEntry] = {}
        
        # Flag to indicate whether to use MongoDB
        self.use_mongodb = self.persist_memory and os.environ.get("USE_MONGODB", "true").lower() == "true"
        
        if self.use_mongodb:
            try:
                # Try to import MongoDB memory
                from memory.mongodb_memory import MongoDBMemory
                # Initialize with our configuration
                self.mongodb_memory = MongoDBMemory(
                    max_memory_age=self.max_memory_age,
                    max_messages=self.max_messages
                )
                logger.info("Using MongoDB for LangGraph memory persistence")
            except ImportError:
                logger.warning("MongoDB memory not available, falling back to in-memory storage")
                self.use_mongodb = False
                
        logger.info(f"Initialized LangGraphMemory with settings: max_memory_age={self.max_memory_age}s, " 
                   f"max_messages={self.max_messages}, message_window={self.message_window}, "
                   f"enable_context_window={self.enable_context_window}, persist_memory={self.persist_memory}")
    
    def get_windowed_history(self, conversation_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Apply context window settings to conversation history.
        
        Args:
            conversation_history: Full conversation history
            
        Returns:
            Windowed conversation history based on configuration
        """
        if not self.enable_context_window or len(conversation_history) <= self.message_window:
            return conversation_history
        
        # Return only the most recent N messages based on message_window setting
        return conversation_history[-self.message_window:]
    
    def store(self, conversation_id: str, user_id: str, state: Any) -> None:
        """
        Store a workflow state in memory.
        
        Args:
            conversation_id: Unique identifier for the conversation
            user_id: Identifier for the user
            state: Current workflow state to store (can be WorkflowState or dict from LangGraph)
        """
        # If using MongoDB, delegate to MongoDB memory
        if self.use_mongodb:
            try:
                self.mongodb_memory.store(conversation_id, user_id, state)
                return
            except Exception as e:
                logger.error(f"Error storing in MongoDB: {str(e)}", exc_info=True)
                logger.warning("Falling back to in-memory storage for this operation")
                
        # Fallback to in-memory storage
        # Create or update memory entry
        if conversation_id not in self._memory:
            self._memory[conversation_id] = MemoryEntry(
                conversation_id=conversation_id,
                user_id=user_id,
                messages=[],
                metadata={}
            )
        
        # Update last accessed time
        self._memory[conversation_id].last_accessed = time.time()
        
        # Convert state to dict if it's not already
        state_dict = state
        if hasattr(state, 'dict'):
            state_dict = state.dict()
        
        # Store user input if it exists
        user_input = state_dict.get('user_input')
        if user_input:
            content = ""
            content_type = ""
            
            # Handle different input formats
            if isinstance(user_input, dict):
                # Dictionary format
                content = user_input.get('content', '')
                content_type = user_input.get('content_type', '')
            else:
                # Object format with attributes
                content = getattr(user_input, 'content', '')
                content_type = getattr(user_input, 'content_type', '')
                
            # Handle binary content
            if hasattr(content, "decode"):
                content = f"[Binary content of type {content_type}]"
            
            message = {
                "role": "user",
                "content": content,
                "timestamp": datetime.datetime.now().isoformat()
            }
            self._memory[conversation_id].messages.append(message)
        
        # Store system response if it exists
        current_response = state_dict.get('current_response')
        if current_response:
            content = ""
            
            # Handle different response formats
            if isinstance(current_response, dict):
                # Dictionary format
                content = current_response.get('content', '')
            else:
                # Object format with attributes
                content = getattr(current_response, 'content', '')
            
            if content:
                message = {
                    "role": "assistant",
                    "content": content,
                    "timestamp": datetime.datetime.now().isoformat()
                }
                self._memory[conversation_id].messages.append(message)
        
        # Extract and store important metadata from the state
        metadata = {}
        if 'intent' in state_dict:
            metadata["intent"] = state_dict['intent']
        if 'extracted_entities' in state_dict:
            metadata["extracted_entities"] = state_dict['extracted_entities']
        if 'extracted_invoice_data' in state_dict:
            metadata["extracted_invoice_data"] = state_dict['extracted_invoice_data']
            
        # Update metadata
        self._memory[conversation_id].metadata.update(metadata)
        
        # Trim messages if exceeding max_messages
        if len(self._memory[conversation_id].messages) > self.max_messages:
            excess = len(self._memory[conversation_id].messages) - self.max_messages
            self._memory[conversation_id].messages = self._memory[conversation_id].messages[excess:]
            
        logger.debug(f"Stored state in memory for conversation {conversation_id}")
    
    def retrieve(self, conversation_id: str) -> Optional[MemoryEntry]:
        """
        Retrieve a conversation memory entry.
        
        Args:
            conversation_id: Unique identifier for the conversation
            
        Returns:
            Memory entry if found, None otherwise
        """
        # If using MongoDB, delegate to MongoDB memory
        if self.use_mongodb:
            try:
                memory_data = self.mongodb_memory.retrieve(conversation_id)
                if memory_data:
                    # Convert to MemoryEntry
                    return MemoryEntry(
                        conversation_id=memory_data["conversation_id"],
                        user_id=memory_data["user_id"],
                        messages=memory_data["messages"],
                        metadata=memory_data.get("metadata", {}),
                        last_accessed=time.time()  # Always update last accessed time
                    )
                return None
            except Exception as e:
                logger.error(f"Error retrieving from MongoDB: {str(e)}", exc_info=True)
                logger.warning("Falling back to in-memory storage for this operation")
        
        # Check if conversation exists in memory
        if conversation_id not in self._memory:
            logger.debug(f"No memory found for conversation {conversation_id}")
            return None
        
        # Update last accessed time
        self._memory[conversation_id].last_accessed = time.time()
        
        return self._memory[conversation_id]
    
    def load_conversation_history(self, conversation_id: str) -> ConversationHistory:
        """
        Load conversation history for use in a workflow state.
        
        Args:
            conversation_id: Unique identifier for the conversation
            
        Returns:
            ConversationHistory object for the workflow state
        """
        # If using MongoDB, delegate to MongoDB memory
        if self.use_mongodb:
            try:
                memory_data = self.mongodb_memory.retrieve(conversation_id)
                if memory_data:
                    # Apply context window if enabled
                    messages = self.get_windowed_history(memory_data["messages"])
                    return ConversationHistory(messages=messages)
                return ConversationHistory(messages=[])
            except Exception as e:
                logger.error(f"Error loading conversation history from MongoDB: {str(e)}", exc_info=True)
                logger.warning("Falling back to in-memory storage for this operation")
        
        memory_entry = self.retrieve(conversation_id)
        
        if not memory_entry:
            return ConversationHistory(messages=[])
        
        # Apply context window if enabled
        messages = self.get_windowed_history(memory_entry.messages)
        return ConversationHistory(messages=messages)
    
    def update_config(self, 
                     max_memory_age: Optional[int] = None, 
                     max_messages: Optional[int] = None,
                     message_window: Optional[int] = None,
                     enable_context_window: Optional[bool] = None,
                     persist_memory: Optional[bool] = None) -> Dict[str, Any]:
        """
        Update memory configuration at runtime.
        
        This allows developers to adjust memory parameters dynamically.
        
        Args:
            max_memory_age: Maximum age of memory entries in seconds
            max_messages: Maximum number of messages to keep in memory per conversation
            message_window: Number of recent messages to use for context in agents
            enable_context_window: Whether to use sliding context window
            persist_memory: Whether to persist memory between restarts
            
        Returns:
            Dict with updated configuration
        """
        if max_memory_age is not None:
            self.max_memory_age = max_memory_age
            logger.info(f"Updated max_memory_age to {max_memory_age}s")
            
        if max_messages is not None:
            self.max_messages = max_messages
            logger.info(f"Updated max_messages to {max_messages}")
            
        if message_window is not None:
            self.message_window = message_window
            logger.info(f"Updated message_window to {message_window}")
            
        if enable_context_window is not None:
            self.enable_context_window = enable_context_window
            logger.info(f"Updated enable_context_window to {enable_context_window}")
            
        if persist_memory is not None:
            prev_persist = self.persist_memory
            self.persist_memory = persist_memory
            logger.info(f"Updated persist_memory to {persist_memory}")
            
            # If changing persistence settings, update MongoDB usage
            if prev_persist != persist_memory:
                self.use_mongodb = self.persist_memory and os.environ.get("USE_MONGODB", "true").lower() == "true"
                logger.info(f"Updated use_mongodb to {self.use_mongodb}")
        
        # Update MongoDB memory configuration if using it
        if self.use_mongodb and hasattr(self, 'mongodb_memory'):
            try:
                self.mongodb_memory.max_memory_age = self.max_memory_age
                self.mongodb_memory.max_messages = self.max_messages
                logger.info("Updated MongoDB memory configuration")
            except Exception as e:
                logger.error(f"Error updating MongoDB memory configuration: {str(e)}")
        
        # Return current configuration
        return self.get_config()
    
    def get_config(self) -> Dict[str, Any]:
        """
        Get the current memory configuration settings.
        
        Returns:
            Dict with current configuration settings
        """
        return {
            "max_memory_age": self.max_memory_age,
            "max_messages": self.max_messages,
            "message_window": self.message_window,
            "enable_context_window": self.enable_context_window,
            "persist_memory": self.persist_memory,
            "use_mongodb": self.use_mongodb
        }


# Create singleton instance with default configuration
memory_manager = LangGraphMemory() 