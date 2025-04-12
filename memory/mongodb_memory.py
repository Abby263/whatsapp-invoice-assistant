"""
MongoDB-based Memory for the WhatsApp Invoice Assistant.

This module implements stateful memory management for the LangGraph workflow using MongoDB,
providing functionality to store, retrieve, and manage conversation context with persistence.
"""

import logging
import datetime
import time
import os
from typing import Dict, List, Any, Optional, Set, Tuple, Union
from uuid import UUID, uuid4
import json

from pydantic import BaseModel, Field
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection

from langchain_app.state import ConversationHistory, WorkflowState
from utils.config import config

logger = logging.getLogger(__name__)


class MongoDBMemory:
    """
    MongoDB-based memory management system for LangGraph workflows.
    
    This class provides functionality for storing, retrieving, and managing
    conversation history and context across multiple interactions with persistence.
    """
    
    def __init__(self, 
                max_memory_age: Optional[int] = None, 
                max_messages: Optional[int] = None,
                mongo_uri: Optional[str] = None,
                db_name: Optional[str] = None):
        """
        Initialize the MongoDB memory manager.
        
        Args:
            max_memory_age: Maximum age of memory entries in seconds (default: from config)
            max_messages: Maximum number of messages to keep in memory per conversation (default: from config)
            mongo_uri: MongoDB connection URI (default: from config)
            db_name: MongoDB database name (default: from config)
        """
        # Load settings from config
        mongodb_config = config.get("mongodb", default={})
        memory_config = mongodb_config.get("memory", {}) if mongodb_config else {}
        
        # Use provided values or fall back to config values
        self.max_memory_age = max_memory_age or memory_config.get("max_memory_age", 3600)
        self.max_messages = max_messages or memory_config.get("max_messages", 50)
        
        # Get MongoDB URI from config
        self.mongo_uri = mongo_uri or mongodb_config.get("uri")
        if not self.mongo_uri:
            # Final fallback to environment variable
            self.mongo_uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
        
        # Set database name
        self.db_name = db_name or mongodb_config.get("db_name", "whatsapp_invoice_assistant")
        
        # Adjust URI for Docker environment
        if (os.environ.get("PYTHONPATH") == "/app" or 
            os.environ.get("IN_DOCKER") == "true" or 
            os.path.exists("/.dockerenv")):
            # If MONGODB_URI explicitly contains container name, use it
            if "whatsapp-invoice-assistant-mongodb" in self.mongo_uri:
                logger.info(f"Using provided MongoDB URI in Docker: {self.mongo_uri}")
            # Otherwise fix the hostname for Docker environment
            elif "mongodb://" in self.mongo_uri and "localhost" in self.mongo_uri:
                self.mongo_uri = self.mongo_uri.replace("localhost", "whatsapp-invoice-assistant-mongodb")
                logger.info(f"Adjusted MongoDB URI for Docker environment: {self.mongo_uri}")
            elif "mongodb://mongodb" in self.mongo_uri:
                self.mongo_uri = self.mongo_uri.replace("mongodb://mongodb", "mongodb://whatsapp-invoice-assistant-mongodb")
                logger.info(f"Adjusted MongoDB URI from 'mongodb' to container name: {self.mongo_uri}")
        
        # Initialize MongoDB client and collections
        self._init_mongodb()
        
        logger.info(f"Initialized MongoDBMemory with max_memory_age={self.max_memory_age}s, max_messages={self.max_messages}")
        
    def _init_mongodb(self):
        """Initialize MongoDB client and collections."""
        try:
            self.client = MongoClient(self.mongo_uri)
            self.db = self.client[self.db_name]
            
            # Create collections if they don't exist
            self.conversations = self.db.conversations
            self.messages = self.db.messages
            
            # Create indexes for efficient querying
            self.conversations.create_index("conversation_id", unique=True)
            self.conversations.create_index("user_id")
            self.conversations.create_index("last_accessed")
            
            self.messages.create_index([("conversation_id", 1), ("timestamp", 1)])
            
            logger.info(f"Successfully connected to MongoDB at {self.mongo_uri}")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {str(e)}")
            # Create fallback in-memory storage
            self._memory: Dict[str, Dict[str, Any]] = {}
            self._fallback_mode = True
            logger.warning("Using fallback in-memory storage due to MongoDB connection failure")
    
    def store(self, conversation_id: str, user_id: str, state: Any) -> None:
        """
        Store a workflow state in MongoDB memory.
        
        Args:
            conversation_id: Unique identifier for the conversation
            user_id: Identifier for the user
            state: Current workflow state to store (can be WorkflowState or dict from LangGraph)
        """
        try:
            # Convert state to dict if it's not already
            state_dict = state
            if hasattr(state, 'dict'):
                state_dict = state.dict()
            elif hasattr(state, 'to_dict'):
                state_dict = state.to_dict()
            
            # Extract messages to store
            messages_to_store = []
            
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
                    "timestamp": datetime.datetime.now(),
                    "conversation_id": conversation_id
                }
                messages_to_store.append(message)
            
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
                        "timestamp": datetime.datetime.now(),
                        "conversation_id": conversation_id
                    }
                    messages_to_store.append(message)
            
            # Extract and store important metadata from the state
            metadata = {}
            if 'intent' in state_dict:
                metadata["intent"] = state_dict['intent']
            if 'extracted_entities' in state_dict:
                metadata["extracted_entities"] = state_dict['extracted_entities']
            if 'extracted_invoice_data' in state_dict:
                metadata["extracted_invoice_data"] = state_dict['extracted_invoice_data']
            
            # Update conversation record
            conversation_update = {
                "$set": {
                    "user_id": user_id,
                    "last_accessed": datetime.datetime.now(),
                    "metadata": metadata
                },
                "$setOnInsert": {
                    "created_at": datetime.datetime.now()
                }
            }
            
            # Upsert conversation record
            self.conversations.update_one(
                {"conversation_id": conversation_id},
                conversation_update,
                upsert=True
            )
            
            # Insert messages
            if messages_to_store:
                self.messages.insert_many(messages_to_store)
                
                # Trim excess messages if needed
                message_count = self.messages.count_documents({"conversation_id": conversation_id})
                if message_count > self.max_messages:
                    # Find ids of oldest messages to delete
                    excess = message_count - self.max_messages
                    oldest_messages = list(self.messages.find(
                        {"conversation_id": conversation_id},
                        sort=[("timestamp", 1)],
                        limit=excess
                    ))
                    
                    if oldest_messages:
                        oldest_ids = [msg["_id"] for msg in oldest_messages]
                        self.messages.delete_many({"_id": {"$in": oldest_ids}})
                        logger.debug(f"Trimmed {len(oldest_ids)} old messages for conversation {conversation_id}")
            
            logger.debug(f"Stored state in MongoDB for conversation {conversation_id}")
            
        except Exception as e:
            logger.error(f"Error storing state in MongoDB: {str(e)}", exc_info=True)
            # Handle fallback if needed
    
    def retrieve(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a conversation memory entry.
        
        Args:
            conversation_id: Unique identifier for the conversation
            
        Returns:
            Memory entry if found, None otherwise
        """
        try:
            # Get conversation record
            conversation = self.conversations.find_one({"conversation_id": conversation_id})
            if not conversation:
                logger.debug(f"No conversation found for id {conversation_id}")
                return None
            
            # Update last accessed time
            self.conversations.update_one(
                {"conversation_id": conversation_id},
                {"$set": {"last_accessed": datetime.datetime.now()}}
            )
            
            # Get messages for this conversation
            messages_cursor = self.messages.find(
                {"conversation_id": conversation_id},
                sort=[("timestamp", 1)]
            )
            
            # Convert MongoDB cursor to list and format for compatibility
            messages = []
            for msg in messages_cursor:
                # Remove MongoDB-specific fields and format for API
                formatted_msg = {
                    "role": msg["role"],
                    "content": msg["content"],
                    "timestamp": msg["timestamp"].isoformat() if isinstance(msg["timestamp"], datetime.datetime) else msg["timestamp"]
                }
                messages.append(formatted_msg)
            
            # Construct memory entry
            memory_entry = {
                "conversation_id": conversation_id,
                "user_id": conversation["user_id"],
                "messages": messages,
                "metadata": conversation.get("metadata", {}),
                "last_accessed": conversation["last_accessed"]
            }
            
            return memory_entry
            
        except Exception as e:
            logger.error(f"Error retrieving conversation from MongoDB: {str(e)}", exc_info=True)
            return None
    
    def load_conversation_history(self, conversation_id: str) -> ConversationHistory:
        """
        Load conversation history for use in a workflow state.
        
        Args:
            conversation_id: Unique identifier for the conversation
            
        Returns:
            ConversationHistory object for the workflow state
        """
        memory_entry = self.retrieve(conversation_id)
        
        if not memory_entry:
            return ConversationHistory(messages=[])
        
        return ConversationHistory(messages=memory_entry["messages"])
    
    def clear(self, conversation_id: str) -> bool:
        """
        Clear a specific conversation from memory.
        
        Args:
            conversation_id: Unique identifier for the conversation
            
        Returns:
            True if the conversation was cleared, False otherwise
        """
        try:
            # Delete conversation and all its messages
            result_conv = self.conversations.delete_one({"conversation_id": conversation_id})
            result_msgs = self.messages.delete_many({"conversation_id": conversation_id})
            
            if result_conv.deleted_count > 0 or result_msgs.deleted_count > 0:
                logger.info(f"Cleared memory for conversation {conversation_id}: {result_msgs.deleted_count} messages deleted")
                return True
            return False
        except Exception as e:
            logger.error(f"Error clearing conversation from MongoDB: {str(e)}", exc_info=True)
            return False
    
    def cleanup_expired(self) -> int:
        """
        Clean up expired conversations from memory.
        
        Returns:
            Number of conversations cleared
        """
        try:
            # Calculate expiration threshold
            expiration_threshold = datetime.datetime.now() - datetime.timedelta(seconds=self.max_memory_age)
            
            # Find expired conversations
            expired_conversations = list(self.conversations.find(
                {"last_accessed": {"$lt": expiration_threshold}},
                {"conversation_id": 1}
            ))
            
            if not expired_conversations:
                return 0
            
            # Extract conversation IDs
            expired_ids = [conv["conversation_id"] for conv in expired_conversations]
            
            # Delete expired conversations and their messages
            self.conversations.delete_many({"conversation_id": {"$in": expired_ids}})
            self.messages.delete_many({"conversation_id": {"$in": expired_ids}})
            
            logger.info(f"Cleaned up {len(expired_ids)} expired conversations")
            return len(expired_ids)
            
        except Exception as e:
            logger.error(f"Error cleaning up expired conversations from MongoDB: {str(e)}", exc_info=True)
            return 0
    
    def get_active_conversations(self) -> List[str]:
        """
        Get all active conversation IDs.
        
        Returns:
            List of active conversation IDs
        """
        try:
            # Get conversations active in the last hour
            recent_threshold = datetime.datetime.now() - datetime.timedelta(hours=1)
            conversations = list(self.conversations.find(
                {"last_accessed": {"$gt": recent_threshold}},
                {"conversation_id": 1}
            ))
            
            return [conv["conversation_id"] for conv in conversations]
        except Exception as e:
            logger.error(f"Error getting active conversations from MongoDB: {str(e)}", exc_info=True)
            return []
    
    def get_user_conversations(self, user_id: str) -> List[str]:
        """
        Get all conversation IDs for a specific user.
        
        Args:
            user_id: User identifier
            
        Returns:
            List of conversation IDs
        """
        try:
            conversations = self.conversations.find({"user_id": user_id})
            return [conv["conversation_id"] for conv in conversations]
        except Exception as e:
            logger.error(f"Error retrieving user conversations: {str(e)}")
            return []
            
    def get_memory_by_user(self, user_id: str) -> Dict[str, Any]:
        """
        Get all memory data for a specific user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Dictionary containing user memory data including conversations and messages
        """
        try:
            # Get all conversations for this user
            conversations = list(self.conversations.find(
                {"user_id": user_id},
                sort=[("last_accessed", -1)]
            ))
            
            # Get conversation IDs
            conversation_ids = [conv["conversation_id"] for conv in conversations]
            
            # Get messages for these conversations
            all_messages = {}
            for conv_id in conversation_ids:
                messages = list(self.messages.find(
                    {"conversation_id": conv_id},
                    sort=[("timestamp", 1)]
                ))
                # Convert ObjectId to string for JSON serialization
                for msg in messages:
                    if "_id" in msg:
                        msg["_id"] = str(msg["_id"])
                    if "timestamp" in msg:
                        msg["timestamp"] = msg["timestamp"].isoformat()
                
                all_messages[conv_id] = messages
            
            # Prepare the response
            result = {
                "user_id": user_id,
                "conversations": [],
                "message_count": sum(len(msgs) for msgs in all_messages.values())
            }
            
            # Format conversation data
            for conv in conversations:
                # Convert ObjectId to string for JSON serialization
                if "_id" in conv:
                    conv["_id"] = str(conv["_id"])
                # Convert datetime objects to ISO format strings
                for field in ["created_at", "last_accessed"]:
                    if field in conv and isinstance(conv[field], datetime.datetime):
                        conv[field] = conv[field].isoformat()
                
                # Add messages to the conversation
                conv_id = conv["conversation_id"]
                conv["messages"] = all_messages.get(conv_id, [])
                result["conversations"].append(conv)
            
            return result
        except Exception as e:
            logger.error(f"Error retrieving memory for user {user_id}: {str(e)}")
            return {"user_id": user_id, "conversations": [], "message_count": 0, "error": str(e)}
    
    def delete_memory_by_user(self, user_id: str) -> Dict[str, Any]:
        """
        Delete all memory data for a specific user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Dictionary with deletion results
        """
        try:
            # Get all conversations for this user
            conversations = list(self.conversations.find({"user_id": user_id}))
            conversation_ids = [conv["conversation_id"] for conv in conversations]
            
            # Delete all messages for these conversations
            message_result = self.messages.delete_many({"conversation_id": {"$in": conversation_ids}})
            
            # Delete the conversations
            conversation_result = self.conversations.delete_many({"user_id": user_id})
            
            return {
                "user_id": user_id,
                "conversations_deleted": conversation_result.deleted_count,
                "messages_deleted": message_result.deleted_count,
                "conversation_ids": conversation_ids
            }
        except Exception as e:
            logger.error(f"Error deleting memory for user {user_id}: {str(e)}")
            return {
                "user_id": user_id, 
                "error": str(e),
                "conversations_deleted": 0,
                "messages_deleted": 0
            }


# Create singleton instance
mongodb_memory = MongoDBMemory() 