"""
Agent Memory Handler for the WhatsApp Invoice Assistant.

This module provides a wrapper around the memory system specifically for agents,
ensuring they have access to relevant conversation history for improved context awareness.
"""

import logging
from typing import Dict, List, Any, Optional, Union
from uuid import UUID
import json

from pydantic import BaseModel, Field

from memory.langgraph_memory import memory_manager, MemoryEntry
from memory.context_manager import context_manager
from langchain_app.state import ConversationHistory

logger = logging.getLogger(__name__)


class AgentMemory:
    """
    Memory handler specifically designed for agents.
    
    This class provides methods for agents to access and use conversation history,
    ensuring contextual awareness across interactions.
    """
    
    @staticmethod
    async def get_recent_messages(
        conversation_id: str, 
        max_messages: int = 10,
        include_system: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get the most recent messages from a conversation.
        
        Args:
            conversation_id: Conversation ID
            max_messages: Maximum number of messages to return
            include_system: Whether to include system messages
            
        Returns:
            List of recent messages
        """
        memory_entry = memory_manager.retrieve(conversation_id)
        if not memory_entry:
            logger.warning(f"No memory found for conversation {conversation_id}")
            return []
        
        # Filter system messages if needed
        messages = memory_entry.messages
        if not include_system:
            messages = [msg for msg in messages if msg.get('role') != 'system']
        
        # Return the most recent messages
        return messages[-max_messages:] if len(messages) > max_messages else messages
    
    @staticmethod
    async def get_formatted_history(
        conversation_id: str, 
        max_messages: int = 5
    ) -> str:
        """
        Get formatted conversation history for use in prompts.
        
        Args:
            conversation_id: Conversation ID
            max_messages: Maximum number of messages to include
            
        Returns:
            Formatted conversation history string
        """
        messages = await AgentMemory.get_recent_messages(
            conversation_id=conversation_id,
            max_messages=max_messages
        )
        
        if not messages:
            return "No previous conversation history."
        
        # Format the messages
        formatted = "Recent conversation history:\n"
        for msg in messages:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            
            if role == 'user':
                formatted += f"User: {content}\n"
            elif role == 'assistant':
                formatted += f"Assistant: {content}\n"
            else:
                formatted += f"{role.capitalize()}: {content}\n"
        
        return formatted
    
    @staticmethod
    async def extract_relevant_context(
        conversation_id: str,
        query: str,
        max_messages: int = 10
    ) -> str:
        """
        Extract relevant context from conversation history based on a query.
        
        Args:
            conversation_id: Conversation ID
            query: Query to use for relevance matching
            max_messages: Maximum number of messages to consider
            
        Returns:
            Relevant context as a string
        """
        # Get recent messages
        messages = await AgentMemory.get_recent_messages(
            conversation_id=conversation_id,
            max_messages=max_messages
        )
        
        if not messages:
            return ""
        
        # For now, just return a simple combination of all messages
        # TODO: Implement semantic filtering using vector embeddings
        
        # Format the messages
        context = ""
        for msg in messages:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            
            # Only include messages with content
            if content:
                if role == 'user':
                    context += f"User said: {content}\n"
                elif role == 'assistant':
                    context += f"Assistant responded: {content}\n"
        
        return context
    
    @staticmethod
    async def add_context_to_prompt(
        prompt: str,
        conversation_id: Optional[str],
        query: Optional[str] = None,
        max_messages: int = 5
    ) -> str:
        """
        Add conversation context to a prompt.
        
        Args:
            prompt: Base prompt
            conversation_id: Conversation ID
            query: Optional query to use for relevance matching
            max_messages: Maximum number of messages to include
            
        Returns:
            Enhanced prompt with conversation context
        """
        if not conversation_id:
            return prompt
        
        # Get formatted history
        history = await AgentMemory.get_formatted_history(
            conversation_id=conversation_id,
            max_messages=max_messages
        )
        
        # Insert history before the last instruction in the prompt
        if "Previous conversation:" in prompt:
            # Replace existing history placeholder
            return prompt.replace("Previous conversation:", f"Previous conversation:\n{history}")
        else:
            # Add history before the last section
            sections = prompt.split("\n\n")
            
            if len(sections) > 1:
                # Insert before the last section
                sections.insert(-1, f"Previous conversation:\n{history}")
                return "\n\n".join(sections)
            else:
                # Just append to the end
                return f"{prompt}\n\nPrevious conversation:\n{history}"
    
    @staticmethod
    async def update_memory_with_message(
        conversation_id: str,
        user_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Add a new message to memory.
        
        Args:
            conversation_id: Conversation ID
            user_id: User ID
            role: Message role (user, assistant, system)
            content: Message content
            metadata: Optional message metadata
        """
        # Get memory entry or create if it doesn't exist
        memory_entry = memory_manager.retrieve(conversation_id)
        if not memory_entry:
            memory_entry = MemoryEntry(
                conversation_id=conversation_id,
                user_id=user_id,
                messages=[],
                metadata={}
            )
        
        # Add message
        message = {
            "role": role,
            "content": content,
            "timestamp": None,  # Will be filled by store
            "metadata": metadata or {}
        }
        
        memory_entry.messages.append(message)
        
        # Update memory
        memory_manager.store(conversation_id, user_id, memory_entry)
        logger.debug(f"Added message from {role} to memory for conversation {conversation_id}")


# Create a singleton instance for use throughout the application
agent_memory = AgentMemory() 