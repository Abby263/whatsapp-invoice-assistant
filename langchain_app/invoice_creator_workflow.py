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
from services.user_data_service import enrich_invoice_data
from services.invoice_template_service import generate_invoice, check_missing_fields, TEMPLATE_TYPES

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
            try:
                validated_invoice = validate_invoice_entities(invoice_entities, user_id)
            except TypeError as e:
                if "positional" not in str(e):
                    raise
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
                try:
                    validated_invoice = validate_invoice_entities(fixed_entities, user_id)
                except TypeError as e3:
                    if "positional" not in str(e3):
                        raise
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

        generated_invoice = None
        pdf_url = None
        if user_id:
            from services.generated_invoice_service import generate_and_persist_invoice

            generated_invoice = generate_and_persist_invoice(
                validated_invoice,
                user_id=int(user_id),
                source="whatsapp_chat",
            )
            pdf_url = (
                generated_invoice.get("pdf_url")
                or generated_invoice.get("document_url")
            )
        else:
            logger.warning("No user_id provided; generating invoice without persistence")
            pdf_url = generate_invoice_pdf(validated_invoice, user_id)

        # Format response
        response_payload = await format_invoice_creation_response(validated_invoice, pdf_url)
        if isinstance(response_payload, dict):
            response_message = response_payload.get("content", "")
            response_confidence = response_payload.get("confidence", 0.9)
        else:
            response_message = response_payload
            response_confidence = 0.9

        return {
            "content": response_message,
            "metadata": {
                "success": True,
                "invoice": validated_invoice,
                "invoice_data": validated_invoice,
                "generated_invoice": generated_invoice,
                "pdf_path": pdf_url,
                "pdf_url": pdf_url,
                "intent": "invoice_creator"
            },
            "confidence": response_confidence
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

        # Always use default invoice type - no need for detection
        invoice_type = "default"
        logger.info(f"Using default invoice type for all invoices")

        # Build agent input with the correct structure
        # The agent expects a "content" field containing the user's text
        agent_input = {
            "content": user_input,  # This is the key field expected by the agent
            "conversation_history": [],  # Empty conversation history for now
            "metadata": {
                "user_id": user_id,
                "intent_type": "invoice_creation",
                "invoice_type": invoice_type
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

        # Explicitly set invoice_type to default in entities
        entities["invoice_type"] = invoice_type
        logger.info(f"Set invoice_type to 'default' in entities")

        # Extract relevant information from the user message if entities is missing important data
        # This is real extraction, not sample data
        if not entities.get("items"):
            # Try to find item quantity and unit price in the message
            import re

            # Look for quantity and price patterns (e.g., "10 Kg of apples at 10 Rs Kg")
            quantity_match = re.search(r'(\d+)\s*(?:kg|piece|pcs|items?|units?)?', user_input.lower())
            price_match = re.search(r'(?:at|for|price)\s*(\d+)\s*(?:rs|inr|usd|\$|rupees)', user_input.lower())

            if quantity_match and price_match:
                quantity = float(quantity_match.group(1))
                unit_price = float(price_match.group(1))

                # Extract item description - look for terms around the quantity
                description_match = re.search(r'of\s+([a-z\s]+)(?:at|for)', user_input.lower())
                description = description_match.group(1).strip() if description_match else "items"

                # Calculate total price
                total_price = quantity * unit_price

                # Look for currency
                currency_match = re.search(r'(rs|inr|usd|\$|rupees)', user_input.lower())
                currency = currency_match.group(1).upper() if currency_match else "INR"
                if currency.upper() == "RS" or currency.upper() == "RUPEES":
                    currency = "INR"
                elif currency == "$":
                    currency = "USD"

                # Create a proper item
                entities["items"] = [{
                    "description": description,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "total_price": total_price
                }]

                # Set the total amount and currency
                entities["total_amount"] = total_price
                entities["currency"] = currency

                logger.info(f"Extracted item info from message: {entities['items']}")

        # Log the processed entities
        logger.info(f"Extracted invoice entities: {entities}")
        return entities

    except Exception as e:
        logger.exception(f"Error extracting invoice entities: {str(e)}")
        error_msg = str(e)
        return {
            "error": error_msg
        }


def validate_invoice_entities(entities: Dict[str, Any], user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Validate and normalize extracted invoice entities.

    Args:
        entities: Extracted invoice entities
        user_id: Optional user ID to retrieve and use company profile data

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

    # Initialize with company profile data first if user_id is provided
    # This is important to do first so entity extraction data can override it if needed
    if user_id:
        try:
            from database.connection import get_db_session

            session = get_db_session()
            try:
                from services.user_data_service import get_user_data, get_invoice_defaults
                from database.schemas import User
                import json

                user = session.query(User).filter(User.id == int(user_id)).first()
                user_preferences = {}

                if user and hasattr(user, 'preferences') and user.preferences:
                    try:
                        if isinstance(user.preferences, str):
                            user_preferences = json.loads(user.preferences)
                        else:
                            user_preferences = user.preferences
                        logger.info(f"User preferences from database: {user_preferences}")
                    except Exception as e:
                        logger.error(f"Error parsing preferences JSON: {str(e)}")

                user_data = get_user_data(user_id, session)
                invoice_type = entities.get("invoice_type", "service_invoice")
                defaults = get_invoice_defaults(invoice_type, user_data)

                if defaults:
                    logger.info(f"Retrieved company profile defaults for user {user_id}")
                    validated = defaults.copy()

                    if 'company_name' in user_preferences:
                        validated['company_name'] = user_preferences['company_name']
                        logger.info(f"Using company_name from preferences: {validated['company_name']}")

                    for key in ['company_address', 'company_email', 'company_phone', 'company_website']:
                        if key in user_preferences:
                            validated[key] = user_preferences[key]
                            logger.info(f"Using {key} from preferences: {validated[key]}")

                    logger.info(f"Populated fields from user profile: {', '.join(defaults.keys())}")
                else:
                    logger.warning(f"No company profile data found for user {user_id}")
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"Failed to retrieve company profile: {str(e)}")

    # Set default values for required fields not in company profile
    current_date = date.today()

    # Basic invoice information with defaults
    validated["invoice_number"] = entities.get("invoice_number") or validated.get("invoice_number") or f"INV-{uuid.uuid4().hex[:8].upper()}"

    # Update vendor field to always match company_name
    if 'company_name' in validated and validated['company_name']:
        validated["vendor"] = validated['company_name']
    else:
        validated["vendor"] = entities.get("vendor") or validated.get("vendor", "")

    # Handle numeric fields with defaults
    try:
        validated["total_amount"] = float(entities.get("total_amount", validated.get("total_amount", 0)))
    except (ValueError, TypeError):
        validated["total_amount"] = 0
        logger.warning(f"Invalid total_amount: {entities.get('total_amount')}, using default")

    # Set default currency based on context or USD
    validated["currency"] = entities.get("currency") or validated.get("currency", "USD")

    # Handle dates with defaults
    invoice_date = entities.get("invoice_date", validated.get("invoice_date"))
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
    due_date = entities.get("due_date", validated.get("due_date"))
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
    validated["status"] = entities.get("status") or validated.get("status", "pending")

    # Ensure invoice_type is preserved
    validated["invoice_type"] = entities.get("invoice_type") or validated.get("invoice_type", "service_invoice")

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

    # Final check for any missing required fields - use default template
    # Updated to provide both required parameters
    template_info = TEMPLATE_TYPES["default"]
    missing_fields = check_missing_fields(template_info, validated)

    if missing_fields:
        logger.warning(f"Missing fields for default template: {missing_fields}")

    logger.info(f"Validated invoice entities: {validated}")
    return validated


def generate_invoice_pdf(invoice_data: Dict[str, Any], user_id: Optional[str] = None) -> str:
    """
    Generate PDF from validated invoice data using the default invoice template.

    Args:
        invoice_data: Validated invoice data
        user_id: Optional user ID for file naming

    Returns:
        String path to the generated PDF file
    """
    try:
        logger.info(f"=== GENERATING INVOICE PDF ===")
        logger.info(f"Invoice data: {invoice_data}")
        # Debug log to verify company name
        logger.info(f"COMPANY NAME BEING USED: '{invoice_data.get('company_name', 'None')}'")

        if not user_id:
            logger.warning("No user ID provided, proceeding without user data")

        # Get the absolute project directory path
        import sys
        from pathlib import Path
        base_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        # Always use 'default' as the invoice type (simplified approach)
        invoice_data["invoice_type"] = "default"
        logger.info(f"Using default invoice template for all invoices")

        # Ensure output directories exist
        output_dir = base_dir / "data" / "generated_invoices"
        os.makedirs(output_dir, exist_ok=True)

        # Make a copy of invoice_data to avoid modifying the original
        processed_data = invoice_data.copy()

        # Fix entity capitalization and normalization
        for key, value in processed_data.copy().items():
            if isinstance(value, str) and key not in ["invoice_date", "due_date", "status"]:
                if key in ["company_name", "client_name", "company_address", "client_address"] and value:
                    # Only maintain capitalization for names and addresses
                    processed_data[key] = value
                elif value and key not in ["email", "company_email", "client_email"]:
                    # Capitalize first letter of each word for other fields
                    processed_data[key] = value.title()

        # Try to enhance the invoice with user profile data
        try:
            logger.info(f"Enriching invoice data for user {user_id}")
            processed_data = enrich_invoice_data(processed_data, user_id)

            # Ensure necessary company and client fields are populated
            if not processed_data.get('company_address'):
                processed_data['company_address'] = "Street Address"

            if not processed_data.get('company_city'):
                processed_data['company_city'] = "City, ST ZIP Code"

            if not processed_data.get('company_tagline'):
                processed_data['company_tagline'] = "Your Company Slogan"

            if not processed_data.get('client_name'):
                # If we have a vendor name assume it's a client
                if processed_data.get('vendor') and processed_data['vendor'] != processed_data.get('company_name'):
                    processed_data['client_name'] = processed_data['vendor']
                    logger.info(f"Using vendor as client_name: {processed_data['vendor']}")
                else:
                    processed_data['client_name'] = "Client"
                    logger.warning("No client name found, using 'Client' - please update with actual client name")

            # Ensure client address fields are populated
            if not processed_data.get('client_address'):
                processed_data['client_address'] = "Street Address"

            if not processed_data.get('client_city'):
                processed_data['client_city'] = "City, ST ZIP Code"

            if not processed_data.get('client_phone'):
                processed_data['client_phone'] = "555-1234"

            if not processed_data.get('client_company'):
                processed_data['client_company'] = "Company Name"

            logger.info(f"Enhanced invoice data: {processed_data}")

        except Exception as e:
            logger.warning(f"Could not enhance invoice with additional profile data: {str(e)}")

        # Use the template-based invoice generation service
        logger.info(f"Generating invoice with default template")
        result = generate_invoice(processed_data)

        # Log the entire result for debugging
        logger.info(f"Generate invoice result: {result}")

        if not result.get("success", False):
            error_message = result.get('message', 'Unknown error')
            logger.error(f"Failed to generate invoice: {error_message}")

            # Create fallback filename
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            fallback_filename = f"invoice_error_{timestamp}.txt"
            fallback_path = base_dir / "data" / "invoices" / fallback_filename

            # Ensure directory exists
            os.makedirs(fallback_path.parent, exist_ok=True)

            # Create a simple error file
            with open(fallback_path, 'w') as f:
                f.write(f"ERROR GENERATING INVOICE: {error_message}\n")
                f.write(f"Invoice data: {processed_data}\n")

            return str(fallback_path)

        # Get PDF path from result
        pdf_path = result.get("pdf_path")

        # If no PDF was generated, use the document path
        if not pdf_path:
            logger.warning("No PDF was generated, using document path instead")
            doc_path = result.get("document_path", "")

            # Copy to UI uploads for visibility
            try:
                ui_uploads_dir = base_dir / "ui" / "uploads"
                os.makedirs(ui_uploads_dir, exist_ok=True)

                # Generate a unique filename with timestamp
                timestamp = int(datetime.now().timestamp())
                doc_name = Path(doc_path).name
                new_doc_path = ui_uploads_dir / f"invoice_{timestamp}_{doc_name}"

                import shutil
                shutil.copy2(doc_path, new_doc_path)
                logger.info(f"Copied document to UI uploads: {new_doc_path}")

                return str(new_doc_path)
            except Exception as e:
                logger.error(f"Error copying document to UI uploads: {str(e)}")
                return doc_path

        # IMPORTANT FIX: Create a proper PDF file if UI path is available
        ui_pdf_path = result.get("ui_pdf_path")
        if ui_pdf_path and os.path.exists(ui_pdf_path):
            logger.info(f"Using UI PDF path: {ui_pdf_path}")
            return str(ui_pdf_path)

        # Copy PDF to the UI uploads directory for visibility in the UI
        try:
            ui_uploads_dir = base_dir / "ui" / "uploads"
            os.makedirs(ui_uploads_dir, exist_ok=True)

            # Generate a unique filename with timestamp
            timestamp = int(datetime.now().timestamp())
            pdf_filename = f"invoice_{timestamp}.pdf"
            ui_pdf_path = ui_uploads_dir / pdf_filename

            import shutil
            shutil.copy2(pdf_path, ui_pdf_path)

            logger.info(f"Copied invoice PDF to UI uploads: {ui_pdf_path}")
            return str(ui_pdf_path)  # Return the UI path for visibility
        except Exception as e:
            logger.error(f"Error copying PDF to UI uploads: {str(e)}")

        logger.info(f"Invoice PDF generated at: {pdf_path}")
        return pdf_path

    except Exception as e:
        logger.error(f"Error generating invoice PDF: {str(e)}", exc_info=True)

        # Create a fallback file path in case of error
        base_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        fallback_filename = f"invoice_error_{datetime.now().strftime('%Y%m%d%H%M%S')}.txt"
        fallback_path = base_dir / "data" / "invoices" / fallback_filename

        # Ensure directory exists
        os.makedirs(fallback_path.parent, exist_ok=True)

        # Create a simple error file
        try:
            with open(fallback_path, 'w') as f:
                f.write(f"ERROR GENERATING INVOICE PDF: {str(e)}\n")
                f.write(f"Invoice data: {invoice_data}\n")

                # Add stack trace for debugging
                import traceback
                f.write("\n\nStack trace:\n")
                f.write(traceback.format_exc())
        except Exception:
            pass

        return str(fallback_path)


async def format_invoice_creation_response(invoice_data: Dict[str, Any], pdf_url: Optional[str] = None) -> str:
    """
    Format response for invoice creation.

    Args:
        invoice_data: The validated invoice data
        pdf_url: Optional URL to the generated document (DOCX or PDF)

    Returns:
        String message to display to the user
    """
    try:
        llm_factory = LLMFactory()
        agent = ResponseFormatterAgent(llm_factory=llm_factory)

        # Create an agent input with the invoice data for the response formatter
        agent_input = AgentInput(
            content="Format invoice creation success",
            metadata={
                "invoice_data": invoice_data,
                "pdf_url": pdf_url,
                "response_type": "invoice_creation"
            }
        )

        result = await agent.process(agent_input)
        if result and result.content:
            # If the agent returned a response but it doesn't include the document URL,
            # manually add the document link to the response
            if pdf_url and pdf_url not in result.content:
                doc_url = _document_link_from_path(pdf_url)
                # Add the document link to the response
                result.content += f"\n\n📄 <a href='{doc_url}' download class='btn btn-primary'>Download Invoice Document</a>"

            return result.content

        # If the agent fails, create a manual response
        # Get the invoice details for the response
        invoice_number = invoice_data.get("invoice_number", "Unknown")
        vendor = invoice_data.get("vendor", "Unknown vendor")
        total_amount = invoice_data.get("total_amount", 0)
        currency = invoice_data.get("currency", "USD")
        currency_symbol = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹"}.get(currency, currency)

        # Get the items for the response
        items_text = ""
        if "items" in invoice_data and invoice_data["items"]:
            for item in invoice_data["items"]:
                description = item.get("description", "Item")
                quantity = item.get("quantity", 1)
                unit_price = item.get("unit_price", 0)
                total_price = item.get("total_price", 0)
                items_text += f"\n- {description}: {quantity} x {unit_price} {currency} = {total_price} {currency}"

        # Format the success message with all the invoice details
        message = f"✅ *Invoice Created Successfully!*\n\n📄 Invoice #{invoice_number}\n🏢 Vendor: {vendor}\n💰 Total: {currency_symbol}{total_amount} {currency}\n\nItems:{items_text}"

        # Add template information
        template_info = f"\n\nYour company profile data was used to populate this invoice."
        message += template_info

        # Add the document URL to the message with a proper HTML link
        if pdf_url:
            doc_url = _document_link_from_path(pdf_url)
            # Add the document link to the response with formatting
            message += f"\n\n📄 <a href='{doc_url}' download class='btn btn-primary'>Download Invoice Document</a>"

        return message

    except Exception as e:
        logger.exception(f"Error formatting invoice creation response: {str(e)}")
        return CREATION_FALLBACKS["creation_success"]


def _document_link_from_path(path_or_url: str) -> str:
    """Return a browser-usable document link from a local path or URL."""

    if not path_or_url:
        return ""
    if path_or_url.startswith(("http://", "https://", "/")):
        return path_or_url
    return f"/uploads/{os.path.basename(path_or_url)}"


def check_missing_fields(enriched_data: Dict[str, Any], user_id: Optional[str] = None, db_session: Optional[Session] = None) -> Dict[str, Any]:
    """
    Check for missing fields in the invoice data and suggest actions.

    Args:
        enriched_data: The validated and enriched invoice data
        user_id: Optional user ID for accessing user data
        db_session: Optional database session for accessing user data

    Returns:
        Dict containing the response to the user
    """
    try:
        logger.info(f"=== CHECKING MISSING FIELDS ===")
        logger.info(f"Enriched data: {enriched_data}")

        # Check if there are still missing fields
        missing_fields = [field for field, value in enriched_data.items() if value is None or value == ""]

        # Check if there are any missing fields
        if not missing_fields:
            logger.info("No missing fields found")
            return {
                "content": "✅ I've created your invoice successfully! You can access it through the provided link.",
                "metadata": {
                    "confidence": 0.9,
                    "invoice_data": enriched_data,
                    "intent": "invoice_creator"
                },
                "confidence": 0.9
            }

        # Check if there are still missing fields
        if missing_fields:
            logger.info(f"Missing fields: {missing_fields}")

            # Check if any company information is missing
            company_fields = ["company_name", "company_address", "company_phone", "company_email"]
            missing_company_info = [field for field in missing_fields if field in company_fields]

            # Suggest setting up a company profile if company information is missing
            profile_suggestion = ""
            if missing_company_info and user_id and db_session:
                profile_suggestion = "\n\nProTip: You can set up your company profile using the 'Company Profile' button in the UI to avoid entering this information repeatedly."

            # Format a response asking for the missing fields
            fields_prompt = "\n".join([f"- {field}" for field in missing_fields])
            return {
                "content": f"I need a bit more information to create your invoice. Please provide the following details:\n\n{fields_prompt}\n\nYou can reply with the information in any format.{profile_suggestion}",
                "metadata": {
                    "confidence": 0.8,
                    "missing_fields": missing_fields,
                    "invoice_data": enriched_data,
                    "invoice_type": "default",
                    "intent": "invoice_creator",
                    "awaiting_completion": True
                },
                "confidence": 0.8
            }

    except Exception as e:
        logger.exception(f"Error checking missing fields: {str(e)}")
        return {
            "content": "✅ I've created your invoice successfully! You can access it through the provided link.",
            "metadata": {
                "confidence": 0.9,
                "invoice_data": enriched_data,
                "intent": "invoice_creator"
            },
            "confidence": 0.9
        }


def processed_data_from_entities(entities: Dict[str, Any], invoice_type: str) -> Dict[str, Any]:
    """
    Process extracted entities into a consistent invoice data structure.

    Args:
        entities: Dictionary of extracted invoice entities
        invoice_type: The type of invoice to generate

    Returns:
        Dictionary with processed invoice data ready for template
    """
    logger.info(f"Processing data for invoice type: {invoice_type}")

    # Start with a copy of the entities
    processed_data = entities.copy()

    # Make sure invoice_type is set
    processed_data["invoice_type"] = invoice_type

    # Ensure items is a list
    if "items" not in processed_data or not processed_data["items"]:
        processed_data["items"] = []
    elif not isinstance(processed_data["items"], list):
        # Convert to list if it's not already
        processed_data["items"] = [processed_data["items"]]

    # Process each item to ensure it has all required fields
    for i, item in enumerate(processed_data["items"]):
        if isinstance(item, dict):
            # Ensure each item has required fields
            if "description" not in item or not item["description"]:
                item["description"] = f"Item {i+1}"

            if "quantity" not in item or not item["quantity"]:
                item["quantity"] = 1

            if "unit_price" not in item or not item["unit_price"]:
                item["unit_price"] = 0

            # Calculate total price if not provided
            if "total_price" not in item or not item["total_price"]:
                try:
                    item["total_price"] = float(item["quantity"]) * float(item["unit_price"])
                except (ValueError, TypeError):
                    item["total_price"] = 0

    # Calculate total amount if missing
    if "total_amount" not in processed_data or not processed_data["total_amount"]:
        try:
            total = sum(float(item["total_price"]) for item in processed_data["items"])
            processed_data["total_amount"] = total
        except (ValueError, TypeError, KeyError):
            processed_data["total_amount"] = 0

    # Set default values for required fields if not present
    if "invoice_number" not in processed_data or not processed_data["invoice_number"]:
        # Generate a unique invoice number based on current timestamp
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d")
        import uuid
        unique_id = uuid.uuid4().hex[:6].upper()
        processed_data["invoice_number"] = f"INV-{timestamp[:6]}{unique_id}"

    # Set invoice date if not present
    if "invoice_date" not in processed_data or not processed_data["invoice_date"]:
        from datetime import datetime
        processed_data["invoice_date"] = datetime.now().date()

    # Set due date if not present (default to 30 days from invoice date)
    if "due_date" not in processed_data or not processed_data["due_date"]:
        from datetime import datetime, timedelta
        if isinstance(processed_data["invoice_date"], datetime):
            invoice_date = processed_data["invoice_date"].date()
        elif isinstance(processed_data["invoice_date"], date):
            invoice_date = processed_data["invoice_date"]
        else:
            invoice_date = datetime.now().date()

        processed_data["due_date"] = invoice_date + timedelta(days=30)

    # Set currency if not present
    if "currency" not in processed_data or not processed_data["currency"]:
        processed_data["currency"] = "USD"

    # Set status if not present
    if "status" not in processed_data or not processed_data["status"]:
        processed_data["status"] = "pending"

    logger.info(f"Processed invoice data: {processed_data}")
    return processed_data
