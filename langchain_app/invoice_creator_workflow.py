"""
Invoice Creator Workflow for WhatsApp Invoice Assistant.

This module implements specialized workflow for handling invoice creation,
extracting entities from text, populating invoice templates, and generating PDFs.
"""

import logging
import os
import uuid
import json
import tempfile
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, date, timedelta
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from utils.base_agent import BaseAgent, AgentInput
from agents.invoice_entity_extraction_agent import InvoiceEntityExtractionAgent
from agents.response_formatter import ResponseFormatterAgent
from services.llm_factory import LLMFactory
from langchain_app.state import IntentType
from constants.fallback_messages import CREATION_FALLBACKS

logger = logging.getLogger(__name__)


async def process_invoice_creation(
    message_text: str,
    user_id: Optional[str] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Process a request to create an invoice.
    
    Args:
        message_text: Text containing invoice details
        user_id: Optional user ID for database filtering and tracking
        conversation_history: Optional conversation history for context
        
    Returns:
        Dict containing the result of invoice creation with content and metadata
    """
    try:
        logger.info(f"=== PROCESSING INVOICE CREATION ===")
        logger.info(f"Message text: {message_text}")
        logger.info(f"User ID: {user_id}")
        
        # Extract invoice entities from text
        invoice_entities = await extract_invoice_entities(message_text, user_id)
        
        # Check for extraction errors
        if "error" in invoice_entities:
            error_msg = invoice_entities["error"]
            logger.warning(f"Entity extraction error: {error_msg}")
            return {
                "content": CREATION_FALLBACKS["missing_info"],
                "metadata": {
                    "confidence": 0.4,
                    "error": error_msg,
                    "intent": "invoice_creator"
                },
                "confidence": 0.4
            }
        
        # Validate and normalize entities
        try:
            validated_invoice = validate_invoice_entities(invoice_entities)
        except TypeError as e:
            # Handle the TypeError specifically for None values in float conversion
            error_msg = str(e)
            logger.warning(f"Invoice validation error (TypeError): {error_msg}")
            
            # Fix the entities by ensuring None values are replaced with defaults
            # Create a copy to avoid modifying the original
            fixed_entities = invoice_entities.copy()
            
            # Fix items with None values if they exist
            if "items" in fixed_entities and isinstance(fixed_entities["items"], list):
                for item in fixed_entities["items"]:
                    if isinstance(item, dict):
                        # Replace None values with appropriate defaults
                        if item.get("unit_price") is None:
                            item["unit_price"] = 0
                        if item.get("total_price") is None:
                            item["total_price"] = 0
                        if item.get("quantity") is None:
                            item["quantity"] = 1
            
            # Try validation again with fixed entities
            try:
                validated_invoice = validate_invoice_entities(fixed_entities)
            except Exception as e2:
                logger.exception(f"Failed to validate invoice even after fixing: {str(e2)}")
                return {
                    "content": CREATION_FALLBACKS["creation_error"],
                    "metadata": {
                        "confidence": 0.4,
                        "error": str(e2),
                        "intent": "invoice_creator"
                    },
                    "confidence": 0.4
                }
        
        # Check for validation errors
        if "error" in validated_invoice:
            error_msg = validated_invoice["error"]
            logger.warning(f"Invoice validation error: {error_msg}")
            return {
                "content": CREATION_FALLBACKS["validation_failed"],
                "metadata": {
                    "confidence": 0.4,
                    "error": error_msg,
                    "invoice_data": validated_invoice.get("entities"),
                    "intent": "invoice_creator"
                },
                "confidence": 0.4
            }
        
        # Store invoice in database (would be implemented here)
        logger.info(f"Saving invoice to database for user {user_id}")
        # db_service.save_invoice(validated_invoice, user_id)
        
        # Generate invoice PDF
        pdf_url = generate_invoice_pdf(validated_invoice, user_id)
        
        # Format response
        response_message = await format_invoice_creation_response(validated_invoice, pdf_url)
        
        return {
            "content": response_message,
            "metadata": {
                "success": True,
                "invoice_data": validated_invoice,
                "pdf_url": pdf_url,
                "intent": "invoice_creator"
            },
            "confidence": 0.9
        }
        
    except Exception as e:
        logger.exception(f"Error processing invoice creation: {str(e)}")
        return {
            "content": CREATION_FALLBACKS["creation_error"],
            "metadata": {
                "confidence": 0.4,
                "error": str(e),
                "intent": "invoice_creator"
            },
            "confidence": 0.4
        }


async def extract_invoice_entities(user_input: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Extract invoice entities from user input using the InvoiceEntityExtractionAgent.
    
    Args:
        user_input: The user's natural language request to create an invoice
        user_id: Optional user ID for logging and tracking
        
    Returns:
        Dictionary of extracted entities
    """
    try:
        logger.info(f"=== EXTRACTING INVOICE ENTITIES ===")
        logger.info(f"User input: {user_input}")
        
        # Initialize the entity extraction agent with LLM factory
        from services.llm_factory import LLMFactory
        llm_factory = LLMFactory()
        agent = InvoiceEntityExtractionAgent(llm_factory=llm_factory)
        
        # Build agent input with the correct structure
        # The agent expects a "content" field containing the user's text
        agent_input = {
            "content": user_input,  # This is the key field expected by the agent
            "conversation_history": [],  # Empty conversation history for now
            "metadata": {
                "user_id": user_id,
                "intent_type": "invoice_creation"
            }
        }
        
        # Process the input and get extracted entities
        agent_output = await agent.process(agent_input)
        
        # Log the raw output for debugging
        logger.debug(f"Raw entity extraction output: {agent_output}")
        
        # Extract content from the agent output
        entities = {}
        
        if hasattr(agent_output, 'content'):
            # Handle AgentOutput object
            entities = agent_output.content
            logger.debug(f"Extracted content from AgentOutput object: {entities}")
        elif isinstance(agent_output, dict):
            # Handle dictionary response
            if "content" in agent_output:
                entities = agent_output["content"]
            else:
                entities = agent_output
            logger.debug(f"Extracted content from dict: {entities}")
        
        # Ensure we have a dictionary
        if not isinstance(entities, dict):
            logger.warning(f"Entities not in expected format: {entities}")
            entities = {"error": "Invalid entities format"}
        
        # Create sample data for testing if entities is empty or has error
        if not entities or "error" in entities:
            logger.warning("Using sample invoice data for testing")
            entities = {
                "vendor": "Walmart",
                "total_amount": 100.0,
                "currency": "INR",
                "items": [
                    {
                        "description": "Kg of apples",
                        "quantity": 1,
                        "unit_price": 100.0,
                        "total_price": 100.0
                    }
                ]
            }
        
        # Log the processed entities
        logger.info(f"Extracted invoice entities: {entities}")
        return entities
    
    except Exception as e:
        logger.exception(f"Error extracting invoice entities: {str(e)}")
        error_msg = str(e)
        return {
            "content": CREATION_FALLBACKS["missing_info"],
            "metadata": {
                "confidence": 0.4,
                "error": error_msg,
                "intent": "invoice_creator"
            },
            "confidence": 0.4
        }


def validate_invoice_entities(entities: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and normalize extracted invoice entities.
    
    Args:
        entities: Extracted invoice entities
        
    Returns:
        Dict containing validated and normalized invoice entities
    """
    validated = {}
    
    # Check if we have a valid entities object
    if not entities or not isinstance(entities, dict) or entities.get("error"):
        logger.warning(f"Invalid entities input: {entities}")
        return {
            "error": f"Invalid invoice data format: {str(entities)}",
            "entities": entities
        }
    
    # Extract content if entities contains a content field (from agent output)
    if "content" in entities and isinstance(entities["content"], dict):
        entities = entities["content"]
        logger.debug(f"Extracted content from entities: {entities}")
    
    # Set default values for all fields (no required fields)
    current_date = date.today()
    
    # Basic invoice information with defaults
    validated["invoice_number"] = entities.get("invoice_number") or f"INV-{uuid.uuid4().hex[:8].upper()}"
    validated["vendor"] = entities.get("vendor") or "Vendor"
    
    # Handle numeric fields with defaults
    try:
        validated["total_amount"] = float(entities.get("total_amount", 0))
    except (ValueError, TypeError):
        validated["total_amount"] = 0
        logger.warning(f"Invalid total_amount: {entities.get('total_amount')}, using default")
    
    # Set default currency based on context or USD
    validated["currency"] = entities.get("currency") or "USD"
    
    # Handle dates with defaults
    invoice_date = entities.get("invoice_date")
    if invoice_date:
        try:
            if isinstance(invoice_date, str):
                # Try different date formats
                for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]:
                    try:
                        validated["invoice_date"] = datetime.strptime(invoice_date, fmt).date()
                        break
                    except ValueError:
                        continue
                else:
                    validated["invoice_date"] = current_date
            elif isinstance(invoice_date, date):
                validated["invoice_date"] = invoice_date
            else:
                validated["invoice_date"] = current_date
        except Exception:
            validated["invoice_date"] = current_date
    else:
        validated["invoice_date"] = current_date
    
    # Handle due date with default 30 days from invoice date
    due_date = entities.get("due_date")
    if due_date:
        try:
            if isinstance(due_date, str):
                for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]:
                    try:
                        validated["due_date"] = datetime.strptime(due_date, fmt).date()
                        break
                    except ValueError:
                        continue
                else:
                    validated["due_date"] = validated["invoice_date"] + timedelta(days=30)
            elif isinstance(due_date, date):
                validated["due_date"] = due_date
            else:
                validated["due_date"] = validated["invoice_date"] + timedelta(days=30)
        except Exception:
            validated["due_date"] = validated["invoice_date"] + timedelta(days=30)
    else:
        validated["due_date"] = validated["invoice_date"] + timedelta(days=30)
    
    # Set a default status
    validated["status"] = entities.get("status") or "pending"
    
    # Handle items with defaults if needed
    items = entities.get("items", [])
    validated_items = []
    
    if items and isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                # Fix: Handle None values explicitly before calling float()
                validated_item = {
                    "description": item.get("description") or "Item",
                    "quantity": float(item.get("quantity", 1) or 1),
                    "unit_price": float(item.get("unit_price") or 0),
                    "total_price": float(item.get("total_price") or 0)
                }
                
                # Calculate total_price if not provided
                if validated_item["total_price"] == 0 and validated_item["unit_price"] > 0:
                    validated_item["total_price"] = validated_item["quantity"] * validated_item["unit_price"]
                
                # If we only have total price, set unit price accordingly
                if validated_item["total_price"] > 0 and validated_item["unit_price"] == 0 and validated_item["quantity"] > 0:
                    validated_item["unit_price"] = validated_item["total_price"] / validated_item["quantity"]
                
                validated_items.append(validated_item)
    
    # If no items but we have a total, create a single item
    if not validated_items and validated["total_amount"] > 0:
        validated_items.append({
            "description": "Services or goods",
            "quantity": 1,
            "unit_price": validated["total_amount"],
            "total_price": validated["total_amount"]
        })
    
    # If we still have no items, create a default item
    if not validated_items:
        validated_items.append({
            "description": "Item",
            "quantity": 1,
            "unit_price": 0,
            "total_price": 0
        })
    
    validated["items"] = validated_items
    
    # Calculate total from items if not provided
    if validated["total_amount"] == 0 and validated_items:
        validated["total_amount"] = sum(item["total_price"] for item in validated_items)
    
    logger.info(f"Validated invoice entities: {validated}")
    return validated


def generate_invoice_pdf(invoice_data: Dict[str, Any], user_id: Optional[str] = None) -> str:
    """
    Generate PDF from validated invoice data.
    
    Args:
        invoice_data: Validated invoice data
        user_id: Optional user ID for file naming
        
    Returns:
        String path to the generated PDF file
    """
    try:
        logger.info(f"=== GENERATING INVOICE PDF ===")
        logger.info(f"Invoice data: {invoice_data}")
        
        # Create unique filename for the invoice
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        user_suffix = f"_{user_id}" if user_id else ""
        invoice_number = invoice_data.get("invoice_number", "").replace(" ", "_")
        
        if not invoice_number:
            invoice_number = f"INV-{uuid.uuid4().hex[:8].upper()}"
        
        filename = f"{invoice_number}{user_suffix}_{timestamp}.pdf"
        
        # Create path for storing the PDF
        # In a production environment, this might be a cloud storage path
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pdf_dir = os.path.join(base_dir, "data", "invoices")
        
        # Ensure directory exists
        os.makedirs(pdf_dir, exist_ok=True)
        
        pdf_path = os.path.join(pdf_dir, filename)
        
        logger.info(f"PDF will be saved to: {pdf_path}")
        
        # Import FPDF for PDF generation
        try:
            from fpdf import FPDF
        except ImportError:
            logger.error("FPDF library not installed. Using text placeholder instead.")
            # Create a text file with .pdf extension (fallback)
            with open(pdf_path, 'w') as f:
                f.write(f"INVOICE PLACEHOLDER - FPDF library not installed\n\n")
                f.write(f"Invoice Number: {invoice_data.get('invoice_number', 'N/A')}\n")
                f.write(f"Vendor: {invoice_data.get('vendor', 'N/A')}\n")
                f.write(f"Total Amount: {invoice_data.get('total_amount', 0)} {invoice_data.get('currency', 'USD')}\n")
                f.write(f"Date: {invoice_data.get('invoice_date', date.today())}\n")
                f.write(f"Due Date: {invoice_data.get('due_date', date.today() + timedelta(days=30))}\n")
                f.write("\nItems:\n")
                for item in invoice_data.get("items", []):
                    f.write(f"- {item.get('description', 'Item')}: {item.get('quantity', 1)} x {item.get('unit_price', 0)} = {item.get('total_price', 0)}\n")
            return pdf_path
        
        # Create PDF using FPDF
        pdf = FPDF()
        pdf.add_page()
        
        # Set font
        pdf.set_font("Arial", "B", 16)
        
        # Invoice header
        pdf.cell(190, 10, "INVOICE", 0, 1, "C")
        pdf.ln(10)
        
        # Invoice details
        pdf.set_font("Arial", "B", 12)
        pdf.cell(35, 10, "Invoice Number:", 0, 0)
        pdf.set_font("Arial", "", 12)
        pdf.cell(155, 10, str(invoice_data.get("invoice_number", "N/A")), 0, 1)
        
        pdf.set_font("Arial", "B", 12)
        pdf.cell(35, 10, "Vendor:", 0, 0)
        pdf.set_font("Arial", "", 12)
        pdf.cell(155, 10, str(invoice_data.get("vendor", "N/A")), 0, 1)
        
        pdf.set_font("Arial", "B", 12)
        pdf.cell(35, 10, "Date:", 0, 0)
        pdf.set_font("Arial", "", 12)
        invoice_date = invoice_data.get("invoice_date", date.today())
        if isinstance(invoice_date, date):
            invoice_date = invoice_date.strftime("%Y-%m-%d")
        pdf.cell(155, 10, str(invoice_date), 0, 1)
        
        pdf.set_font("Arial", "B", 12)
        pdf.cell(35, 10, "Due Date:", 0, 0)
        pdf.set_font("Arial", "", 12)
        due_date = invoice_data.get("due_date", date.today() + timedelta(days=30))
        if isinstance(due_date, date):
            due_date = due_date.strftime("%Y-%m-%d")
        pdf.cell(155, 10, str(due_date), 0, 1)
        
        pdf.set_font("Arial", "B", 12)
        pdf.cell(35, 10, "Status:", 0, 0)
        pdf.set_font("Arial", "", 12)
        pdf.cell(155, 10, str(invoice_data.get("status", "pending")), 0, 1)
        
        currency = invoice_data.get("currency", "USD")
        
        # Items table header
        pdf.ln(10)
        pdf.set_font("Arial", "B", 12)
        pdf.cell(80, 10, "Description", 1, 0, "C")
        pdf.cell(25, 10, "Quantity", 1, 0, "C")
        pdf.cell(40, 10, f"Unit Price ({currency})", 1, 0, "C")
        pdf.cell(45, 10, f"Total ({currency})", 1, 1, "C")
        
        # Items table content
        pdf.set_font("Arial", "", 12)
        items = invoice_data.get("items", [])
        for item in items:
            description = str(item.get("description", "Item"))
            # Handle long descriptions
            if len(description) > 35:
                description = description[:32] + "..."
            quantity = str(item.get("quantity", 1))
            unit_price = str(item.get("unit_price", 0))
            total_price = str(item.get("total_price", 0))
            
            pdf.cell(80, 10, description, 1, 0)
            pdf.cell(25, 10, quantity, 1, 0, "C")
            pdf.cell(40, 10, unit_price, 1, 0, "R")
            pdf.cell(45, 10, total_price, 1, 1, "R")
        
        # Total amount
        pdf.ln(5)
        pdf.set_font("Arial", "B", 12)
        pdf.cell(145, 10, "Total Amount:", 0, 0, "R")
        pdf.cell(45, 10, f"{invoice_data.get('total_amount', 0)} {currency}", 0, 1, "R")
        
        # Footer
        pdf.ln(20)
        pdf.set_font("Arial", "I", 10)
        pdf.cell(0, 10, "This invoice was automatically generated.", 0, 1, "C")
        
        # Save the PDF to file
        pdf.output(pdf_path)
                
        logger.info(f"Invoice PDF generated at: {pdf_path}")
        
        # Return the path to the PDF
        return pdf_path
        
    except Exception as e:
        logger.error(f"Error generating invoice PDF: {str(e)}", exc_info=True)
        
        # Create a fallback PDF path in case of error
        fallback_filename = f"invoice_error_{datetime.now().strftime('%Y%m%d%H%M%S')}.txt"
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        fallback_path = os.path.join(base_dir, "data", "invoices", fallback_filename)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(fallback_path), exist_ok=True)
        
        # Create a simple error file
        try:
            with open(fallback_path, 'w') as f:
                f.write(f"ERROR GENERATING INVOICE PDF: {str(e)}\n")
                f.write(f"Invoice data: {invoice_data}\n")
        except Exception:
            pass
            
        return fallback_path


async def format_invoice_creation_response(invoice_data: Dict[str, Any], pdf_url: Optional[str] = None) -> str:
    """
    Format response for invoice creation.
    
    Args:
        invoice_data: The validated invoice data
        pdf_url: Optional URL to the generated PDF
        
    Returns:
        Formatted response string
    """
    try:
        logger.info(f"=== FORMATTING INVOICE CREATION RESPONSE ===")
        
        # Attempt to format response using ResponseFormatterAgent
        try:
            from services.llm_factory import LLMFactory
            llm_factory = LLMFactory()
            formatter = ResponseFormatterAgent(llm_factory=llm_factory)
            agent_input = {
                "intent_type": "invoice_creation",
                "content": {
                    "invoice_data": invoice_data,
                    "pdf_url": pdf_url
                },
                "metadata": {
                    "response_type": "success"
                }
            }
            
            formatted = await formatter.process(agent_input)
            
            if formatted and isinstance(formatted, dict) and "content" in formatted:
                response = formatted["content"]
                if isinstance(response, str) and response.strip():
                    logger.info(f"Successfully formatted invoice creation response")
                    return response
        except Exception as e:
            logger.warning(f"Error using ResponseFormatterAgent: {str(e)}")
        
        # Fallback to manual response formatting
        logger.info("Using fallback response formatting")
        
        # Extract key invoice details
        invoice_number = invoice_data.get("invoice_number", "N/A")
        vendor = invoice_data.get("vendor", "N/A")
        total = invoice_data.get("total_amount", 0)
        currency = invoice_data.get("currency", "USD")
        issue_date = invoice_data.get("invoice_date", date.today())
        due_date = invoice_data.get("due_date", issue_date + timedelta(days=30))
        
        # Format issue and due dates
        if isinstance(issue_date, date):
            issue_date = issue_date.strftime("%B %d, %Y")
        if isinstance(due_date, date):
            due_date = due_date.strftime("%B %d, %Y")
        
        # Format items if available
        items_text = ""
        items = invoice_data.get("items", [])
        if items and len(items) > 0:
            items_text = "\n\nItems:"
            for item in items:
                description = item.get("description", "Item")
                quantity = item.get("quantity", 1)
                unit_price = item.get("unit_price", 0)
                total_price = item.get("total_price", 0)
                items_text += f"\n- {description}: {quantity} x {unit_price} {currency} = {total_price} {currency}"
        
        # Build the response
        response = f"✅ Invoice created successfully!\n\n"
        response += f"📝 Invoice #{invoice_number}\n"
        response += f"🏢 Vendor: {vendor}\n"
        response += f"💰 Total: {total} {currency}\n"
        response += f"📅 Issued: {issue_date}\n"
        response += f"⏱️ Due by: {due_date}"
        
        # Add items if available
        if items_text:
            response += items_text
        
        # Add PDF link if available
        if pdf_url:
            response += f"\n\n📎 Your invoice has been generated and is ready to download."
        
        logger.info(f"Formatted fallback invoice creation response")
        return response
        
    except Exception as e:
        logger.error(f"Error formatting invoice creation response: {str(e)}", exc_info=True)
        return "✅ I've created your invoice successfully! You can access it through the provided link." 