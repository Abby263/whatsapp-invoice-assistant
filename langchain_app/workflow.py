"""
LangGraph workflow for the WhatsApp Invoice Assistant.

This module defines the main LangGraph workflow by connecting the nodes with edges.
It also includes the entry point for running the workflow.
"""

import logging
import os
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel
# Import just StateGraph and END, avoid importing Checkpoint classes that might not be available
from langgraph.graph import StateGraph, END

# Only import MemorySaver if it's needed
try:
    from langgraph.checkpoint.memory import MemorySaver
except ImportError:
    # Provide a fallback or just log the issue
    logging.warning("MemorySaver not available in this version of langgraph")
    MemorySaver = None

# Create a stub for CheckpointAt if it's not available
try:
    from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointAt
except ImportError:
    # Create stub class for CheckpointAt
    class CheckpointAt:
        """Stub class for CheckpointAt."""
        pass

from langchain_app.state import WorkflowState, InputType, IntentType, UserInput, ConversationHistory
from langchain_app.nodes import (
    input_classifier,
    text_intent_classifier,
    file_validator,
    invoice_entity_extractor,
    data_extractor,
    sql_query_generator,
    response_formatter
)
from memory.langgraph_memory import memory_manager
from memory.context_manager import context_manager

logger = logging.getLogger(__name__)


def create_workflow_graph() -> StateGraph:
    """
    Creates the LangGraph workflow graph.
    
    Returns:
        The configured workflow graph
    """
    # Create a new graph
    workflow = StateGraph(WorkflowState)
    
    # Add nodes to the graph
    workflow.add_node("input_classifier", input_classifier)
    workflow.add_node("text_intent_classifier", text_intent_classifier)
    workflow.add_node("file_validator", file_validator)
    workflow.add_node("invoice_entity_extractor", invoice_entity_extractor)
    workflow.add_node("data_extractor", data_extractor)
    workflow.add_node("sql_query_generator", sql_query_generator)
    workflow.add_node("response_formatter", response_formatter)
    
    # Define the edges (conditional branches in the workflow)
    
    # Start with input classification
    workflow.set_entry_point("input_classifier")
    
    # After input classification, route based on input type
    workflow.add_conditional_edges(
        "input_classifier",
        lambda state: (
            # For text input, go to text intent classifier
            "text_intent_classifier" if state.input_type == InputType.TEXT
            # For file inputs, go to file validator
            else "file_validator"
        )
    )
    
    # After text intent classification, route based on intent
    workflow.add_conditional_edges(
        "text_intent_classifier",
        lambda state: (
            # For invoice queries, go to SQL query generator
            "sql_query_generator" if state.intent == IntentType.INVOICE_QUERY
            # For invoice creator intents, go to entity extractor
            else "invoice_entity_extractor" if state.intent == IntentType.INVOICE_CREATOR
            # For other intents, go straight to response formatter
            else "response_formatter"
        )
    )
    
    # After file validation, route based on validation result
    workflow.add_conditional_edges(
        "file_validator",
        lambda state: (
            # If file is a valid invoice, extract data
            "data_extractor" if state.file_validation and state.file_validation.is_valid
            # Otherwise, go straight to response formatter
            else "response_formatter"
        )
    )
    
    # All other nodes proceed to response formatter
    workflow.add_edge("invoice_entity_extractor", "response_formatter")
    workflow.add_edge("data_extractor", "response_formatter")
    workflow.add_edge("sql_query_generator", "response_formatter")
    
    # Response formatter is the final step
    workflow.add_edge("response_formatter", END)
    
    # Compile the graph
    workflow.compile()
    
    # Create visualization for debugging
    try:
        docs_dir = Path("docs")
        docs_dir.mkdir(exist_ok=True)
        
        # Save visualization to docs folder
        workflow.write_html(docs_dir / "workflow_graph.html")
        logger.info(f"Workflow graph visualization saved to {docs_dir / 'workflow_graph.html'}")
    except Exception as e:
        logger.warning(f"Could not save workflow visualization: {e}")
    
    return workflow


def get_workflow_graph() -> StateGraph:
    """
    Get the workflow graph for visualization.
    
    Returns:
        The StateGraph instance representing the workflow
    """
    return create_workflow_graph()


def create_workflow() -> Any:
    """
    Creates and configures the workflow with a checkpoint.
    
    Returns:
        The configured workflow that can be called
    """
    # Create the graph
    graph = create_workflow_graph()
    
    # Try to use MongoDB checkpoint if available
    try:
        from memory.langgraph_mongodb_checkpoint import create_mongodb_checkpoint_saver
        
        # Create a MongoDB checkpoint saver
        mongo_saver = create_mongodb_checkpoint_saver()
        
        if mongo_saver:
            logger.info("Using MongoDB checkpoint saver for LangGraph workflow")
            return graph.compile(checkpointer=mongo_saver)
    except ImportError:
        logger.warning("MongoDB checkpoint saver not available, using in-memory storage")
    except Exception as e:
        logger.error(f"Error initializing MongoDB checkpoint saver: {str(e)}")
        logger.warning("Falling back to no checkpointer")
    
    # Fallback to no checkpointer
    return graph.compile()


async def process_input(
    input_content: str, 
    file_path: Optional[str] = None, 
    file_name: Optional[str] = None, 
    mime_type: Optional[str] = None, 
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    user_id: Optional[Union[str, UUID]] = None,
    conversation_id: Optional[str] = None,
    db_session = None
) -> Dict[str, Any]:
    """
    Process an input through the workflow.
    
    Args:
        input_content: The text content or file content
        file_path: Optional path to an uploaded file
        file_name: Optional original filename
        mime_type: Optional MIME type of the file
        conversation_history: Optional history of previous conversations
        user_id: Optional user ID for persisting conversation history
        conversation_id: Optional conversation ID for continuing a conversation
        db_session: Optional database session for context persistence
        
    Returns:
        The workflow result
    """
    logger.info(f"Processing input: {'text input' if not file_path else f'file input ({file_name})'}")

    # Create the workflow
    workflow = create_workflow()
    
    # Determine content type
    content_type = InputType.TEXT if not file_path else InputType.UNKNOWN
    
    # Load conversation history from memory/db if user_id is provided
    history = ConversationHistory(messages=conversation_history or [])
    
    if user_id:
        try:
            # Get conversation history from context manager if available
            if db_session:
                # Get actual conversation ID and history from context manager
                conversation_id, history = await context_manager.load_state_with_history(
                    db_session, user_id, conversation_id
                )
                logger.info(f"Loaded conversation history for conversation {conversation_id}")
            # If no db_session but conversation_id is provided, try to get from memory
            elif conversation_id:
                memory_entry = memory_manager.retrieve(conversation_id)
                if memory_entry:
                    history = ConversationHistory(messages=memory_entry.messages)
                    logger.info(f"Loaded conversation history from memory for conversation {conversation_id}")
        except Exception as e:
            logger.warning(f"Error loading conversation history: {str(e)}")
            # Continue with empty history if there's an error
            pass
    
    # Create the initial state
    initial_state = WorkflowState(
        user_input=UserInput(
            content=input_content,
            content_type=content_type,
            file_path=file_path,
            file_name=file_name,
            mime_type=mime_type
        ),
        conversation_history=history
    )
    
    # Run the workflow
    try:
        result = workflow.invoke(initial_state)
        logger.info("Workflow completed successfully")
        
        # Store conversation in memory if user_id is provided
        if user_id and result:
            # Generate a conversation ID if not provided
            if not conversation_id:
                conversation_id = str(UUID.uuid4())
                
            # Store the result in memory
            memory_manager.store(conversation_id, str(user_id), result)
            logger.info(f"Stored conversation in memory with ID {conversation_id}")
            
            # Sync to database if session is provided
            if db_session:
                try:
                    await context_manager.sync_memory_to_db(db_session, conversation_id, user_id)
                    logger.info(f"Synced conversation {conversation_id} to database")
                except Exception as e:
                    logger.warning(f"Error syncing conversation to database: {str(e)}")
        
        # Extract the final response
        response_content = "I apologize, but I could not process your request."
        response_metadata = {}
        response_confidence = 0.0
        
        # LangGraph result is a dict, not a WorkflowState
        if result:
            # Extract the current_response if it exists
            current_response = result.get('current_response', {})
            if isinstance(current_response, dict):
                response_content = current_response.get('content', response_content)
                response_metadata = current_response.get('metadata', response_metadata)
                response_confidence = current_response.get('confidence', response_confidence)
            # If it's an object with attributes
            elif hasattr(current_response, 'content'):
                response_content = getattr(current_response, 'content', response_content)
                response_metadata = getattr(current_response, 'metadata', response_metadata)
                response_confidence = getattr(current_response, 'confidence', response_confidence)
        
        return {
            "content": response_content,
            "metadata": response_metadata,
            "confidence": response_confidence,
            "conversation_id": conversation_id
        }
            
    except Exception as e:
        logger.exception(f"Error running workflow: {str(e)}")
        return {
            "content": "I apologize, but an error occurred while processing your request.",
            "metadata": {"error": str(e)},
            "confidence": 0.0,
            "conversation_id": conversation_id
        }


def create_state(
    input_content: str, 
    content_type: InputType = InputType.TEXT,
    file_path: Optional[str] = None, 
    file_name: Optional[str] = None, 
    mime_type: Optional[str] = None, 
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    user_id: Optional[Union[str, UUID]] = None
) -> WorkflowState:
    """
    Create an initial state object for the workflow.
    
    Args:
        input_content: The text content or file content
        content_type: The type of input (text, file, etc.)
        file_path: Optional path to an uploaded file
        file_name: Optional original filename
        mime_type: Optional MIME type of the file
        conversation_history: Optional history of previous conversations
        user_id: Optional user ID for persisting conversation history
        
    Returns:
        The initial workflow state
    """
    logger.info(f"Creating initial state: {content_type}")
    
    # Create conversation history object
    history = ConversationHistory(messages=conversation_history or [])
    
    # Create the initial state
    initial_state = WorkflowState(
        user_input=UserInput(
            content=input_content,
            content_type=content_type,
            file_path=file_path,
            file_name=file_name,
            mime_type=mime_type
        ),
        conversation_history=history,
        user_id=user_id
    )
    
    return initial_state 