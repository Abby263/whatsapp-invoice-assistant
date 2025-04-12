"""
Flask UI for testing the WhatsApp Invoice Assistant.

This is a simple web interface for testing the assistant without needing a real WhatsApp account.
It allows sending text messages and uploading files to simulate interactions with the assistant.
"""

import os
import json
import asyncio
import logging
import sys
import argparse
from pathlib import Path
from contextlib import asynccontextmanager, contextmanager
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import uuid
from datetime import datetime
from sqlalchemy import text
from typing import Dict, Any, Optional, List, Tuple
import threading
import traceback

# Add the project root directory to the path for proper imports
app_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(app_dir)
sys.path.insert(0, project_dir)

# Import logging utilities
from utils.logging import get_logs_directory

# Load environment variables from .env file
load_dotenv()

# Ensure AWS credentials are available in environment
if os.path.exists(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')):
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'), 'r') as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value

# Set event loop policy to WindowsSelectorEventLoopPolicy on Windows to avoid 'Event loop is closed' errors
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Configure logging
logs_dir = get_logs_directory()
log_file = os.path.join(logs_dir, 'ui_test.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file, mode='w')
    ]
)

logger = logging.getLogger("ui_test")

# Apply patches before importing LangGraph
try:
    import patches
    logging.info("Applied compatibility patches")
except Exception as e:
    logging.error(f"Error applying patches: {e}")

# Import the interactive test module
from tests.interactive_test import handle_message, handle_command, ensure_test_user_exists

# Import constants
from constants.ui_config import DEFAULT_WHATSAPP_NUMBER, DEFAULT_CONVERSATION_ID, MAX_CHAT_HISTORY, MAX_CONTENT_LENGTH, UPLOAD_FOLDER, VECTOR_EXTENSION_NAME, DEFAULT_VECTOR_DIMENSION

# Import application modules
from langchain_app.api import process_text_message, process_file_message
from memory.memory_manager import get_memory, set_memory_config
from database import database_utils
from scripts.update_embeddings import run_embeddings_update

# Helper function to properly handle async operations in Flask
@asynccontextmanager
async def managed_event_loop():
    """Context manager for properly handling async operations and cleanup in Flask."""
    # Use Windows selector event loop policy on Windows
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        yield loop
    finally:
        # Get all tasks that are still running
        pending_tasks = asyncio.all_tasks(loop)
        if pending_tasks:
            # Create a future that will mark all tasks as done
            cleanup_future = asyncio.gather(*pending_tasks, return_exceptions=True)
            try:
                loop.run_until_complete(cleanup_future)
            except Exception as e:
                logger.warning(f"Error cleaning up pending tasks: {str(e)}")
            
        # Close all remaining resources
        try:
            # Use an approach that doesn't try to run the coroutine directly
            if hasattr(loop, "shutdown_asyncgens") and callable(loop.shutdown_asyncgens):
                if sys.version_info >= (3, 10):
                    # Python 3.10+ approach
                    # Create and run a separate task for shutdown_asyncgens
                    shutdown_task = loop.create_task(loop.shutdown_asyncgens())
                    loop.run_until_complete(shutdown_task)
                else:
                    # For older Python versions
                    shutdown_coro = loop.shutdown_asyncgens()
                    loop.run_until_complete(shutdown_coro)
        except Exception as e:
            logger.warning(f"Error shutting down async generators: {str(e)}")
        
        # Now it's safe to close the loop
        try:
            loop.close()
        except Exception as e:
            logger.warning(f"Error closing event loop: {str(e)}")

def run_async(async_func, *args, **kwargs):
    """Run an async function safely within a synchronous Flask route."""
    # Set environment variable to force HTTPX to close connections
    # This helps prevent 'Event loop is closed' errors
    os.environ["HTTPX_CLOSE_CONNECTIONS"] = "1"
    
    current_loop = None
    try:
        # Check if there's already a running event loop
        try:
            current_loop = asyncio.get_event_loop()
            if current_loop.is_running():
                logger.debug("Using existing running event loop")
                
                # Create a new loop for this task to avoid nested loop errors
                task_loop = asyncio.new_event_loop()
                try:
                    # Run our function in the new loop
                    async def isolated_task():
                        return await async_func(*args, **kwargs)
                    
                    return task_loop.run_until_complete(isolated_task())
                finally:
                    # Clean up our isolated loop
                    try:
                        if hasattr(task_loop, "shutdown_asyncgens") and callable(task_loop.shutdown_asyncgens):
                            shutdown_coro = task_loop.shutdown_asyncgens()
                            task_loop.run_until_complete(shutdown_coro)
                    except Exception as e:
                        logger.debug(f"Error shutting down async generators in task loop: {str(e)}")
                    task_loop.close()
        except RuntimeError:
            # No event loop exists yet, we'll create one below
            logger.debug("No existing event loop found")
            pass
        
        # Standard case: Create a new managed event loop
        async def wrapper():
            async with managed_event_loop() as loop:
                return await async_func(*args, **kwargs)
        
        try:
            return asyncio.run(wrapper())
        except RuntimeError as e:
            if "Event loop is closed" in str(e) or "cannot schedule new futures" in str(e):
                logger.warning("Event loop closed error caught, using new isolated loop")
                # Create and use a completely new event loop
                isolated_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(isolated_loop)
                try:
                    # Run directly without wrapper to avoid nested context issues
                    coro = async_func(*args, **kwargs)
                    return isolated_loop.run_until_complete(coro)
                finally:
                    try:
                        tasks = asyncio.all_tasks(isolated_loop)
                        if tasks:
                            isolated_loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                    except Exception as e:
                        logger.debug(f"Error cleaning up tasks in isolated loop: {str(e)}")
                    
                    try:
                        if hasattr(isolated_loop, "shutdown_asyncgens"):
                            shutdown_task = asyncio.ensure_future(isolated_loop.shutdown_asyncgens(), loop=isolated_loop)
                            isolated_loop.run_until_complete(shutdown_task)
                    except Exception as e:
                        logger.debug(f"Error shutting down async generators in isolated loop: {str(e)}")
                    
                    isolated_loop.close()
            else:
                raise
        except Exception as e:
            logger.exception(f"Unhandled error in run_async: {str(e)}")
            raise
    except Exception as e:
        logger.exception(f"Outer error in run_async: {str(e)}")
        raise

# Create the Flask app
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH  # 16 MB max upload

# Create uploads folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Global variables
CONVERSATION_ID = DEFAULT_CONVERSATION_ID  # From constants
WHATSAPP_NUMBER = DEFAULT_WHATSAPP_NUMBER  # From constants
USER_ID = None  # Will be fetched based on WhatsApp number

# Global variable to store agent traces
agent_traces = []

# Global variable to store conversation history
CONVERSATION_HISTORY = []

# Function to get user ID from WhatsApp number
async def get_user_id_from_whatsapp(whatsapp_number: str) -> int:
    """Get user ID from WhatsApp number or create if doesn't exist."""
    from database.connection import get_db
    
    @contextmanager
    def get_session():
        db = next(get_db())
        try:
            yield db
        finally:
            db.close()
    
    # First try to find existing user
    with get_session() as db:
        query = text("SELECT id FROM users WHERE whatsapp_number = :whatsapp_number LIMIT 1")
        result = db.execute(query, {"whatsapp_number": whatsapp_number}).fetchone()
        
        if result:
            return result[0]
        
        # If user doesn't exist, create a new one
        # This will likely be handled by ensure_test_user_exists, but as a fallback
        logger.info(f"User with WhatsApp number {whatsapp_number} not found, creating new user")
        insert_query = text("""
            INSERT INTO users (name, email, whatsapp_number, created_at, updated_at) 
            VALUES (:name, :email, :whatsapp_number, NOW(), NOW())
            RETURNING id
        """)
        
        result = db.execute(
            insert_query, 
            {
                "name": f"Test User {whatsapp_number}", 
                "email": f"test_{whatsapp_number.replace('+', '')}@example.com",
                "whatsapp_number": whatsapp_number
            }
        ).fetchone()
        
        db.commit()
        return result[0] if result else 0

# Get all users from database
async def get_all_users() -> List[Dict[str, Any]]:
    """Get all users from database."""
    from database.connection import get_db
    
    @contextmanager
    def get_session():
        db = next(get_db())
        try:
            yield db
        finally:
            db.close()
    
    with get_session() as db:
        query = text("SELECT id, name, whatsapp_number FROM users ORDER BY id")
        results = db.execute(query).fetchall()
        
        # Convert to list of dicts
        users = [{"id": row[0], "name": row[1], "whatsapp_number": row[2]} for row in results]
        return users

# Create a new user in the database
async def create_new_user(whatsapp_number: str, name: str = None, email: str = None) -> Dict[str, Any]:
    """Create a new user in the database.
    
    Args:
        whatsapp_number: The WhatsApp number for the user
        name: The name of the user (optional)
        email: The email of the user (optional)
        
    Returns:
        A dictionary with the user information
    """
    from database.connection import get_db
    import uuid
    
    @contextmanager
    def get_session():
        db = next(get_db())
        try:
            yield db
        finally:
            db.close()
    
    with get_session() as db:
        # Check if user with this WhatsApp number already exists
        check_query = text("SELECT id FROM users WHERE whatsapp_number = :whatsapp_number LIMIT 1")
        existing_user = db.execute(check_query, {"whatsapp_number": whatsapp_number}).fetchone()
        
        if existing_user:
            logger.warning(f"User with WhatsApp number {whatsapp_number} already exists")
            # Return existing user information
            user_query = text("SELECT id, name, email, whatsapp_number, created_at FROM users WHERE id = :id")
            user_result = db.execute(user_query, {"id": existing_user[0]}).fetchone()
            
            return {
                "id": user_result[0],
                "name": user_result[1],
                "email": user_result[2],
                "whatsapp_number": user_result[3],
                "created_at": user_result[4].isoformat() if user_result[4] else None,
                "is_new": False
            }
        
        # Prepare user data
        user_id = str(uuid.uuid4())
        user_name = name or f"User {whatsapp_number}"
        user_email = email or f"user_{whatsapp_number.replace('+', '')}@example.com"
        
        # Insert new user
        insert_query = text("""
            INSERT INTO users (id, name, email, whatsapp_number, created_at, updated_at, is_active) 
            VALUES (:id, :name, :email, :whatsapp_number, NOW(), NOW(), TRUE)
            RETURNING id, name, email, whatsapp_number, created_at
        """)
        
        result = db.execute(
            insert_query, 
            {
                "id": user_id,
                "name": user_name, 
                "email": user_email,
                "whatsapp_number": whatsapp_number
            }
        ).fetchone()
        
        db.commit()
        
        if result:
            logger.info(f"Created new user with ID {result[0]} for WhatsApp number {whatsapp_number}")
            return {
                "id": result[0],
                "name": result[1],
                "email": result[2],
                "whatsapp_number": result[3],
                "created_at": result[4].isoformat() if result[4] else None,
                "is_new": True
            }
        
        return None

@app.route('/')
def home():
    """Render the home page"""
    return render_template('index.html')

@app.route('/api/message', methods=['POST'])
def api_message():
    try:
        global CONVERSATION_ID, CONVERSATION_HISTORY, USER_ID, WHATSAPP_NUMBER
        
        data = request.json
        message = data.get('message')
        is_file = data.get('is_file', False)
        
        # Get WhatsApp number from request or use global
        whatsapp_number = data.get('whatsapp_number', WHATSAPP_NUMBER)
        
        # Update global WhatsApp number if it changed
        if whatsapp_number != WHATSAPP_NUMBER:
            WHATSAPP_NUMBER = whatsapp_number
            # Get user ID for this WhatsApp number
            USER_ID = run_async(lambda: get_user_id_from_whatsapp(WHATSAPP_NUMBER))
        
        logger.info(f"Processing message from WhatsApp number: {WHATSAPP_NUMBER}")
        
        if not message:
                return jsonify({
                "status": "error",
                "message": "No message provided"
            }), 400
            
        if is_file:
            # Handle file message (you can add logic here if needed)
            pass
            
        # Process the message using our test handler
        # Pass the current conversation history to maintain context
        
        # Log the conversation history we're passing
        logger.info(f"Passing conversation history with {len(CONVERSATION_HISTORY)} messages")
        if CONVERSATION_HISTORY:
            for i, msg in enumerate(CONVERSATION_HISTORY):
                logger.info(f"History item {i}: {msg['role']} - {msg['content'][:30]}...")
                
        # Process message with history
        result = run_async(
            handle_message, 
            message, 
            USER_ID, 
            CONVERSATION_ID,
            is_file=is_file,
            conversation_history=CONVERSATION_HISTORY
        )
        
        # Update conversation history with the new exchange
        CONVERSATION_HISTORY.append({"role": "user", "content": message})
        CONVERSATION_HISTORY.append({"role": "assistant", "content": result.get("message", "")})
        
        # Keep only the last MAX_CHAT_HISTORY messages to avoid context getting too long
        if len(CONVERSATION_HISTORY) > MAX_CHAT_HISTORY:
            CONVERSATION_HISTORY = CONVERSATION_HISTORY[-MAX_CHAT_HISTORY:]
            
        logger.info(f"Updated conversation history now has {len(CONVERSATION_HISTORY)} messages")
        
        # Add WhatsApp number and user ID to the result
        result["whatsapp_number"] = WHATSAPP_NUMBER
        result["user_id"] = USER_ID
        
        return jsonify(result)
        
    except Exception as e:
        logger.exception(f"Error processing message: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Error processing message: {str(e)}"
        }), 500

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Handle file uploads"""
    try:
        global WHATSAPP_NUMBER, USER_ID
        
        if 'file' not in request.files:
            return jsonify({'status': 'error', 'message': 'No file part'}), 400
            
        file = request.files['file']
        
        # Handle WhatsApp number if provided
        whatsapp_number = request.form.get('whatsapp_number', WHATSAPP_NUMBER)
        
        # Update global WhatsApp number if it changed
        if whatsapp_number != WHATSAPP_NUMBER:
            WHATSAPP_NUMBER = whatsapp_number
            # Get user ID for this WhatsApp number
            USER_ID = run_async(lambda: get_user_id_from_whatsapp(WHATSAPP_NUMBER))
        
        # Log the WhatsApp number for context in log analysis
        logger.info(f"Processing file upload from WhatsApp number: {WHATSAPP_NUMBER}")
        
        if file.filename == '':
            return jsonify({'status': 'error', 'message': 'No file selected'}), 400
            
        if file:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            # Determine MIME type
            file_ext = os.path.splitext(filename)[1].lower()
            mime_type = "application/pdf" if file_ext == ".pdf" else \
                        "image/jpeg" if file_ext in [".jpg", ".jpeg"] else \
                        "image/png" if file_ext == ".png" else \
                        "application/octet-stream"
                        
            # Process the file using the /file command with improved async handling
            command = f"/file {file_path}"
            response = run_async(handle_message, command, USER_ID, CONVERSATION_ID)
            
            return jsonify({
                'status': 'success',
                'message': response.get('message', 'File processed'),
                'metadata': response.get('metadata', {}),
                'filename': filename,
                'type': 'file',
                'whatsapp_number': WHATSAPP_NUMBER,
                'user_id': USER_ID
            })
    
    except Exception as e:
        logger.exception(f"Error uploading file: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f"Error: {str(e)}",
            'type': 'error'
        }), 500

@app.route('/api/agent-flow')
def get_agent_flow():
    """Return the agent flow data for visualization based on logs analysis"""
    try:
        # Get the last processed intent from logs
        import re
        import os
        from collections import defaultdict
        
        # Read from log file
        log_file = os.path.join(project_dir, 'ui_test.log')
        
        if not os.path.exists(log_file):
            return jsonify({
                'status': 'error',
                'message': 'Log file not found'
            }), 404
            
        # Define regex patterns for workflow tracking
        intent_pattern = re.compile(r'(intent|intent_type)[:|=]\s*[\'"]?([a-z_]+)[\'"]?', re.IGNORECASE)
        workflow_step_pattern = re.compile(r'=== ([\w\s]+) (STARTED|PROCESSING|COMPLETED|FINISHED) ===', re.IGNORECASE)
        agent_pattern = re.compile(r'([\w]+Agent|[\w]+Router|[\w]+Classifier) (processing|completed)', re.IGNORECASE)
        rag_pattern = re.compile(r'\[WORKFLOW STEP\] (Starting RAG process|RAG search completed|Vector search found)', re.IGNORECASE)
        s3_url_pattern = re.compile(r's3_url[:|=]\s*[\'"]?(https?://[^\'"]+)[\'"]?', re.IGNORECASE)
        s3_key_pattern = re.compile(r'file_key[:|=]\s*[\'"]?([^\'"]+)[\'"]?', re.IGNORECASE)
        
        # Track workflow steps, intent, and S3 storage info
        workflow_steps = []
        current_intent = "unknown"
        s3_storage_info = {}
        user_id = "0"
        whatsapp_number = "+1234567890"
        last_timestamp = None
        last_transaction_steps = []
        
        # Find the most recent workflow execution by tracking timestamps
        transaction_steps = defaultdict(list)
        transactions = []
        transaction_start_pattern = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - .* - .*message from WhatsApp number: ([+\d]+)', re.IGNORECASE)
        
        with open(log_file, 'r') as f:
            for line in f:
                # Track transaction boundaries based on message processing
                tx_match = transaction_start_pattern.search(line)
                if tx_match:
                    timestamp = tx_match.group(1)
                    whatsapp_num = tx_match.group(2)
                    transactions.append((timestamp, whatsapp_num))
                    last_timestamp = timestamp
                
                # Extract steps for the current transaction
                if last_timestamp:
                    # Extract workflow steps
                    workflow_match = workflow_step_pattern.search(line)
                    if workflow_match:
                        step_name = workflow_match.group(1).strip()
                        transaction_steps[last_timestamp].append(step_name)
                    
                    # Extract agent steps
                    agent_match = agent_pattern.search(line)
                    if agent_match:
                        agent_name = agent_match.group(1).strip()
                        transaction_steps[last_timestamp].append(agent_name)
                    
                    # Extract RAG steps
                    rag_match = rag_pattern.search(line)
                    if rag_match:
                        transaction_steps[last_timestamp].append("InvoiceRAGAgent")
                
                # Extract intent
                intent_match = intent_pattern.search(line)
                if intent_match:
                    current_intent = intent_match.group(2).strip()
                
                # Extract S3 storage information
                s3_url_match = s3_url_pattern.search(line)
                if s3_url_match:
                    s3_storage_info['url'] = s3_url_match.group(1)
                
                s3_key_match = s3_key_pattern.search(line)
                if s3_key_match:
                    s3_storage_info['file_key'] = s3_key_match.group(1)
                
                # Extract user ID
                user_id_match = re.search(r'user_id[:|=]\s*(\d+)', line, re.IGNORECASE)
                if user_id_match:
                    user_id = user_id_match.group(1)
                
                # Extract WhatsApp number
                whatsapp_match = re.search(r'whatsapp[:|=]\s*(\+\d+)', line, re.IGNORECASE)
                if whatsapp_match:
                    whatsapp_number = whatsapp_match.group(1)
        
        # Get the most recent transaction steps
        if transactions:
            sorted_transactions = sorted(transactions, key=lambda x: x[0], reverse=True)
            last_timestamp = sorted_transactions[0][0]
            last_transaction_steps = transaction_steps[last_timestamp]
        
        # Process the raw steps to create a normalized workflow
        if last_transaction_steps:
            # Remove duplicates while preserving order
            seen = set()
            workflow_steps = []
            for step in last_transaction_steps:
                normalized_step = step
                
                # Map various step names to normalized names
                step_mapping = {
                    'INPUT': 'InputProcessor',
                    'TEXT INTENT CLASSIFICATION': 'TextIntentClassifier',
                    'TEXT INTENT CLASSIFIER': 'TextIntentClassifier',
                    'INVOICE QUERY': 'InvoiceQueryProcessor',
                    'INVOICE CREATION': 'InvoiceCreator',
                    'TEXT PROCESSING': 'TextProcessor',
                    'TEXT TO SQL CONVERSION': 'TextToSqlConverter',
                    'FILE PROCESSING': 'FileProcessor',
                    'FILE VALIDATOR': 'FileValidator',
                    'DATA EXTRACTION': 'DataExtractor',
                    'DATABASE STORAGE': 'DatabaseStorageAgent',
                    'RESPONSE FORMATTING': 'ResponseFormatter',
                    'RESPONSE FORMATTER': 'ResponseFormatter',
                    'PROCESSING INVOICE CREATION': 'InvoiceCreator',
                    'EXTRACTING INVOICE ENTITIES': 'EntityExtractor',
                    'RAG': 'InvoiceRagAgent',
                    'VECTOR SEARCH': 'VectorSearchAgent',
                    'VECTOR SIMILARITY': 'VectorSimilarityAgent',
                    'INVOICERAGAGENT': 'InvoiceRagAgent'
                }
                
                # Check if the step matches one of our known steps
                for key, value in step_mapping.items():
                    if key.lower() in step.lower():
                        normalized_step = value
                        break
                
                # Use the agent name directly if it matches a pattern
                if 'Agent' in step or 'Router' in step or 'Classifier' in step:
                    normalized_step = step
                
                if normalized_step.lower() not in seen:
                    workflow_steps.append(normalized_step)
                    seen.add(normalized_step.lower())
        
        # If we still don't have steps, provide defaults based on intent
        if not workflow_steps:
            if current_intent == "invoice_query":
                workflow_steps = ['InputProcessor', 'TextIntentClassifier', 'TextToSqlConverter', 'DatabaseQuerier', 'InvoiceRagAgent', 'ResponseFormatter']
            elif current_intent == "invoice_creator":
                workflow_steps = ['InputProcessor', 'TextIntentClassifier', 'EntityExtractor', 'InvoiceCreator', 'ResponseFormatter']
            elif current_intent == "greeting":
                workflow_steps = ['InputProcessor', 'TextIntentClassifier', 'GreetingHandler', 'ResponseFormatter']
            else:
                workflow_steps = ['InputProcessor', 'TextIntentClassifier', 'ResponseFormatter']
        
        # Build edges for visualization
        edges = []
        for i in range(len(workflow_steps) - 1):
            edges.append({
                'from': workflow_steps[i],
                'to': workflow_steps[i + 1]
            })
        
        return jsonify({
            'status': 'success',
            'nodes': workflow_steps,
            'edges': edges,
            'intent': current_intent,
            'user_id': user_id,
            'whatsapp_number': whatsapp_number,
            's3_storage': s3_storage_info
        })
    except Exception as e:
        logger.exception(f"Error generating agent flow visualization: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f"Error generating agent flow: {str(e)}"
        }), 500

@app.route('/api/db-status')
def get_db_status():
    """Return the current database status including size information"""
    try:
        global USER_ID
        
        # Specific user ID for which to get invoice count
        user_id = request.args.get('user_id', USER_ID) if USER_ID is not None else None
        
        # Define an async function to query the database
        async def query_db():
            from database.connection import get_db, check_pgvector_extension
            from constants.ui_config import VECTOR_EXTENSION_NAME, DEFAULT_VECTOR_DIMENSION
            from sqlalchemy import text
            from contextlib import contextmanager
            
            @contextmanager
            def get_session():
                db = next(get_db())
                try:
                    yield db
                finally:
                    db.close()
            
            # Get counts from database
            with get_session() as db:
                # Count all invoices
                invoice_result = db.execute(text("SELECT COUNT(*) FROM invoices")).scalar()
                
                # Count user-specific invoices
                user_invoice_result = 0
                if user_id is not None:
                    user_invoice_query = text("SELECT COUNT(*) FROM invoices WHERE user_id = :user_id")
                    user_invoice_result = db.execute(user_invoice_query, {"user_id": user_id}).scalar()
                
                # Count all items
                item_result = db.execute(text("SELECT COUNT(*) FROM items")).scalar()
                
                # Count user-specific items
                user_items_result = 0
                if user_id is not None:
                    user_items_query = text("""
                        SELECT COUNT(*) FROM items i
                        JOIN invoices inv ON i.invoice_id = inv.id
                        WHERE inv.user_id = :user_id
                    """)
                    user_items_result = db.execute(user_items_query, {"user_id": user_id}).scalar()
                
                # Get database connection details
                db_details = {
                    "postgresql": {
                        "host": os.environ.get("DATABASE_URL", "").split("@")[1].split("/")[0].split(":")[0] if "@" in os.environ.get("DATABASE_URL", "") else "unknown",
                        "port": os.environ.get("DATABASE_URL", "").split("@")[1].split("/")[0].split(":")[1] if "@" in os.environ.get("DATABASE_URL", "") and ":" in os.environ.get("DATABASE_URL", "").split("@")[1].split("/")[0] else "unknown",
                        "user": os.environ.get("DATABASE_URL", "").split("://")[1].split(":")[0] if "://" in os.environ.get("DATABASE_URL", "") else "unknown",
                        "database": os.environ.get("DATABASE_URL", "").split("/")[-1] if "/" in os.environ.get("DATABASE_URL", "") else "unknown"
                    },
                    "mongodb": {
                        "uri": os.environ.get("MONGODB_URI", "unknown"),
                        "host": os.environ.get("MONGODB_URI", "").split("@")[1].split("/")[0] if "@" in os.environ.get("MONGODB_URI", "") else os.environ.get("MONGODB_URI", "").split("://")[1].split("/")[0] if "://" in os.environ.get("MONGODB_URI", "") else "unknown",
                        "port": os.environ.get("MONGODB_URI", "").split(":")[-1].split("/")[0] if ":" in os.environ.get("MONGODB_URI", "") else "unknown",
                        "database": os.environ.get("MONGODB_URI", "").split("/")[-1] if "/" in os.environ.get("MONGODB_URI", "") else "unknown"
                    }
                }
                
                # Get database size information
                try:
                    # Get total database size
                    db_size_query = text("""
                    SELECT pg_size_pretty(pg_database_size(current_database())) as db_size,
                           pg_size_pretty(sum(pg_total_relation_size(relid))) as tables_size
                    FROM pg_catalog.pg_statio_user_tables
                    """)
                    size_result = db.execute(db_size_query).first()
                    
                    # Get table sizes
                    table_size_query = text("""
                    SELECT relname as table_name, 
                           pg_size_pretty(pg_total_relation_size(relid)) as total_size,
                           pg_total_relation_size(relid) as size_bytes
                    FROM pg_catalog.pg_statio_user_tables
                    ORDER BY pg_total_relation_size(relid) DESC
                    LIMIT 5
                    """)
                    table_sizes = []
                    for row in db.execute(table_size_query):
                        table_sizes.append({
                            'name': row[0],
                            'size': row[1],
                            'bytes': row[2]
                        })
                    
                    size_info = {
                        'total_size': size_result[0] if size_result else "Unknown",
                        'tables_size': size_result[1] if size_result else "Unknown",
                        'top_tables': table_sizes
                    }
                except Exception as e:
                    logger.warning(f"Error getting database size: {str(e)}")
                    size_info = {
                        'total_size': "Error",
                        'error': str(e)
                    }
                
                # Check pgvector status
                try:
                    # First check if the extension is installed
                    pgvector_installed = check_pgvector_extension()
                    
                    if pgvector_installed:
                        # Check for items with embeddings to demonstrate functionality
                        with_embeddings_query = text("SELECT COUNT(*) FROM items WHERE description_embedding IS NOT NULL")
                        with_embeddings = db.execute(with_embeddings_query).scalar() or 0
                        
                        without_embeddings_query = text("SELECT COUNT(*) FROM items WHERE description_embedding IS NULL AND description IS NOT NULL")
                        without_embeddings = db.execute(without_embeddings_query).scalar() or 0
                        
                        # Also check invoice embeddings
                        invoice_embeddings_query = text("SELECT COUNT(*) FROM invoice_embeddings")
                        invoice_embeddings = db.execute(invoice_embeddings_query).scalar() or 0
                        
                        vector_info = {
                            'installed': True,
                            'extension_name': VECTOR_EXTENSION_NAME,
                            'with_embeddings': with_embeddings,
                            'without_embeddings': without_embeddings,
                            'invoice_embeddings': invoice_embeddings,
                            'embedding_dimension': DEFAULT_VECTOR_DIMENSION
                        }
                        
                        if with_embeddings > 0:
                            # Try to get embedding dimension from an actual item
                            try:
                                # First try vector_dims if available
                                try:
                                    dim_query = text("SELECT vector_dims(description_embedding) FROM items WHERE description_embedding IS NOT NULL LIMIT 1")
                                    dimension = db.execute(dim_query).scalar()
                                    if dimension:
                                        vector_info['embedding_dimension'] = dimension
                                except Exception:
                                    # Try length function
                                    try:
                                        dim_query = text("SELECT length(description_embedding) FROM items WHERE description_embedding IS NOT NULL LIMIT 1")
                                        dimension = db.execute(dim_query).scalar()
                                        if dimension:
                                            vector_info['embedding_dimension'] = dimension
                                    except Exception as e:
                                        logger.warning(f"Error determining embedding dimension: {str(e)}")
                            except Exception as e:
                                logger.warning(f"Error determining embedding dimension: {str(e)}")
                    else:
                        vector_info = {
                            'installed': False,
                            'extension_name': VECTOR_EXTENSION_NAME
                        }
                except Exception as e:
                    logger.warning(f"Error checking vector status: {str(e)}")
                    vector_info = {
                        'installed': False,
                        'error': str(e)
                    }
                
            return {
                'invoices': invoice_result or 0,
                'user_invoices': user_invoice_result or 0,
                'items': item_result or 0,
                'user_items': user_items_result or 0,
                'size_info': size_info,
                'vector_info': vector_info,
                'db_details': db_details
            }
        
        # Use our improved async handling
        db_status = run_async(lambda: query_db())
        
        return jsonify({
            'status': 'success',
            'counts': {
                'invoices': {
                    'total': db_status['invoices'],
                    'user_specific': db_status.get('user_invoices', 0)
                },
                'items': db_status['items'],
                'user_items': db_status.get('user_items', 0)
            },
            'size_info': db_status['size_info'],
            'vector_info': db_status['vector_info'],
            'connection_info': db_status.get('db_details', {})
        })
            
    except Exception as e:
        logger.exception(f"Error fetching database status: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f"Error: {str(e)}"
        }), 500

@app.route('/api/memory/config', methods=['GET', 'POST'])
def memory_config():
    """
    Get or update memory configuration settings.
    
    GET: Retrieve current memory configuration
    POST: Update memory configuration with provided values
    """
    try:
        # Import memory management
        from memory.langgraph_memory import LangGraphMemory
        memory_manager = LangGraphMemory()
        
        if request.method == 'GET':
            # Get current configuration
            config = memory_manager.get_config()
            return jsonify({
                'status': 'success',
                'config': config
            })
        elif request.method == 'POST':
            # Update configuration with provided values
            data = request.json
            
            # Extract configuration parameters from request
            max_memory_age = data.get('max_memory_age')
            max_messages = data.get('max_messages')
            message_window = data.get('message_window')
            enable_context_window = data.get('enable_context_window')
            persist_memory = data.get('persist_memory')
            
            # Update configuration
            updated_config = memory_manager.update_config(
                max_memory_age=max_memory_age,
                max_messages=max_messages,
                message_window=message_window,
                enable_context_window=enable_context_window,
                persist_memory=persist_memory
            )
            
            return jsonify({
                'status': 'success',
                'message': 'Memory configuration updated successfully',
                'config': updated_config
            })
    except Exception as e:
        logger.exception(f"Error managing memory configuration: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f"Error: {str(e)}"
        }), 500

@app.route('/api/step-logs/<step_name>')
def get_step_logs(step_name):
    """Return logs for a specific workflow step"""
    try:
        # Get the most recent logs for the specific step
        import re
        import json
        from collections import defaultdict
        
        # Read from log file
        log_file = os.path.join(project_dir, 'ui_test.log')
        
        if not os.path.exists(log_file):
            return jsonify({
                'status': 'error',
                'message': 'Log file not found'
            }), 404
            
        # Process the logs to extract relevant information for this step
        step_logs = []
        s3_storage_info = {}
        
        # Normalize step name for log matching
        step_search_patterns = {
            'InputRouter': r'(InputTypeRouter|input.*router)',
            'TextIntentClassifier': r'(TextIntentClassifier|intent.*classifier)',
            'GreetingHandler': r'(GreetingHandler|greeting.*handler)',
            'SQLGenerator': r'(TextToSQLConversionAgent|sql.*generator)',
            'DatabaseQuerier': r'(DatabaseQueryAgent|query.*executor)',
            'ResponseFormatter': r'(ResponseFormatterAgent|response.*formatter)',
            'FileValidator': r'(FileValidatorAgent|file.*validator)',
            'DataExtractor': r'(DataExtractorAgent|data.*extract)',
            'DatabaseStorage': r'(DatabaseStorageAgent|storage.*agent)',
            'S3Storage': r'(s3_handler|S3Handler|s3.storage)',
            'InvoiceRAGAgent': r'(\[WORKFLOW STEP\]|InvoiceRAGAgent|vector.*search|RAG.*search)'
        }
        
        pattern = step_search_patterns.get(step_name, step_name)
        search_regex = re.compile(pattern, re.IGNORECASE)
        
        # Patterns to search for S3 information
        s3_url_pattern = re.compile(r'url[:|=]\s*[\'"]?(https?://[^\'"]+)[\'"]?', re.IGNORECASE)
        s3_file_key_pattern = re.compile(r'file_key[:|=]\s*[\'"]?([^\'"]+)[\'"]?', re.IGNORECASE)
        s3_bucket_pattern = re.compile(r'bucket[:|=]\s*[\'"]?([^\'"]+)[\'"]?', re.IGNORECASE)
        s3_upload_pattern = re.compile(r'uploaded.*(to|S3).*', re.IGNORECASE)
        s3_metadata_pattern = re.compile(r'S3 metadata', re.IGNORECASE)
        
        # Read all logs and keep track of the context
        context = defaultdict(dict)
        
        # Always include logs with user_id for context
        user_id_regex = re.compile(r'user_id[:|=]\s*(\d+)', re.IGNORECASE)
        whatsapp_regex = re.compile(r'whatsapp[:|=]\s*(\+\d+)', re.IGNORECASE)
        
        with open(log_file, 'r') as f:
            for line in f:
                # Check for user_id to maintain context
                user_id_match = user_id_regex.search(line)
                if user_id_match:
                    context['user_id'] = user_id_match.group(1)
                
                # Check for whatsapp number to maintain context
                whatsapp_match = whatsapp_regex.search(line)
                if whatsapp_match:
                    context['whatsapp'] = whatsapp_match.group(1)
                
                # Look for S3 information regardless of step
                s3_url_match = s3_url_pattern.search(line)
                if s3_url_match:
                    s3_storage_info['url'] = s3_url_match.group(1)
                    logger.info(f"Found S3 URL in logs: {s3_storage_info['url'][:30]}...")
                
                s3_file_key_match = s3_file_key_pattern.search(line)
                if s3_file_key_match:
                    s3_storage_info['file_key'] = s3_file_key_match.group(1)
                    logger.info(f"Found S3 file key in logs: {s3_storage_info['file_key']}")
                
                s3_bucket_match = s3_bucket_pattern.search(line)
                if s3_bucket_match:
                    s3_storage_info['bucket'] = s3_bucket_match.group(1)
                    logger.info(f"Found S3 bucket in logs: {s3_storage_info['bucket']}")
                
                # Check for input/output patterns to enhance log context
                if 'input:' in line.lower() or 'with input:' in line.lower():
                    try:
                        # Try to extract structured input
                        input_part = line.split('input:', 1)[1].strip() if 'input:' in line.lower() else line.split('with input:', 1)[1].strip()
                        context['last_input'] = input_part
                    except:
                        pass
                
                if 'output:' in line.lower() or 'result:' in line.lower() or 'response:' in line.lower():
                    try:
                        # Try to extract structured output
                        output_key = [k for k in ['output:', 'result:', 'response:'] if k in line.lower()][0]
                        output_part = line.split(output_key, 1)[1].strip()
                        context['last_output'] = output_part
                    except:
                        pass
                
                # Special case: if we're looking for S3 storage info specifically
                if step_name == 'S3Storage' and (s3_upload_pattern.search(line) or s3_metadata_pattern.search(line)):
                    # Add context information to the log line
                    enriched_log = {
                        'log': line.strip(),
                        'context': {k: v for k, v in context.items()}
                    }
                    step_logs.append(enriched_log)
                # Check if this line matches our target step
                elif search_regex.search(line):
                    # Add context information to the log line
                    enriched_log = {
                        'log': line.strip(),
                        'context': {k: v for k, v in context.items()}
                    }
                    step_logs.append(enriched_log)
        
        # Return the step-specific logs with context and S3 info
        response_data = {
            'status': 'success',
            'step_name': step_name,
            'logs': [log['log'] for log in step_logs[-50:]] if step_logs else [],  # Return the last 50 log lines
        }
        
        # Add S3 storage info if available
        if s3_storage_info:
            response_data['s3_storage'] = s3_storage_info
            logger.info(f"Including S3 storage info in response: {s3_storage_info}")
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.exception(f"Error fetching step logs: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f"Error fetching logs: {str(e)}"
        }), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/init')
def initialize():
    """Initialize the test environment"""
    try:
        global CONVERSATION_ID, CONVERSATION_HISTORY, WHATSAPP_NUMBER, USER_ID
        
        # Reset conversation ID for new session
        CONVERSATION_ID = str(uuid.uuid4())
        CONVERSATION_HISTORY = []
        
        # Get WhatsApp number from request or use default
        whatsapp_number = request.args.get('whatsapp_number', DEFAULT_WHATSAPP_NUMBER)
        WHATSAPP_NUMBER = whatsapp_number
        
        # Get user ID for this WhatsApp number, creating if needed
        USER_ID = run_async(lambda: get_user_id_from_whatsapp(WHATSAPP_NUMBER))
        
        # Use our improved async handling
        run_async(lambda: asyncio.to_thread(ensure_test_user_exists))
        
        return jsonify({
            'status': 'success', 
            'message': 'Test environment initialized',
            'user_id': USER_ID,
            'whatsapp_number': WHATSAPP_NUMBER
        })
            
    except Exception as e:
        logger.exception(f"Error initializing test environment: {str(e)}")
        return jsonify({'status': 'error', 'message': f"Error: {str(e)}"}), 500

@app.route('/api/s3-info')
def get_s3_info():
    """Return S3 storage information for the most recent file upload"""
    try:
        import re
        import os
        import time
        from sqlalchemy import text
        
        # Read from log file
        log_file = os.path.join(project_dir, 'ui_test.log')
        
        if not os.path.exists(log_file):
            return jsonify({
                'status': 'error',
                'message': 'Log file not found'
            }), 404
        
        # Get WhatsApp number from environment or use default
        whatsapp_number = request.args.get('whatsapp_number') or os.environ.get('WHATSAPP_NUMBER', '+1234567890')
        logger.info(f"Looking for S3 info for WhatsApp number: {whatsapp_number}")
        
        # Regular expressions to search for S3 information
        s3_url_pattern = re.compile(r'url[\'"]?:\s*[\'"]?(https?://[^\'",}\n]+)', re.IGNORECASE)
        s3_direct_url_pattern = re.compile(r'https://[a-zA-Z0-9.-]+\.s3\.amazonaws\.com/[^\'"\s]+', re.IGNORECASE)
        s3_file_key_pattern = re.compile(r'file_key[\'"]?:\s*[\'"]?([^\'",}\n]+)', re.IGNORECASE)
        s3_bucket_pattern = re.compile(r'bucket[\'"]?:\s*[\'"]?([^\'",}\n]+)', re.IGNORECASE)
        s3_invoice_pattern = re.compile(r'invoice/\+\d+/invoice_\d+\.\w+', re.IGNORECASE)
        
        # Import the S3Handler to generate presigned URLs
        from storage.s3_handler import S3Handler
        s3_handler = None
        try:
            s3_handler = S3Handler()
            logger.info(f"Created S3Handler for generating presigned URLs")
        except Exception as e:
            logger.warning(f"Failed to create S3Handler: {str(e)}")
        
        # Variables to store S3 information
        s3_storage_info = {}
        
        logger.info("Searching for actual invoice S3 storage information...")
        
        # Approach 1: Try to find an actual uploaded invoice in the logs first
        real_invoice_found = False
        with open(log_file, 'r') as f:
            lines = f.readlines()
            
            # First look for actual invoice uploads in the logs
            for line in reversed(lines):
                # Look for the pattern like "invoice/+1234567890/invoice_1743961448.txt"
                invoice_match = s3_invoice_pattern.search(line)
                if invoice_match:
                    path = invoice_match.group(0)
                    logger.info(f"Found actual invoice path in logs: {path}")
                    
                    # Determine the S3 bucket from the same line or nearby lines
                    bucket_name = "sagemaker-us-east-1-911595125327"  # Default from URL example
                    bucket_match = re.search(r'bucket[^:]*:[^"\']*["\']?([^"\']+)["\']?', line)
                    if bucket_match:
                        bucket_name = bucket_match.group(1).strip()
                        if ' in region' in bucket_name:
                            bucket_name = bucket_name.split(' in region')[0].strip()
                    
                    # Try using existing presigned URL from logs first
                    pre_signed_url = None
                    for i in range(min(10, lines.index(line))):
                        url_check_line = lines[lines.index(line) - i]
                        url_match = s3_url_pattern.search(url_check_line)
                        if url_match and "AWSAccessKeyId=" in url_check_line:
                            pre_signed_url = url_match.group(1)
                            logger.info(f"Found pre-signed URL in logs: {pre_signed_url[:30]}...")
                            break
                    
                    # If we have S3Handler and no pre-signed URL yet, generate one
                    if s3_handler and not pre_signed_url:
                        try:
                            pre_signed_url = s3_handler.generate_url(path)
                            logger.info(f"Generated new pre-signed URL: {pre_signed_url[:30]}...")
                        except Exception as e:
                            logger.warning(f"Failed to generate pre-signed URL: {str(e)}")
                    
                    s3_storage_info = {
                        "file_key": path,
                        "bucket": bucket_name,
                        "url": pre_signed_url or f"https://{bucket_name}.s3.amazonaws.com/{path}"
                    }
                    
                    real_invoice_found = True
                    break
        
        # Approach 2: Check the database for the latest stored invoice
        if not real_invoice_found:
            try:
                # Define an async function to query the database
                async def query_db():
                    nonlocal s3_storage_info, whatsapp_number
                    from database.connection import get_db
                    
                    @contextmanager
                    def get_session():
                        db = next(get_db())
                        try:
                            yield db
                        finally:
                            db.close()
                    
                    # Get the latest invoice info from database
                    with get_session() as db:
                        # First try to get media record with file_url
                        media_query = text("""
                            SELECT m.file_url, m.file_path, i.user_id
                            FROM media m
                            JOIN invoices i ON m.invoice_id = i.id
                            ORDER BY m.created_at DESC
                            LIMIT 1
                        """)
                        
                        result = db.execute(media_query).first()
                        if result:
                            file_url, file_path, user_id = result
                            if file_url:
                                logger.info(f"Found invoice file URL in database: {file_url[:30]}...")
                                # Extract or build the file key
                                file_key = file_path or f"invoice/{whatsapp_number}/invoice_{int(time.time())}.png"
                                
                                # Get bucket name from URL if possible
                                bucket_name = "sagemaker-us-east-1-911595125327"  # Default from URL example
                                bucket_match = re.search(r'https://([^.]+)', file_url)
                                if bucket_match:
                                    bucket_name = bucket_match.group(1)
                                
                                # If URL is not presigned but we have file_key and handler, generate presigned URL
                                if s3_handler and file_key and "AWSAccessKeyId=" not in file_url:
                                    try:
                                        presigned_url = s3_handler.generate_url(file_key)
                                        logger.info(f"Generated new pre-signed URL from DB record: {presigned_url[:30]}...")
                                        file_url = presigned_url
                                    except Exception as e:
                                        logger.warning(f"Failed to generate pre-signed URL from DB: {str(e)}")
                                
                                s3_storage_info = {
                                    "file_key": file_key,
                                    "bucket": bucket_name,
                                    "url": file_url
                                }
                                
                        # If no media record, try to get just the latest invoice
                        if not s3_storage_info or not s3_storage_info.get('url'):
                            invoice_query = text("""
                                SELECT i.id, u.whatsapp_number
                                FROM invoices i
                                JOIN users u ON i.user_id = u.id
                                ORDER BY i.created_at DESC
                                LIMIT 1
                            """)
                            
                            result = db.execute(invoice_query).first()
                            if result:
                                invoice_id, user_whatsapp = result
                                if user_whatsapp:
                                    whatsapp_number = user_whatsapp
                
                # Use our improved async handling
                run_async(lambda: query_db())
                
            except Exception as e:
                logger.warning(f"Error querying database for invoice information: {str(e)}")
        
        # Approach 3: If we still don't have the info, create a properly structured file_key and pre-signed URL
        if not s3_storage_info or 'url' not in s3_storage_info:
            # Get bucket name from environment or use default from URL example
            bucket_name = os.environ.get('S3_BUCKET_NAME', 'sagemaker-us-east-1-911595125327')
            
            # Create a timestamp for the filename
            timestamp = int(time.time())
            
            # Format the file key according to the standard structure
            file_key = f"invoice/{whatsapp_number}/invoice_{timestamp}.png"
            
            # Generate pre-signed URL if handler is available
            if s3_handler:
                try:
                    presigned_url = s3_handler.generate_url(file_key)
                    logger.info(f"Created pre-signed URL for new file key: {presigned_url[:30]}...")
                    
                    s3_storage_info = {
                        "file_key": file_key,
                        "bucket": bucket_name,
                        "url": presigned_url
                    }
                except Exception as e:
                    logger.warning(f"Failed to generate pre-signed URL for new file: {str(e)}")
                    # Fall back to direct URL if pre-signed fails
                    s3_storage_info = {
                        "file_key": file_key,
                        "bucket": bucket_name,
                        "url": f"https://{bucket_name}.s3.amazonaws.com/{file_key}"
                    }
                    logger.info("Using direct S3 URL as fallback (requires public access)")
            else:
                # If S3Handler is not available, use direct URL as last resort
                s3_storage_info = {
                    "file_key": file_key,
                    "bucket": bucket_name,
                    "url": f"https://{bucket_name}.s3.amazonaws.com/{file_key}"
                }
                logger.warning("S3Handler not available, using direct URL (requires public access)")
            
            logger.info(f"Created new S3 storage info with correct path structure: {file_key}")
        
        # Final check: If we have a file_key and S3Handler but direct URL, try one more time to create pre-signed URL
        if s3_storage_info and s3_handler and 'file_key' in s3_storage_info and 'url' in s3_storage_info and not "AWSAccessKeyId=" in s3_storage_info['url']:
            try:
                presigned_url = s3_handler.generate_url(s3_storage_info['file_key'])
                logger.info(f"Generated final pre-signed URL: {presigned_url[:30]}...")
                s3_storage_info['url'] = presigned_url
            except Exception as e:
                logger.warning(f"Final attempt to generate pre-signed URL failed: {str(e)}")
        
        # If we found or created S3 info, return it
        logger.info(f"Returning S3 storage information: {s3_storage_info}")
        return jsonify({
            'status': 'success',
            's3_storage': s3_storage_info
        })
            
    except Exception as e:
        logger.exception(f"Error fetching S3 storage information: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f"Error fetching S3 storage information: {str(e)}"
        }), 500

@app.route('/api/users')
def get_users():
    """Get all users from database for UI dropdown"""
    try:
        users = run_async(lambda: get_all_users())
        
        return jsonify({
            'status': 'success',
            'users': users
        })
    except Exception as e:
        logger.exception(f"Error fetching users: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f"Error fetching users: {str(e)}"
        }), 500

@app.route('/api/users/create', methods=['POST'])
def create_user():
    """Create a new user with the provided information"""
    try:
        # Get request data
        data = request.json
        
        # Extract required field
        whatsapp_number = data.get('whatsapp_number')
        
        # Extract optional fields
        name = data.get('name')
        email = data.get('email')
        
        # Validate required field
        if not whatsapp_number:
            return jsonify({
                'status': 'error',
                'message': 'WhatsApp number is required'
            }), 400
            
        # Import the user utilities
        from database.user_utils import create_user as db_create_user
        from database.connection import db_session
        
        # Create the user in the database
        with db_session() as session:
            user_info = db_create_user(
                session=session,
                whatsapp_number=whatsapp_number,
                name=name,
                email=email
            )
        
        # Return the created user information
        return jsonify({
            'status': 'success',
            'message': 'User created successfully' if user_info['is_new'] else 'User already exists',
            'user': user_info
            })
            
    except Exception as e:
        logger.exception(f"Error creating user: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f"Error creating user: {str(e)}"
        }), 500

@app.route('/api/embeddings/update', methods=['POST'])
def update_embeddings():
    """
    Endpoint to trigger updating of vector embeddings for items and invoices.
    
    Query Params:
        force (bool): If true, will update all embeddings even if they already exist.
                      If false, will only update embeddings for records without them.
    """
    try:
        # Get parameters from request
        data = request.json
        force = data.get('force', False)
        
        logger.info(f"Starting embeddings update. Force update: {force}")
        
        # Run embeddings update in a background thread
        thread = threading.Thread(
            target=run_embeddings_update,
            kwargs={'force_update': force}
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'status': 'success',
            'message': 'Vector embeddings update started',
            'result': {
                'force_update': force
            }
        })
        
    except Exception as e:
        logger.error(f"Error updating embeddings: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'status': 'error',
            'message': f"Error updating embeddings: {str(e)}"
        }), 500

@app.route('/api/check-embeddings', methods=['GET'])
def check_embeddings():
    """Check the status of embeddings in the database."""
    try:
        from utils.db_embeddings import check_embedding_status
        
        result = run_async(check_embedding_status)
        return jsonify({
            "status": "success",
            "data": result
        })
    except Exception as e:
        logger.exception(f"Error checking embeddings: {str(e)}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.teardown_appcontext
def shutdown_event_loops(exception=None):
    """Properly clean up any remaining event loops on app shutdown"""
    logger.info("Shutting down application and cleaning up resources")
    try:
        # Get the current event loop if one exists
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_closed():
                # Cancel any pending tasks
                tasks = asyncio.all_tasks(loop)
                if tasks:
                    logger.info(f"Cancelling {len(tasks)} pending tasks")
                    for task in tasks:
                        task.cancel()
                    
                    # Give tasks a chance to respond to cancellation
                    try:
                        loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                    except Exception as e:
                        logger.warning(f"Error cancelling tasks: {str(e)}")
                
                # Close the loop
                loop.close()
                logger.info("Event loop closed")
        except RuntimeError:
            # No event loop, nothing to do
            pass
    except Exception as e:
        logger.exception(f"Error during application shutdown: {str(e)}")

# Run the application only if executed directly (not when imported)
if __name__ == '__main__':
    # If this module is run directly, parse arguments and start the server
    import sys
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Flask app for WhatsApp Invoice Assistant testing',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('--port', type=int, default=5001, 
                        help='Port to run the app on (default: 5001)')
    parser.add_argument('--host', type=str, default='0.0.0.0', 
                        help='Host address to bind to (default: 0.0.0.0)')
    parser.add_argument('--debug', action='store_true', 
                        help='Run in debug mode (default: False)')
    parser.add_argument('--force', action='store_true',
                        help='Force update embeddings on startup')
    
    # Only parse known arguments, ignore the rest
    args, unknown = parser.parse_known_args()
    if unknown:
        logger.warning(f"Unknown arguments ignored: {unknown}")
    
    # Ensure test user exists before starting the app using our improved async handling
    run_async(lambda: asyncio.to_thread(ensure_test_user_exists))
    
    logger.info(f"Starting Flask app on {args.host}:{args.port}")
    logger.info(f"Open your browser and navigate to http://localhost:{args.port}")
    logger.info(f"Available API endpoints:")
    logger.info(f"  - GET  /api/init - Initialize test environment")
    logger.info(f"  - POST /api/message - Send a message to the assistant")
    logger.info(f"  - POST /api/upload - Upload a file")
    logger.info(f"  - GET  /api/agent-flow - Get agent flow information")
    logger.info(f"  - GET  /api/db-status - Get database status")
    logger.info(f"  - GET  /api/step-logs/<step_name> - Get logs for a specific workflow step")
    logger.info(f"  - GET  /api/s3-info - Get S3 storage information for the most recent file upload")
    logger.info(f"  - GET  /api/users - Get all users from database for UI dropdown")
    logger.info(f"  - POST /api/users/create - Create a new user with WhatsApp number")
    
    # Run the app
    try:
        app.run(debug=args.debug, host=args.host, port=args.port, threaded=True)
    finally:
        logger.info("Flask app shutdown complete") 