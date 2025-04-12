"""
File Processing Workflow for WhatsApp Invoice Assistant.

This module implements specialized workflow for handling file inputs,
validating invoice files, extracting data, and formatting responses.
"""

import logging
import os
from typing import Dict, Any, Optional, List, Union, BinaryIO
from uuid import UUID
from pathlib import Path
from datetime import datetime
import uuid
import json
import tempfile
import asyncio

from sqlalchemy.orm import Session

from agents.file_validator import FileValidatorAgent
from agents.data_extractor import DataExtractorAgent
from agents.response_formatter import ResponseFormatterAgent
from agents.database_storage_agent import DatabaseStorageAgent
from services.llm_factory import LLMFactory
from langchain_app.state import IntentType, FileType
from utils.base_agent import AgentInput, AgentContext
from database.connection import get_db, SessionLocal
from database import crud, models, schemas
from constants.fallback_messages import FILE_PROCESSING_FALLBACKS

logger = logging.getLogger(__name__)


async def process_file_message(
    file_path: str,
    file_type: str,
    file_name: Optional[str] = None,
    user_id: Optional[Union[str, UUID]] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Process a file message by validating and extracting data.
    
    Args:
        file_path: Path to the file to process
        file_type: MIME type or file extension
        file_name: Optional original filename
        user_id: Optional user ID for personalization
        conversation_history: Optional conversation history for context
        
    Returns:
        Dict containing the response content, metadata, and confidence
    """
    logger.info(f"Processing file: {file_name or file_path}")
    
    # Detect normalized file type from MIME type or extension
    normalized_file_type = detect_file_type(file_path, file_type)
    
    # Validate the file
    validation_result = await validate_file(file_path, normalized_file_type)
    
    if not validation_result.get("is_valid", False):
        logger.warning(f"Invalid file: {validation_result.get('reason', 'Unknown reason')}")
        return await format_invalid_file_response(validation_result, file_name or file_path)
    
    # Extract data if it's a valid invoice
    if validation_result.get("is_invoice", False):
        return await process_invoice_file(file_path, normalized_file_type, file_name, user_id, conversation_history)
    else:
        # Handle non-invoice but valid files
        return await format_unsupported_format_response(file_name or file_path, normalized_file_type)


async def validate_file(
    file_path: str,
    file_type: str
) -> Dict[str, Any]:
    """
    Validate a file to determine if it's a valid invoice.
    
    Args:
        file_path: Path to the file
        file_type: MIME type or file extension
        
    Returns:
        Dict containing validation results
    """
    llm_factory = LLMFactory()
    agent = FileValidatorAgent(llm_factory=llm_factory)
    
    try:
        # Check if file exists
        if not os.path.exists(file_path):
            return {
                "is_valid": False,
                "is_invoice": False,
                "reason": "File not found",
                "file_type": file_type
            }
        
        # Validate file type first
        supported_types = [
            FileType.PDF.value,
            FileType.IMAGE.value,
            FileType.EXCEL.value,
            FileType.CSV.value
        ]
        
        detected_type = detect_file_type(file_path, file_type)
        
        if detected_type not in supported_types:
            return {
                "is_valid": False,
                "is_invoice": False,
                "reason": f"Unsupported file type: {detected_type}",
                "file_type": detected_type
            }
        
        # Read file content
        with open(file_path, 'rb') as f:
            file_content = f.read()
        
        # Use agent to validate if it's an invoice - create an AgentInput object
        agent_input = AgentInput(
            content=file_content,
            file_path=file_path,
            file_name=os.path.basename(file_path),
            content_type=detected_type,
            metadata={"file_type": detected_type}
        )
        
        # Process with the properly constructed AgentInput object
        result = await agent.process(agent_input)
        
        if not result:
            return {
                "is_valid": True,
                "is_invoice": False,
                "reason": "Could not determine if file is an invoice",
                "file_type": detected_type
            }
        
        return {
            "is_valid": True,
            "is_invoice": result.content,  # The content field contains the boolean is_invoice result
            "confidence": result.confidence,
            "file_type": detected_type,
            "reason": result.metadata.get("reasons", "")
        }
        
    except Exception as e:
        logger.exception(f"Error validating file: {str(e)}")
        return {
            "is_valid": False,
            "is_invoice": False,
            "reason": f"Error during validation: {str(e)}",
            "file_type": file_type
        }


def detect_file_type(file_path: str, mime_type: str) -> str:
    """
    Detect file type based on extension and/or MIME type.
    
    Args:
        file_path: Path to the file
        mime_type: MIME type or file extension
        
    Returns:
        Normalized file type string
    """
    # Extract file extension
    extension = Path(file_path).suffix.lower()
    
    # Check based on extension
    if extension in ['.pdf']:
        return FileType.PDF.value
    elif extension in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']:
        return FileType.IMAGE.value
    elif extension in ['.xls', '.xlsx']:
        return FileType.EXCEL.value
    elif extension in ['.csv']:
        return FileType.CSV.value
    
    # Check based on MIME type
    if mime_type:
        mime_lower = mime_type.lower()
        if 'pdf' in mime_lower:
            return FileType.PDF.value
        elif any(img_type in mime_lower for img_type in ['jpeg', 'jpg', 'png', 'image']):
            return FileType.IMAGE.value
        elif any(excel_type in mime_lower for excel_type in ['excel', 'spreadsheet', 'xlsx', 'xls']):
            return FileType.EXCEL.value
        elif 'csv' in mime_lower:
            return FileType.CSV.value
    
    # Default to binary
    return FileType.BINARY.value


async def process_invoice_file(
    file_path: str,
    file_type: str,
    file_name: Optional[str] = None,
    user_id: Optional[Union[str, UUID]] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Process a valid invoice file by extracting data.
    
    Args:
        file_path: Path to the file
        file_type: File type
        file_name: Optional original filename
        user_id: Optional user ID
        conversation_history: Optional conversation history
        
    Returns:
        Dict containing extracted data and response
    """
    # Extract data from invoice
    extraction_result = await extract_invoice_data(file_path, file_type, user_id, conversation_history)
    
    # If extraction failed
    if "error" in extraction_result:
        logger.warning(f"Data extraction error: {extraction_result['error']}")
        return {
            "content": FILE_PROCESSING_FALLBACKS["extraction_failed"],
            "metadata": {
                "intent": IntentType.FILE_PROCESSING.value,
                "file_type": file_type,
                "error": extraction_result["error"]
            },
            "confidence": 0.4
        }
    
    # Store invoice data in database
    invoice_id = None
    if user_id is not None:
        # Use the DatabaseStorageAgent to store the invoice data
        storage_agent = DatabaseStorageAgent()
        
        # Convert extraction_result to JSON string to satisfy AgentInput requirements
        extraction_result_json = json.dumps(extraction_result)
        logger.info(f"Preparing to store invoice data for user_id: {user_id}, data size: {len(extraction_result_json)} bytes")
        
        try:
            # Create agent input with the extraction result as JSON string
            agent_input = AgentInput(
                content=extraction_result_json,
                metadata={"user_id": user_id}
            )
            
            # Create agent context with the user_id
            agent_context = AgentContext(user_id=str(user_id))
            
            # Store the invoice data
            logger.info("Calling DatabaseStorageAgent to store invoice data")
            storage_result = await storage_agent.process(agent_input, agent_context)
            
            # Get the invoice_id from the result if successful
            if storage_result and storage_result.status == "success" and isinstance(storage_result.content, dict):
                invoice_id = storage_result.content.get("invoice_id")
                item_ids = storage_result.content.get("item_ids", [])
                logger.info(f"✅ Successfully stored invoice data in database with ID: {invoice_id}, items: {len(item_ids)}")
                
                # Add invoice ID to extraction result for reference
                if "metadata" not in extraction_result:
                    extraction_result["metadata"] = {}
                extraction_result["metadata"]["invoice_id"] = invoice_id
                extraction_result["metadata"]["item_ids"] = item_ids
            else:
                error_message = storage_result.error if storage_result else "No result returned from storage agent"
                logger.error(f"❌ Error storing invoice data: {error_message}")
                if storage_result:
                    logger.error(f"Storage result status: {storage_result.status}, content type: {type(storage_result.content)}")
                    if isinstance(storage_result.content, dict) and "error" in storage_result.content:
                        logger.error(f"Storage error details: {storage_result.content['error']}")
        except Exception as e:
            logger.exception(f"❌ Exception in database storage: {str(e)}")
    
    # Format successful extraction response
    response = await format_extraction_response(extraction_result, file_name or file_path)
    
    # Add S3 storage metadata if available
    s3_metadata = None
    if "metadata" in extraction_result and "s3_storage" in extraction_result["metadata"]:
        s3_metadata = extraction_result["metadata"]["s3_storage"]
    
    # Prepare response metadata
    response_metadata = {
        "intent": IntentType.FILE_PROCESSING.value,
        "file_type": file_type,
        "extraction_results": extraction_result,
        "invoice_data": extraction_result.get("data", {})
    }
    
    # Add S3 metadata if available
    if s3_metadata:
        response_metadata["s3_storage"] = s3_metadata
    
    # Add invoice ID to response metadata if available
    if invoice_id:
        response_metadata["invoice_id"] = str(invoice_id)
    
    return {
        "content": response.get("content", ""),
        "metadata": response_metadata,
        "confidence": response.get("confidence", 0.7)
    }


async def extract_invoice_data(
    file_path: str, 
    file_type: str,
    user_id: Optional[Union[str, UUID]] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Extract data from an invoice file.
    
    Args:
        file_path: Path to the invoice file
        file_type: Type of the file
        user_id: Optional user ID for S3 storage
        conversation_history: Optional conversation history
        
    Returns:
        Dict containing extracted invoice data
    """
    # Log the environment variables to ensure AWS credentials are available
    aws_key = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret = os.environ.get("AWS_SECRET_ACCESS_KEY") 
    s3_bucket = os.environ.get("S3_BUCKET_NAME")
    s3_region = os.environ.get("S3_REGION")
    
    logger.info(f"AWS Environment Check:")
    logger.info(f"  - AWS_ACCESS_KEY_ID: {'Available' if aws_key else 'MISSING'}")
    logger.info(f"  - AWS_SECRET_ACCESS_KEY: {'Available' if aws_secret else 'MISSING'}")
    logger.info(f"  - S3_BUCKET_NAME: {s3_bucket or 'MISSING'}")
    logger.info(f"  - S3_REGION: {s3_region or 'MISSING'}")
    
    llm_factory = LLMFactory()
    agent = DataExtractorAgent(llm_factory=llm_factory)
    
    try:
        # Read file content
        with open(file_path, 'rb') as f:
            file_content = f.read()
        
        # Upload file to S3 if user_id is provided
        s3_metadata = None
        if user_id:
            try:
                from storage.s3_handler import S3Handler
                s3_handler = S3Handler()
                
                # Log S3 handler initialization
                logger.info(f"Created S3Handler for bucket: {s3_handler.bucket_name} in region: {s3_handler.region}")
                
                # Get file mime type
                import mimetypes
                file_mime_type, _ = mimetypes.guess_type(file_path)
                if not file_mime_type:
                    if file_type == FileType.PDF.value:
                        file_mime_type = "application/pdf"
                    elif file_type == FileType.IMAGE.value:
                        # Determine image type from extension
                        ext = os.path.splitext(file_path)[1].lower()
                        if ext == '.png':
                            file_mime_type = "image/png"
                        elif ext in ['.jpg', '.jpeg']:
                            file_mime_type = "image/jpeg"
                        else:
                            file_mime_type = "image/unknown"
                
                # Upload to S3
                upload_metadata = {
                    "user_id": str(user_id),
                    "file_type": file_type,
                    "original_filename": os.path.basename(file_path)
                }
                
                logger.info(f"Uploading invoice file to S3: {os.path.basename(file_path)} with mime type: {file_mime_type}")
                logger.info(f"File size: {os.path.getsize(file_path)} bytes")
                
                # Read file content again to ensure we have a fresh file handle
                with open(file_path, 'rb') as f:
                    fresh_file_content = f.read()
                
                # Always use real S3 regardless of test mode
                logger.info(f"Uploading to real AWS S3 bucket: {s3_handler.bucket_name}")
                
                # Proceed with actual S3 upload
                s3_result = s3_handler.upload_file(
                    file_content=fresh_file_content,
                    file_name=os.path.basename(file_path),
                    user_id=user_id,
                    content_type=file_mime_type,
                    file_type="invoices",
                    metadata=upload_metadata
                )
                
                # Store S3 metadata
                if s3_result and isinstance(s3_result, dict):
                    logger.info(f"File uploaded to S3 successfully: {s3_result.get('file_key')}")
                    s3_metadata = {
                        "file_key": s3_result.get("file_key"),
                        "url": s3_result.get("url"),
                        "bucket": s3_result.get("bucket")
                    }
                    logger.info(f"S3 metadata created: {s3_metadata}")
                else:
                    logger.error(f"S3 upload returned unexpected result: {s3_result}")
            except Exception as e:
                logger.exception(f"Error uploading file to S3: {str(e)}")
                # Continue with extraction even if S3 upload fails
        
        # Create an agent context with user ID if available
        agent_context = None
        if user_id:
            agent_context = AgentContext(
                user_id=str(user_id),
                conversation_history=conversation_history or []
            )
            
        # Create an AgentInput object
        agent_input = AgentInput(
            content=file_content,
            file_path=file_path,
            file_name=os.path.basename(file_path),
            content_type=file_type,
            metadata={"file_type": file_type, "input_type": file_type}
        )
        
        # Process with the properly constructed AgentInput object
        result = await agent.process(agent_input, agent_context)
        
        if not result:
            return {"error": "Could not extract data from the invoice"}
        
        if result.error:
            return {"error": result.error}
        
        # The content field contains the extracted data
        extracted_data = result.content
        logger.info(f"Successfully extracted invoice data: {extracted_data.keys() if isinstance(extracted_data, dict) else 'not a dict'}")
        
        # Create metadata with S3 information if available
        metadata = result.metadata or {}
        if s3_metadata:
            metadata["s3_storage"] = s3_metadata
            logger.info(f"Added S3 storage metadata to extraction result: {s3_metadata}")
        
        # Return a structure that includes both the data and any metadata
        return {
            "data": extracted_data,
            "file_type": file_type,
            "file_path": file_path,
            "metadata": metadata  # Include all metadata from the agent result, including S3 info
        }
        
    except Exception as e:
        logger.exception(f"Error extracting invoice data: {str(e)}")
        return {"error": f"Error extracting data: {str(e)}"}


async def format_extraction_response(
    extraction_result: Dict[str, Any],
    file_name: str
) -> Dict[str, Any]:
    """
    Format the extraction results into a user-friendly response.
    
    Args:
        extraction_result: The extraction results
        file_name: Original filename
        
    Returns:
        Dict containing the formatted response
    """
    llm_factory = LLMFactory()
    agent = ResponseFormatterAgent(llm_factory=llm_factory)
    
    # Check for S3 storage metadata
    s3_storage = None
    if "metadata" in extraction_result and "s3_storage" in extraction_result["metadata"]:
        s3_storage = extraction_result["metadata"]["s3_storage"]
    
    # Get the invoice data
    invoice_data = extraction_result.get("data", {})
    
    # Check for sample data flag in the raw extraction metadata
    is_sample_data = False
    
    # Check if this is sample data
    if "file_path" in extraction_result and isinstance(invoice_data, dict):
        file_path = extraction_result.get("file_path", "")
        if "is_sample_data" in extraction_result:
            is_sample_data = extraction_result.get("is_sample_data", False)
        # Also check the data directly, which might come from the DataExtractorAgent
        elif "metadata" in extraction_result and isinstance(extraction_result["metadata"], dict):
            is_sample_data = extraction_result["metadata"].get("is_sample_data", False)
    
    # Use a specialized function to create a formatted response from the invoice data
    def create_formatted_response(data, s3_url=None):
        vendor = data.get("vendor", {})
        vendor_name = vendor.get("name", "Unknown Vendor") if isinstance(vendor, dict) else vendor
        
        transaction = data.get("transaction", {})
        invoice_number = transaction.get("invoice_number", "Unknown") if isinstance(transaction, dict) else None
        date = transaction.get("date", "Unknown Date") if isinstance(transaction, dict) else data.get("date", "Unknown Date")
        due_date = transaction.get("due_date", "Unknown") if isinstance(transaction, dict) else data.get("due_date", "Unknown")
        
        financial = data.get("financial", {})
        if isinstance(financial, dict):
            total = financial.get("total", 0)
            currency = financial.get("currency", "USD")
        else:
            total = data.get("total_amount", 0)
            currency = data.get("currency", "USD")
        
        items = data.get("items", [])
        
        items_text = ""
        if items and len(items) > 0:
            items_text = "\n\n📋 Items:"
            for item in items:
                if not isinstance(item, dict):
                    continue
                description = item.get("description", "Item")
                quantity = item.get("quantity", 1)
                unit_price = item.get("unit_price", 0)
                total_price = item.get("total_price", 0)
                items_text += f"\n- {description}: {quantity} x {unit_price} {currency} = {total_price} {currency}"
        
        response = f"✅ I've successfully processed your invoice from {file_name}!\n\n"
        response += f"🏢 Vendor: {vendor_name}\n"
        if invoice_number:
            response += f"📝 Invoice #{invoice_number}\n"
        response += f"💰 Total: {total} {currency}\n"
        if date and date != "Unknown Date":
            response += f"📅 Dated: {date}\n"
        if due_date and due_date != "Unknown":
            response += f"⏱️ Due by: {due_date}"
        response += items_text
        
        # Add S3 link if available
        if s3_url:
            response += f"\n\n🔗 Your invoice has been saved and is available here."
        
        return response
    
    # For sample data, use a templated response
    if is_sample_data:
        logger.info(f"Using templated response for sample invoice data")
        s3_url = s3_storage.get("url") if s3_storage else None
        response = create_formatted_response(invoice_data, s3_url)
        
        return {
            "content": response,
            "confidence": 0.9
        }
    
    # Create a proper AgentInput object with S3 storage info if available
    metadata = {
        "intent": IntentType.FILE_PROCESSING.value,
        "extraction_result": extraction_result,
        "file_name": file_name,
        "response_type": "invoice_summary"  # Specify the type of response we want
    }
    
    if s3_storage:
        metadata["s3_storage"] = s3_storage
    
    agent_input = AgentInput(
        content="Format invoice extraction response",
        metadata=metadata
    )
    
    try:
        # First attempt with the ResponseFormatterAgent
        result = await agent.process(agent_input)
        
        # Only proceed if we got some response content
        if result and hasattr(result, "content") and result.content:
            # Validate the response quality using LLM-based validation
            validation_context = {
                "invoice_data": invoice_data,
                "has_s3_storage": s3_storage is not None
            }
            
            validation_result = await llm_factory.validate_response(
                response_content=result.content,
                response_type="invoice_summary",
                context=validation_context
            )
            
            # Check if the response is valid based on validation results
            if validation_result.get("is_valid", False) and validation_result.get("confidence", 0) >= 0.6:
                logger.info(f"Response validation successful: {validation_result.get('confidence')}")
                return {
                    "content": result.content,
                    "confidence": result.confidence
                }
            else:
                # Log why validation failed
                issues = validation_result.get("issues", [])
                logger.warning(f"Response validation failed: {', '.join(issues)}")
        else:
            logger.warning("ResponseFormatterAgent returned no content")

        # If validation failed or no content was returned, use our fallback formatter
        s3_url = s3_storage.get("url") if s3_storage else None
        response = create_formatted_response(invoice_data, s3_url)
        
        return {
            "content": response,
            "confidence": 0.8
        }
        
    except Exception as e:
        logger.exception(f"Error formatting extraction response: {str(e)}")
        
        # Create a response using our helper function as fallback
        s3_url = s3_storage.get("url") if s3_storage else None
        response = create_formatted_response(invoice_data, s3_url)
        
        return {
            "content": response,
            "confidence": 0.7
        }


async def format_invalid_file_response(
    validation_result: Dict[str, Any],
    file_name: str
) -> Dict[str, Any]:
    """
    Format response for invalid files.
    
    Args:
        validation_result: Validation results containing error reason
        file_name: Original filename
        
    Returns:
        Dict containing the formatted response
    """
    llm_factory = LLMFactory()
    agent = ResponseFormatterAgent(llm_factory=llm_factory)
    
    # Create a proper AgentInput object
    agent_input = AgentInput(
        content="Format invalid file response",
        metadata={
            "intent": IntentType.FILE_PROCESSING.value,
            "validation_result": validation_result,
            "file_name": file_name,
            "response_type": "error",  # Specify the type of response we want
            "error_type": "file_validation_error"  # Provide more context for the formatter
        }
    )
    
    try:
        # Generate response with the formatter agent
        result = await agent.process(agent_input)
        
        # Only proceed if we got some response content
        if result and hasattr(result, "content") and result.content:
            # Validate the response quality using LLM-based validation
            validation_context = {
                "validation_result": validation_result,
                "error_reason": validation_result.get("reason", "Unknown error"),
                "file_name": file_name
            }
            
            validation_result = await llm_factory.validate_response(
                response_content=result.content,
                response_type="error",
                context=validation_context
            )
            
            # Check if the response is valid based on validation results
            if validation_result.get("is_valid", False) and validation_result.get("confidence", 0) >= 0.6:
                logger.info(f"Error response validation successful: {validation_result.get('confidence')}")
                return {
                    "content": result.content,
                    "confidence": result.confidence
                }
            else:
                # Log why validation failed
                issues = validation_result.get("issues", [])
                logger.warning(f"Error response validation failed: {', '.join(issues)}")
        else:
            logger.warning("ResponseFormatterAgent returned no content for error response")
        
        # Fallback response if formatter failed or validation failed
        reason = validation_result.get("reason", "Unknown error")
        response = FILE_PROCESSING_FALLBACKS["invalid_file"]
        
        return {
            "content": response,
            "confidence": 0.6
        }
        
    except Exception as e:
        logger.exception(f"Error formatting invalid file response: {str(e)}")
        return {
            "content": FILE_PROCESSING_FALLBACKS["invalid_file"],
            "metadata": {"intent": IntentType.FILE_PROCESSING.value, "success": False},
            "confidence": 0.5
        }


async def format_unsupported_format_response(
    file_name: str,
    file_type: str
) -> Dict[str, Any]:
    """
    Format response for valid but unsupported file formats.
    
    Args:
        file_name: Original filename
        file_type: File type
        
    Returns:
        Dict containing the formatted response
    """
    llm_factory = LLMFactory()
    agent = ResponseFormatterAgent(llm_factory=llm_factory)
    
    # Create a proper AgentInput object
    agent_input = AgentInput(
        content="Format unsupported format response",
        metadata={
            "intent": IntentType.FILE_PROCESSING.value,
            "file_name": file_name,
            "file_type": file_type,
            "response_type": "error",  # Specify the type of response
            "error_type": "unsupported_file_format",  # Categorize the error type
            "suggestion": "Please upload an invoice file (PDF, image, Excel, or CSV)."
        }
    )
    
    try:
        # Generate response with the formatter agent
        result = await agent.process(agent_input)
        
        # Only proceed if we got some response content
        if result and hasattr(result, "content") and result.content:
            # Validate the response quality using LLM-based validation
            validation_context = {
                "file_type": file_type,
                "file_name": file_name,
                "expected_formats": ["PDF", "image", "Excel", "CSV"]
            }
            
            validation_result = await llm_factory.validate_response(
                response_content=result.content,
                response_type="error",
                context=validation_context
            )
            
            # Check if the response is valid based on validation results
            if validation_result.get("is_valid", False) and validation_result.get("confidence", 0) >= 0.6:
                logger.info(f"Unsupported format response validation successful: {validation_result.get('confidence')}")
                return {
                    "content": result.content,
                    "confidence": result.confidence
                }
            else:
                # Log why validation failed
                issues = validation_result.get("issues", [])
                logger.warning(f"Unsupported format response validation failed: {', '.join(issues)}")
        else:
            logger.warning("ResponseFormatterAgent returned no content for unsupported format response")
        
        # Fallback response if formatter failed or validation failed
        response = FILE_PROCESSING_FALLBACKS["unsupported_format"]
        
        return {
            "content": response,
            "confidence": 0.6
        }
        
    except Exception as e:
        logger.exception(f"Error formatting unsupported format response: {str(e)}")
        return {
            "content": FILE_PROCESSING_FALLBACKS["unsupported_format"],
            "metadata": {"intent": IntentType.FILE_PROCESSING.value, "success": False},
            "confidence": 0.5
        } 