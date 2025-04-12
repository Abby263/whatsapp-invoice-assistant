"""
MongoDB Checkpoint Implementation for LangGraph.

This module provides a custom checkpoint implementation for LangGraph
using MongoDB for persistence.
"""

import logging
import os
import json
import datetime
from typing import Dict, Any, List, Optional, Tuple, Set, Union
from uuid import UUID
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection

try:
    # Import LangGraph checkpoint classes if available
    from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint
except ImportError:
    # Create stub classes as fallback
    class BaseCheckpointSaver:
        """Stub class for BaseCheckpointSaver."""
        pass
    
    class Checkpoint:
        """Stub class for Checkpoint."""
        pass

logger = logging.getLogger(__name__)


class MongoDBCheckpointSaver(BaseCheckpointSaver):
    """
    MongoDB-based checkpoint saver for LangGraph.
    
    This class enables LangGraph to persist state in MongoDB, allowing
    conversations to continue across different sessions.
    """
    
    def __init__(
        self,
        mongo_uri: Optional[str] = None,
        db_name: str = "whatsapp_invoice_assistant",
        collection_name: str = "langgraph_checkpoints",
        ttl_seconds: int = 86400,  # 24 hours
    ):
        """
        Initialize the MongoDB checkpoint saver.
        
        Args:
            mongo_uri: MongoDB connection URI (defaults to MONGODB_URI env var)
            db_name: MongoDB database name
            collection_name: MongoDB collection name for checkpoints
            ttl_seconds: Time-to-live for checkpoint documents in seconds
        """
        self.mongo_uri = mongo_uri or os.environ.get(
            "MONGODB_URI", "mongodb://localhost:27017/whatsapp_invoice_assistant"
        )
        self.db_name = db_name
        self.collection_name = collection_name
        self.ttl_seconds = ttl_seconds
        
        # Instead of using CheckpointAt, we'll just use a string
        self.at = "end_of_run"
        
        # Connect to MongoDB
        try:
            self.client = MongoClient(self.mongo_uri)
            self.db = self.client[self.db_name]
            self.collection = self.db[self.collection_name]
            
            # Create TTL index if it doesn't exist
            self.collection.create_index(
                "last_accessed", 
                expireAfterSeconds=self.ttl_seconds
            )
            
            logger.info(
                f"Initialized MongoDB checkpoint saver using {self.mongo_uri}, "
                f"db: {self.db_name}, collection: {self.collection_name}"
            )
        except Exception as e:
            logger.error(f"Error connecting to MongoDB: {str(e)}")
            raise
    
    def get_state(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        Get checkpoint state for a thread.
        
        Args:
            thread_id: Thread ID to retrieve
            
        Returns:
            Checkpoint state dict or None if not found
        """
        try:
            # Find checkpoint with matching thread_id
            checkpoint = self.collection.find_one({"thread_id": thread_id})
            
            if not checkpoint:
                logger.debug(f"No checkpoint found for thread {thread_id}")
                return None
            
            # Update last accessed time
            self.collection.update_one(
                {"thread_id": thread_id},
                {"$set": {"last_accessed": datetime.datetime.now()}}
            )
            
            logger.debug(f"Retrieved checkpoint for thread {thread_id}")
            return checkpoint.get("state")
        except Exception as e:
            logger.error(f"Error retrieving checkpoint for thread {thread_id}: {str(e)}")
            return None
    
    def set_state(self, thread_id: str, state: Dict[str, Any]) -> None:
        """
        Set checkpoint state for a thread.
        
        Args:
            thread_id: Thread ID to update
            state: Checkpoint state dict to save
        """
        try:
            # Create document
            doc = {
                "thread_id": thread_id,
                "state": state,
                "last_accessed": datetime.datetime.now()
            }
            
            # Upsert the document
            self.collection.update_one(
                {"thread_id": thread_id},
                {"$set": doc},
                upsert=True
            )
            
            logger.debug(f"Saved checkpoint for thread {thread_id}")
        except Exception as e:
            logger.error(f"Error saving checkpoint for thread {thread_id}: {str(e)}")
    
    def delete_state(self, thread_id: str) -> None:
        """
        Delete checkpoint state for a thread.
        
        Args:
            thread_id: Thread ID to delete
        """
        try:
            # Delete the document
            result = self.collection.delete_one({"thread_id": thread_id})
            
            if result.deleted_count > 0:
                logger.debug(f"Deleted checkpoint for thread {thread_id}")
            else:
                logger.debug(f"No checkpoint found for thread {thread_id} to delete")
        except Exception as e:
            logger.error(f"Error deleting checkpoint for thread {thread_id}: {str(e)}")
    
    def list_threads(self) -> List[str]:
        """
        List all thread IDs with saved checkpoints.
        
        Returns:
            List of thread IDs
        """
        try:
            # Find all thread IDs
            thread_ids = list(self.collection.distinct("thread_id"))
            
            logger.debug(f"Found {len(thread_ids)} threads in checkpoints")
            return thread_ids
        except Exception as e:
            logger.error(f"Error listing checkpoint threads: {str(e)}")
            return []
    
    # Implement the required interface methods
    def get(self, config):
        """Get checkpoint state for the thread in config."""
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        state = self.get_state(thread_id)
        if state:
            return state
        return None
    
    def put(self, config, checkpoint):
        """Save checkpoint state for the thread in config."""
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        self.set_state(thread_id, checkpoint)
        return None


def create_mongodb_checkpoint_saver() -> Optional[MongoDBCheckpointSaver]:
    """
    Create a MongoDB checkpoint saver if MongoDB is available and enabled.
    
    Returns:
        MongoDBCheckpointSaver instance or None if MongoDB is not available or disabled
    """
    # Check if MongoDB is enabled
    use_mongodb = os.environ.get("USE_MONGODB", "true").lower() == "true"
    if not use_mongodb:
        logger.info("MongoDB is disabled, not creating checkpoint saver")
        return None
    
    try:
        # Try to create and test MongoDB connection
        mongo_uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/whatsapp_invoice_assistant")
        
        # Create the checkpoint saver
        saver = MongoDBCheckpointSaver(mongo_uri=mongo_uri)
        
        # Test connection by listing threads (which should not raise exceptions)
        saver.list_threads()
        
        # Create a test document to ensure the collection exists
        test_thread_id = "test_connection"
        saver.set_state(test_thread_id, {"test": True, "timestamp": str(datetime.datetime.now())})
        saver.delete_state(test_thread_id)
        
        logger.info("Successfully created MongoDB checkpoint saver")
        return saver
    except Exception as e:
        logger.error(f"Failed to create MongoDB checkpoint saver: {str(e)}")
        return None 