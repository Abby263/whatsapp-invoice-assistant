"""
Database Storage Agent for WhatsApp Invoice Assistant.

This module implements the agent responsible for storing extracted invoice data
in the database using appropriate schema mapping and data validation.
"""

import logging
import json
import uuid
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from utils.base_agent import BaseAgent, AgentInput, AgentOutput, AgentContext
from services.llm_factory import LLMFactory
from database.connection import SessionLocal
from database import schemas
from utils.vector_utils import get_embedding_generator

# Configure logger for this module
logger = logging.getLogger(__name__)


class DatabaseStorageAgent(BaseAgent):
    """
    Agent for storing extracted invoice data in the database.
    
    This agent handles the creation of database records for invoices,
    invoice items, and media files, with appropriate error handling
    and data validation.
    """
    
    def __init__(self, llm_factory: Optional[LLMFactory] = None):
        """
        Initialize the DatabaseStorageAgent.
        
        Args:
            llm_factory: Optional LLMFactory instance for LLM operations
        """
        super().__init__(llm_factory)
        # Initialize the embedding generator
        self.embedding_generator = get_embedding_generator()
        
    async def process(self, agent_input: AgentInput, context: AgentContext) -> AgentOutput:
        """
        Process the agent input to store invoice data in the database.
        
        Args:
            agent_input: The input containing the invoice data
            context: Agent context with user information
            
        Returns:
            An AgentOutput object with the status of the database operation
        """
        logger.info(f"DatabaseStorageAgent processing request for user: {context.user_id}")
        
        try:
            # Extract content from agent input
            content = agent_input.content
            
            # Check if content is a JSON string or a dict
            if isinstance(content, str):
                try:
                    # Try to parse as JSON
                    logger.info("Content is a string, attempting to parse as JSON")
                    logger.debug(f"JSON string length: {len(content)} bytes")
                    extraction_result = json.loads(content)
                    logger.info(f"JSON parse success, keys: {extraction_result.keys() if isinstance(extraction_result, dict) else 'not a dict'}")
                except json.JSONDecodeError as e:
                    error_message = f"Invalid JSON: {str(e)}"
                    logger.error(f"JSON parse error: {error_message}")
                    return AgentOutput(
                        content={"error": error_message},
                        status="error",
                        error=error_message
                    )
            elif isinstance(content, dict):
                # Already a dictionary
                logger.info("Content is already a dictionary")
                extraction_result = content
                logger.info(f"Dictionary content keys: {extraction_result.keys()}")
            else:
                error_message = f"Unsupported content type: {type(content)}"
                logger.error(error_message)
                return AgentOutput(
                    content={"error": error_message},
                    status="error",
                    error=error_message
                )
            
            # Get user_id from context or metadata
            user_id = context.user_id
            if not user_id and agent_input.metadata and "user_id" in agent_input.metadata:
                user_id = agent_input.metadata.get("user_id")
                logger.info(f"Using user_id from metadata: {user_id}")
                
            if not user_id:
                error_message = "User ID not provided."
                logger.error(error_message)
                return AgentOutput(
                    content={"error": error_message},
                    status="error",
                    error=error_message
                )
                
            # Log structured data availability before storage
            if isinstance(extraction_result, dict):
                logger.info(f"Invoice data summary before storage:")
                if "vendor" in extraction_result:
                    vendor_data = extraction_result.get("vendor", {})
                    vendor_name = vendor_data.get("name", "Unknown") if isinstance(vendor_data, dict) else vendor_data
                    logger.info(f"- Vendor: {vendor_name}")
                
                # Log items data presence
                items = []
                if "items" in extraction_result:
                    items = extraction_result.get("items", [])
                    logger.info(f"- Items count at root level: {len(items) if isinstance(items, list) else 'not a list'}")
                
                # Check for nested data structure
                if "data" in extraction_result and isinstance(extraction_result["data"], dict):
                    data = extraction_result["data"]
                    if "items" in data:
                        items = data.get("items", [])
                        logger.info(f"- Items count in data node: {len(items) if isinstance(items, list) else 'not a list'}")
            
            # Store the invoice data
            logger.info(f"Calling store_invoice_data with user_id: {user_id}")
            store_result = self.store_invoice_data(extraction_result, user_id)
            logger.info(f"Store invoice data returned: {store_result}")
            
            # Ensure the store_result has a status field
            if "status" not in store_result:
                logger.info("Adding missing 'status' field with default value 'success'")
                store_result["status"] = "success"
                
            if "status" in store_result and store_result["status"] == "success":
                logger.info(f"Storage successful: {store_result}")
                return AgentOutput(
                    content=store_result,
                    status="success"
                )
            else:
                error_message = store_result.get("error", "Unknown error")
                logger.error(f"Storage failed with error: {error_message}")
                return AgentOutput(
                    content={"error": error_message},
                    status="error",
                    error=error_message
                )
                
        except Exception as e:
            error_message = f"Error storing invoice data: {str(e)}"
            logger.exception(error_message)
            return AgentOutput(
                content={"error": error_message},
                status="error",
                error=error_message
            )
    
    def store_invoice_data(self, extraction_result: Dict[str, Any], user_id: Union[str, UUID]) -> Dict[str, Any]:
        """
        Store extracted invoice data in the database.
        
        Args:
            extraction_result: Extracted invoice data
            user_id: User ID to associate with the invoice
            
        Returns:
            Dict containing storage operation results or error information
        """
        # Get database session
        db = SessionLocal()
        
        try:
            # Extract the invoice data - handle different structure possibilities
            # First log the extraction_result structure for debugging
            logger.info(f"extraction_result keys: {extraction_result.keys() if isinstance(extraction_result, dict) else 'not a dict'}")
            
            # Handle both direct structure and nested 'data' structure
            if "data" in extraction_result:
                invoice_data = extraction_result.get("data", {})
                logger.info("Using 'data' field from extraction_result")
            else:
                # The extraction_result itself contains the invoice data
                invoice_data = extraction_result
                logger.info("Using extraction_result directly as invoice data")
            
            # Log the invoice_data keys for debugging
            logger.info(f"invoice_data keys: {invoice_data.keys() if isinstance(invoice_data, dict) else 'not a dict'}")
            
            # Parse user_id to UUID if it's a string
            # Handle special case for test user with ID '0'
            if user_id == '0' or user_id == 0:
                # For test user with ID 0, use integer
                user_id_value = 0
                logger.info("Using integer ID 0 for test user")
            else:
                # For non-test users, convert UUID to string and then to integer if possible
                try:
                    if isinstance(user_id, UUID):
                        # Try to extract numeric part from UUID if needed
                        user_id_str = str(user_id)
                        # If it's a valid integer string, convert to int
                        if user_id_str.isdigit():
                            user_id_value = int(user_id_str)
                        else:
                            # Use a fallback ID for UUIDs that can't be converted
                            user_id_value = 1  # Default to user ID 1 for non-test users
                    else:
                        # Try to convert to int
                        user_id_value = int(user_id)
                except (ValueError, TypeError):
                    # If conversion fails, use a default user ID
                    user_id_value = 1
                    logger.warning(f"Could not convert user_id to integer: {user_id}, using default: 1")
            
            # Extract vendor information
            vendor_data = invoice_data.get("vendor", {})
            vendor_name = vendor_data.get("name", "Unknown") if isinstance(vendor_data, dict) else vendor_data
            
            # Extract transaction information
            transaction_data = invoice_data.get("transaction", {})
            if isinstance(transaction_data, dict):
                invoice_number = transaction_data.get("invoice_number")
                
                # Parse dates
                invoice_date_str = transaction_data.get("date")
                
                # Convert date strings to datetime objects if present
                invoice_date = None
                if invoice_date_str:
                    try:
                        invoice_date = datetime.strptime(invoice_date_str, "%Y-%m-%d")
                    except ValueError:
                        logger.warning(f"Could not parse invoice date: {invoice_date_str}")
            else:
                invoice_number = None
                invoice_date = None
            
            # Extract financial information
            financial_data = invoice_data.get("financial", {})
            if isinstance(financial_data, dict):
                total_amount = financial_data.get("total", 0)
                currency = financial_data.get("currency", "INR")
                
                # Extract tax information - we track this but don't store it directly
                tax_data = financial_data.get("tax", {})
                # Note: tax_amount is not directly stored, but kept in the raw_data JSON
            else:
                total_amount = invoice_data.get("total_amount", 0)
                currency = invoice_data.get("currency", "INR")
            
            # Extract notes
            additional_info = invoice_data.get("additional_info", {})
            notes = additional_info.get("notes", "") if isinstance(additional_info, dict) else ""
            
            # Get S3 file URL if available
            file_url = None
            file_content_type = None
            if "metadata" in extraction_result and "s3_storage" in extraction_result["metadata"]:
                s3_storage = extraction_result["metadata"]["s3_storage"]
                file_url = s3_storage.get("url", "")
                file_content_type = s3_storage.get("content_type", "")
            
            # Create an invoice record directly using SQLAlchemy model
            invoice = schemas.Invoice(
                user_id=user_id_value,
                invoice_number=invoice_number,
                invoice_date=invoice_date,
                vendor=vendor_name,
                total_amount=float(total_amount),
                currency=currency,
                notes=notes,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            # Add and commit the invoice
            db.add(invoice)
            db.flush()  # Flush to get the invoice.id without committing yet
            
            # Extract items
            item_ids = []
            # Try to get items directly from the invoice_data
            items = invoice_data.get("items", [])
            logger.info(f"Found {len(items) if items else 0} items in invoice data")
            
            if not items and "items" in extraction_result:
                # If items not in invoice_data but in extraction_result, use that
                items = extraction_result.get("items", [])
                logger.info(f"Using items directly from extraction_result: {len(items) if items else 0} items")
            
            if items and isinstance(items, list):
                # Pre-generate embeddings for all item descriptions in batch for efficiency
                item_descriptions = [item.get("description", "Item") for item in items if isinstance(item, dict)]
                logger.info(f"Generating embeddings for {len(item_descriptions)} items")
                
                batch_embeddings = None
                try:
                    # Generate embeddings for all descriptions in a single batch operation
                    batch_embeddings = self.embedding_generator.generate_batch_embeddings(item_descriptions)
                    logger.info(f"Successfully generated {len(batch_embeddings) if batch_embeddings else 0} embeddings")
                except Exception as e:
                    logger.exception(f"Error generating batch embeddings: {str(e)}")
                    # Continue with item creation even if embeddings fail
                
                # Process each item
                for i, item in enumerate(items):
                    if not isinstance(item, dict):
                        logger.warning(f"Skipping item {i}: not a dictionary, type: {type(item)}")
                        continue
                        
                    logger.info(f"Processing item {i+1}: {item}")
                    description = item.get("description", "Item")
                    quantity = item.get("quantity", 1)
                    unit_price = item.get("unit_price", 0)
                    total_price = item.get("total_price", 0)
                    item_category = item.get("item_category")  # Get item_category
                    item_code = item.get("item_code")  # Get item_code
                    
                    # Log item values for debugging
                    logger.info(f"Item details - description: {description}, quantity: {quantity}, " 
                               f"unit_price: {unit_price}, total_price: {total_price}, "
                               f"item_category: {item_category}, item_code: {item_code}")
                    
                    # Get the embedding for this item
                    embedding = None
                    if batch_embeddings and i < len(batch_embeddings):
                        embedding = batch_embeddings[i]
                        logger.info(f"Using pre-generated embedding for item {i+1}")
                    
                    try:
                        # Create an item record directly using SQLAlchemy model
                        item_record = schemas.Item(
                            invoice_id=invoice.id,
                            description=description,
                            quantity=float(quantity),
                            unit_price=float(unit_price),
                            total_price=float(total_price),
                            item_category=item_category,  # Set item_category
                            item_code=item_code,  # Set item_code
                            description_embedding=embedding,  # Set the embedding
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow()
                        )
                        
                        # Add the item
                        db.add(item_record)
                        db.flush()  # Flush to get the item.id
                        logger.info(f"Item record created with ID: {item_record.id} {'with embedding' if embedding else 'without embedding'}")
                        item_ids.append(str(item_record.id))
                    except Exception as e:
                        logger.exception(f"Error creating item record: {str(e)}")
            else:
                logger.warning(f"No items found in invoice data or items not a list. Items data: {items}")
            
            # If S3 storage info is available, store it as media
            media_id = None
            if "metadata" in extraction_result and "s3_storage" in extraction_result["metadata"]:
                s3_storage = extraction_result["metadata"]["s3_storage"]
                
                # Create a media record with the correct column names
                media_record = schemas.Media(
                    user_id=user_id_value,
                    invoice_id=invoice.id,
                    filename=s3_storage.get("original_filename", "invoice"),
                    original_filename=s3_storage.get("original_filename", "invoice"),
                    file_path=s3_storage.get("file_key", ""),
                    file_url=s3_storage.get("url", ""),
                    content_type=s3_storage.get("content_type", "image"),
                    file_size=extraction_result.get("file_size", 0),
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                
                # Add the media record
                db.add(media_record)
                db.flush()  # Flush to get the media.id
                media_id = media_record.id
            
            # Commit all changes
            db.commit()
            
            logger.info(f"Invoice stored in database with ID: {invoice.id}")
            
            # Return success information
            return {
                "status": "success",
                "invoice_id": str(invoice.id),
                "item_ids": item_ids,
                "media_id": str(media_id) if media_id else None,
                "invoice_number": invoice_number,
                "vendor": vendor_name,
                "total_amount": float(total_amount) if total_amount else 0
            }
            
        except Exception as e:
            # Roll back on error
            db.rollback()
            logger.exception(f"Error storing invoice: {str(e)}")
            return {
                "status": "error",
                "error": f"Database error: {str(e)}"
            }
        finally:
            # Always close the session
            db.close() 