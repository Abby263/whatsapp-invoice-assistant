"""
Main API entry point for the WhatsApp Invoice Assistant.

This module configures and runs the FastAPI application that serves
as the backend for the WhatsApp Invoice Assistant.
"""

import os
import logging
import sys
from pathlib import Path
from fastapi import FastAPI, Request, Response, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Add project root to path for imports
app_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(app_dir)
sys.path.insert(0, project_dir)

# Configure logging
from utils.logging import get_logs_directory, setup_logger

logs_dir = get_logs_directory()
log_file = os.path.join(logs_dir, 'api.log')
logger = setup_logger("api", log_file)

# Import API routes
# from api.routes import webhooks, memory, health

# Load environment variables
load_dotenv()

# Apply patches if needed
try:
    import patches
    logger.info("Applied compatibility patches")
except Exception as e:
    logger.error(f"Error applying patches: {e}")

# Import WhatsApp message processing functions
from langchain_app.api import process_whatsapp_message, process_text_message, process_file_message

# Create FastAPI app
app = FastAPI(
    title="WhatsApp Invoice Assistant API",
    description="API for the WhatsApp Invoice Assistant",
    version="1.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production, specify domain names instead of "*"
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/health")
async def health_check():
    """Check if the API is running"""
    return {"status": "ok", "message": "WhatsApp Invoice Assistant API is running"}

# Webhook endpoint for WhatsApp messages
@app.post("/webhook")
async def webhook(request: Request):
    """Handle incoming webhook from WhatsApp"""
    data = await request.form()
    data_dict = dict(data)
    
    logger.info(f"Received webhook: {data_dict}")
    
    try:
        response = await process_whatsapp_message(data_dict)
        logger.info(f"Processed webhook with response: {response}")
        return JSONResponse(content=response)
    except Exception as e:
        logger.exception(f"Error processing webhook: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

# Test endpoint for text messages
@app.post("/message")
async def message(request: Request):
    """Process a text message directly (for testing)"""
    data = await request.json()
    
    message = data.get("message")
    sender = data.get("sender", "test-user")
    user_id = data.get("user_id")
    conversation_id = data.get("conversation_id")
    
    if not message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No message provided"
        )
    
    try:
        response = await process_text_message(
            message=message,
            sender=sender,
            user_id=user_id,
            conversation_id=conversation_id
        )
        
        return response
    except Exception as e:
        logger.exception(f"Error processing message: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

# Test endpoint for file processing
@app.post("/file")
async def file(request: Request):
    """Process a file directly (for testing)"""
    form = await request.form()
    
    if "file" not in form:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided"
        )
    
    file = form["file"]
    sender = form.get("sender", "test-user")
    user_id = form.get("user_id")
    conversation_id = form.get("conversation_id")
    
    # Save the file temporarily
    temp_file_path = Path(os.path.join(project_dir, "uploads", file.filename))
    with open(temp_file_path, "wb") as f:
        f.write(await file.read())
    
    try:
        # Determine MIME type
        file_ext = os.path.splitext(file.filename)[1].lower()
        mime_type = "application/pdf" if file_ext == ".pdf" else \
                    "image/jpeg" if file_ext in [".jpg", ".jpeg"] else \
                    "image/png" if file_ext == ".png" else \
                    "application/octet-stream"
        
        response = await process_file_message(
            file_path=str(temp_file_path),
            file_name=file.filename,
            mime_type=mime_type,
            sender=sender,
            user_id=user_id,
            conversation_id=conversation_id
        )
        
        return response
    except Exception as e:
        logger.exception(f"Error processing file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    finally:
        # Clean up the temporary file
        if temp_file_path.exists():
            temp_file_path.unlink()

# Memory management endpoints
@app.get("/memory")
async def get_memory(user_id: str):
    """Get memory data for a specific user"""
    from memory.mongodb_memory import MongoDBMemory
    try:
        mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017/whatsapp_invoice_assistant")
        memory = MongoDBMemory(mongodb_uri=mongodb_uri)
        
        # Get memory data for the specified user
        memory_data = memory.get_memory_by_user(user_id)
        
        return {"status": "success", "data": memory_data}
    except Exception as e:
        logger.exception(f"Error retrieving memory: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@app.delete("/memory/{user_id}")
async def delete_memory(user_id: str):
    """Delete memory data for a specific user"""
    from memory.mongodb_memory import MongoDBMemory
    try:
        mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017/whatsapp_invoice_assistant")
        memory = MongoDBMemory(mongodb_uri=mongodb_uri)
        
        # Delete memory data for the specified user
        result = memory.delete_memory_by_user(user_id)
        
        return {"status": "success", "message": f"Memory deleted for user {user_id}", "result": result}
    except Exception as e:
        logger.exception(f"Error deleting memory: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

# Include other route modules when they're created
# app.include_router(webhooks.router)
# app.include_router(memory.router)
# app.include_router(health.router)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("api.main:app", host="0.0.0.0", port=port, reload=True) 