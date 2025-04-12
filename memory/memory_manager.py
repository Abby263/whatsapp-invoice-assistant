"""
Memory manager utility functions.

This module provides simplified access to LangGraph memory management functions,
acting as a wrapper around the LangGraphMemory class.
"""

from typing import Dict, Any, Optional, List
import logging

from memory.langgraph_memory import memory_manager

logger = logging.getLogger(__name__)

def get_memory() -> Dict[str, Any]:
    """
    Get current memory configuration settings.
    
    Returns:
        Dict with current memory configuration including:
        - max_memory_age: Maximum age of memory entries in seconds
        - max_messages: Maximum number of messages to keep in memory
        - message_window: Number of messages to return in context window
        - enable_context_window: Whether to use context window
        - persist_memory: Whether to persist memory to storage
        - use_mongodb: Whether MongoDB is being used for storage
    """
    return memory_manager.get_config()

def set_memory_config(
    max_memory_age: Optional[int] = None, 
    max_messages: Optional[int] = None,
    message_window: Optional[int] = None,
    enable_context_window: Optional[bool] = None,
    persist_memory: Optional[bool] = None
) -> Dict[str, Any]:
    """
    Update memory configuration settings.
    
    Args:
        max_memory_age: Maximum age of memory entries in seconds
        max_messages: Maximum number of messages to keep in memory
        message_window: Number of messages to return in context window
        enable_context_window: Whether to use context window
        persist_memory: Whether to persist memory to storage
        
    Returns:
        Dict with updated configuration
    """
    logger.info(f"Updating memory configuration: age={max_memory_age}s, max_msgs={max_messages}, window={message_window}, context_enabled={enable_context_window}, persist={persist_memory}")
    
    return memory_manager.update_config(
        max_memory_age=max_memory_age,
        max_messages=max_messages,
        message_window=message_window,
        enable_context_window=enable_context_window,
        persist_memory=persist_memory
    ) 