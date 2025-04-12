#!/usr/bin/env python

"""
Interactive end-to-end test for the WhatsApp Invoice Assistant.

This script provides an interactive test environment for the WhatsApp Invoice
Assistant, allowing manual input of text messages and files to test the
complete workflow from input to response.

Usage:
    python -m tests.interactive_test

Commands:
    /exit - Exit the interactive test
    /file <path> - Process a file at the given path
    /graph - Save the current workflow graph visualization
    /help - Display help information
"""

import asyncio
import logging
import os
import sys
import uuid
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
import time
import re

# Add project directory to path for proper imports
script_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(script_dir)
sys.path.insert(0, project_dir)

# Import logging utilities
from utils.logging import get_logs_directory

# Configure logging
logs_dir = get_logs_directory()
log_file = os.path.join(logs_dir, 'interactive_test.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file, mode='w')
    ]
)

logger = logging.getLogger("interactive_test")

# Import required modules
from langchain_app.api import process_text_message, process_file_message
# Load workflow module conditionally to handle import errors
try:
    from langchain_app.workflow import process_input, get_workflow_graph
except ImportError as e:
    logging.warning(f"Could not import from workflow module: {e}")
    # Create dummy functions for type checking
    async def process_input(*args, **kwargs):
        return {"message": "Workflow module import failed"}
    
    def get_workflow_graph():
        return None
from langchain_app.state import IntentType, FileType, WorkflowState
from database.connection import get_db, ensure_test_user_exists
from services.llm_factory import LLMFactory

# Set specific module log levels for detailed debugging
logging.getLogger('langchain_app.invoice_query_workflow').setLevel(logging.DEBUG)
logging.getLogger('agents.text_to_sql_conversion_agent').setLevel(logging.INFO)
logging.getLogger('agents.response_formatter').setLevel(logging.INFO)
logging.getLogger('database.connection').setLevel(logging.INFO)


async def handle_message(
    message: str, 
    user_id: str, 
    conversation_id: str, 
    is_file: bool = False,
    conversation_history: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Process a user message and return the response.
    
    Args:
        message: User's message text
        user_id: User's ID
        conversation_id: Conversation ID
        is_file: Whether the message is a file path
        conversation_history: Optional list of previous messages
        
    Returns:
        Dict containing the response
    """
    logger.info(f"=== PROCESSING USER MESSAGE ===")
    logger.info(f"Message: '{message}'")
    logger.info(f"User ID: {user_id}")
    logger.info(f"Conversation ID: {conversation_id}")
    
    # Log conversation history if provided
    if conversation_history:
        logger.info(f"Received conversation history with {len(conversation_history)} messages")
        for i, msg in enumerate(conversation_history):
            logger.debug(f"History item {i}: {msg.get('role')} - {msg.get('content', '')[:50]}...")
    else:
        logger.info("No conversation history provided")
        conversation_history = []
    
    if is_file or message.lower().startswith('/file '):
        # Handle file path commands
        file_path = message.split(' ', 1)[1] if message.lower().startswith('/file ') else message
        logger.info(f"Processing file: {file_path}")
        
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return {
                "message": f"Error: File not found: {file_path}"
            }
        
        try:
            # Get file details
            filename = os.path.basename(file_path)
            file_ext = os.path.splitext(filename)[1].lower()
            
            # Determine MIME type
            mime_type = "application/pdf" if file_ext == ".pdf" else \
                       "image/jpeg" if file_ext in [".jpg", ".jpeg"] else \
                       "image/png" if file_ext == ".png" else \
                       "application/octet-stream"
            
            logger.info(f"File MIME type: {mime_type}")
            
            # Set logging levels for better debugging
            logging.getLogger('agents.database_storage_agent').setLevel(logging.DEBUG)
            logging.getLogger('langchain_app.file_processing_workflow').setLevel(logging.DEBUG)
            
            # Log key information before processing
            logger.info(f"Sending file for processing: {filename}, type: {mime_type}, user_id: {user_id}")
            
            response = await process_file_message(
                file_path=file_path,
                file_name=filename,
                mime_type=mime_type,
                sender="test_user",
                user_id=user_id,
                conversation_id=conversation_id,
                conversation_history=conversation_history
            )
            
            logger.info(f"File processing complete")
            
            # Check response for database storage information
            if "metadata" in response:
                metadata = response.get("metadata", {})
                if "invoice_id" in metadata:
                    logger.info(f"✅ Invoice stored in database with ID: {metadata['invoice_id']}")
                    if "item_ids" in metadata:
                        logger.info(f"✅ Items stored: {len(metadata.get('item_ids', []))} items")
                else:
                    logger.warning("⚠️ No invoice_id in response, database storage may have failed")
            
            return response
            
        except Exception as e:
            logger.exception(f"Error processing file: {str(e)}")
            return {
                "message": f"Error processing file: {str(e)}"
            }
    else:
        # Handle text message
        logger.info(f"Processing text message")
        try:
            response = await process_text_message(
                message=message,
                sender="test_user",
                conversation_history=conversation_history,
                user_id=user_id,
                conversation_id=conversation_id
            )
            
            logger.info(f"Text processing complete")
            logger.debug(f"Response details: {json.dumps(response, default=str)[:200]}...")
            return response
            
        except Exception as e:
            logger.exception(f"Error processing message: {str(e)}")
            return {
                "message": f"Error processing message: {str(e)}"
            }


async def handle_command(command: str, user_id: str, conversation_id: str) -> bool:
    """
    Handle special commands.
    
    Args:
        command: The command text
        user_id: User ID
        conversation_id: Conversation ID
        
    Returns:
        True if the command was handled, False if it should be treated as a message
    """
    logger.debug(f"Checking if '{command}' is a command")
    if command.startswith('/'):
        parts = command.split(' ', 1)
        cmd = parts[0].lower()
        
        if cmd == '/help':
            logger.info("Displaying help command")
            print("\n=== Commands ===")
            print("/help - Show this help message")
            print("/exit - Exit the interactive test")
            print("/new - Start a new conversation")
            print("/file <path> - Process a file")
            print("\nYou can also type any message to interact with the assistant.\n")
            return True
            
        elif cmd == '/exit':
            logger.info("Exiting interactive test")
            print("\nGoodbye! Exiting interactive test.")
            return True
            
        elif cmd == '/new':
            logger.info("Starting new conversation")
            print("\nStarting a new conversation.")
            # Create a new conversation ID
            new_conversation_id = str(uuid.uuid4())
            print(f"New conversation ID: {new_conversation_id}")
            return True
            
        elif cmd == '/file' and len(parts) == 1:
            logger.warning("Missing file path")
            print("Error: Missing file path. Usage: /file <path>")
            return True
            
    return False


async def interactive_test():
    """Run the interactive test session."""
    # Use a fixed user_id for testing instead of generating a new one each time
    # Using integer 0 instead of UUID to match database schema
    user_id = 0
    conversation_id = str(uuid.uuid4())
    
    # Ensure the test user exists in the database
    ensure_test_user_exists()
    
    print("\n===== WhatsApp Invoice Assistant Interactive Test =====")
    print("Type /help for available commands")
    print(f"Testing with fixed user ID: {user_id}")
    print("Type your message or command below:")
    
    while True:
        try:
            # Get user input
            user_input = input("\n> ")
            
            # Handle exit command
            if user_input.lower() == '/exit':
                logger.info("User requested to exit")
                print("Goodbye!")
                break
                
            # Handle other commands
            is_command = await handle_command(user_input, user_id, conversation_id)
            if is_command:
                continue
                
            # Start timer for performance tracking
            start_time = datetime.now()
            
            # Process the message
            logger.info(f"Starting processing of message: '{user_input}'")
            response = await handle_message(user_input, user_id, conversation_id)
            
            # Calculate processing time
            end_time = datetime.now()
            processing_time = (end_time - start_time).total_seconds()
            
            # Display the response
            if response and "message" in response:
                print(f"\n{response['message']}")
                
                # Log additional response details
                logger.info(f"Response received in {processing_time:.2f} seconds")
                if "metadata" in response:
                    intent = response.get("metadata", {}).get("intent", "unknown")
                    logger.info(f"Detected intent: {intent}")
                    
                    if "query" in response.get("metadata", {}):
                        logger.info(f"SQL query: {response['metadata']['query']}")
                    
                    if "success" in response.get("metadata", {}):
                        logger.info(f"Query success: {response['metadata']['success']}")
                    
                    if "results_count" in response.get("metadata", {}):
                        logger.info(f"Results count: {response['metadata']['results_count']}")
            else:
                print("\nError: No valid response received.")
                logger.error(f"Invalid response format: {response}")
                
        except KeyboardInterrupt:
            logger.info("Test interrupted by user")
            print("\nInterrupted by user. Exiting...")
            break
            
        except Exception as e:
            logger.exception(f"Error in interactive test loop: {str(e)}")
            print(f"\nError: {str(e)}")


def guess_mime_type(file_path: str) -> str:
    """
    Guess the MIME type of a file based on its extension.
    
    Args:
        file_path: Path to the file
        
    Returns:
        The MIME type as a string
    """
    extension = os.path.splitext(file_path)[1].lower()
    
    mime_types = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".xls": "application/vnd.ms-excel",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".csv": "text/csv"
    }
    
    return mime_types.get(extension, "application/octet-stream")


def save_workflow_graph():
    """Save the workflow graph visualization."""
    # Create docs directory if it doesn't exist
    os.makedirs("docs", exist_ok=True)
    
    # Get the workflow graph
    graph = get_workflow_graph()
    
    # Create a visualization of the graph
    try:
        # Try using the .viz() method for LangGraph 0.0.x
        from langgraph.graph import StateGraph
        viz = graph.viz()
        viz.save("docs/workflow_graph.png")
        logger.info("Workflow graph saved to docs/workflow_graph.png")
    except Exception as e:
        # For newer LangGraph versions or other visualization approaches
        try:
            from langgraph.visualize import visualize
            visualize(graph).save("docs/workflow_graph.png")
            logger.info("Workflow graph saved to docs/workflow_graph.png using visualize()")
        except Exception as e2:
            logger.error(f"Error saving graph visualization: {e2}")
            print(f"\nError saving workflow graph: {e2}")


async def run_langgraph_studio():
    """Run the application with LangGraph Studio."""
    # Import the required LangGraph Studio function (only if available)
    try:
        from langgraph.studio import start_studio
        
        # Get the workflow graph
        graph = get_workflow_graph()
        
        # Start LangGraph Studio with the graph
        print("\nStarting LangGraph Studio server...")
        await start_studio(graph, host="localhost", port=8000)
        
    except ImportError:
        print("\nError: LangGraph Studio not available.")
        print("To use LangGraph Studio, install langgraph with:")
        print("  pip install langgraph[studio]")


async def test_specific_query(query: str, user_id: int = 0):
    """
    Test a specific query programmatically without interactive input.
    
    Args:
        query: The query text to test
        user_id: The user ID to use for testing (default: 0)
    """
    logging.info(f"=== PROGRAMMATIC QUERY TEST STARTED ===")
    logging.info(f"Testing query: '{query}' with user_id: {user_id}")
    
    # Ensure test user exists
    ensure_test_user_exists()
    
    from langchain_app.text_processing_workflow import process_text_message
    from langchain_app.api import process_text_message as api_process_text_message
    
    # Process the query
    try:
        logging.info(f"Processing query: '{query}'")
        
        # Use LangGraph to process the message
        start_time = time.time()
        response = await api_process_text_message(
            message=query, 
            sender=f"+1234567890",  # Mock sender number
            conversation_id=str(uuid.uuid4()),  # New conversation
            user_id=user_id,
            conversation_history=[]  # No history for this test
        )
        
        execution_time = time.time() - start_time
        logging.info(f"Response received in {execution_time:.2f} seconds")
        
        # Log and print the response
        logging.info(f"Response: {response}")
        print("\n=== TEST QUERY RESULT ===")
        print(f"Query: {query}")
        print(f"Response: {response.get('message', response.get('content', 'No content found'))}")
        print(f"Time: {execution_time:.2f} seconds")
        print("=========================")
        
        # Extract and log additional details from the response
        if response.get('metadata', {}).get('intent'):
            logging.info(f"Detected intent: {response['metadata']['intent']}")
        
        if 'sql_query' in str(response):
            sql_match = re.search(r'SQL query: (.*?)(?:\n|$)', str(response))
            if sql_match:
                logging.info(f"SQL query: {sql_match.group(1)}")
        
        if 'success' in str(response):
            success_match = re.search(r'success\': (True|False)', str(response))
            if success_match:
                logging.info(f"Query success: {success_match.group(1)}")
        
        if 'count' in str(response):
            count_match = re.search(r'count\': (\d+)', str(response))
            if count_match:
                logging.info(f"Results count: {count_match.group(1)}")
        
        return response
        
    except Exception as e:
        logging.exception(f"Error processing query: {str(e)}")
        print(f"\nError processing query: {str(e)}")
        
    logging.info(f"=== PROGRAMMATIC QUERY TEST COMPLETED ===")


if __name__ == "__main__":
    # If command-line arguments are provided, use them as test queries
    import sys
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        asyncio.run(test_specific_query(query))
    else:
        # Otherwise, run the interactive test
        try:
            asyncio.run(interactive_test())
        except KeyboardInterrupt:
            logging.info("Test interrupted by user")
            logging.info("=== INTERACTIVE TEST ENDED ===")
            print("\nInteractive test ended.")
        except Exception as e:
            logging.exception(f"Error in interactive test: {str(e)}")
            print(f"\nError: {str(e)}")
            logging.info("=== INTERACTIVE TEST ENDED WITH ERROR ===")
            print("Interactive test ended with error.") 