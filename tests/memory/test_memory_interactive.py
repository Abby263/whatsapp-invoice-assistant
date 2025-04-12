#!/usr/bin/env python
"""
Interactive test for memory and context management.

This script tests the memory and context management by simulating a conversation
with the assistant.
"""

import asyncio
import sys
import os
import logging
from pathlib import Path
from uuid import uuid4

# Add the root directory to the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from langchain_app.workflow import process_input
from memory.langgraph_memory import memory_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("memory_test")


async def simulate_conversation():
    """Simulate a conversation to test memory retention."""
    # Create a test user and conversation ID
    user_id = str(uuid4())
    conversation_id = str(uuid4())
    
    logger.info("==== First message ====")
    # First message
    result = await process_input(
        "Hello, I'd like to create an invoice",
        user_id=user_id,
        conversation_id=conversation_id
    )
    
    logger.info(f"Response: {result['content']}")
    conversation_id = result.get("conversation_id", conversation_id)
    logger.info(f"Conversation ID: {conversation_id}")
    
    logger.info("\n==== Second message ====")
    # Second message should have context from first
    result = await process_input(
        "It's for web development services.",
        user_id=user_id,
        conversation_id=conversation_id
    )
    
    logger.info(f"Response: {result['content']}")
    
    logger.info("\n==== Third message ====")
    # Third message builds on previous context
    result = await process_input(
        "The total amount is $500.",
        user_id=user_id,
        conversation_id=conversation_id
    )
    
    logger.info(f"Response: {result['content']}")
    
    logger.info("\n==== Memory Contents ====")
    # Check what's stored in memory
    try:
        memory_entry = memory_manager.retrieve(conversation_id)
        if memory_entry:
            logger.info(f"User ID: {memory_entry.user_id}")
            logger.info(f"Message count: {len(memory_entry.messages)}")
            for i, msg in enumerate(memory_entry.messages):
                logger.info(f"Message {i+1}: {msg['role']} - {msg['content'][:50]}...")
        else:
            logger.error(f"No memory entry found for conversation {conversation_id}")
    except Exception as e:
        logger.error(f"Error retrieving memory: {str(e)}")
    
    logger.info("\n==== Clearing Memory ====")
    # Clean up after test
    try:
        cleared = memory_manager.clear(conversation_id)
        logger.info(f"Memory cleared: {cleared}")
    except Exception as e:
        logger.error(f"Failed to clear memory for conversation {conversation_id}: {str(e)}")


if __name__ == "__main__":
    # Run the conversation simulation
    asyncio.run(simulate_conversation()) 