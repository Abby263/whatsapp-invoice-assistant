#!/usr/bin/env python
"""
User Data Service

This module handles retrieving and caching user-specific data for invoice creation,
reducing the need to repeatedly ask users for the same information.
"""

import logging
import json
import re
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from database.schemas import User, Invoice, Item
from database.connection import get_db_session

logger = logging.getLogger(__name__)

# Define which fields can be retrieved from user history
RETRIEVABLE_USER_FIELDS = {
    # User table fields
    "company_name", "company_address", "company_phone", "company_email", "company_fax",
    "company_slogan", "company_website", "company_tax_id", "payment_terms",

    # Common recipient fields - stored as JSON in user preferences
    "last_client_name", "last_client_company", "last_client_address", "last_client_phone",
    "last_client_email", "default_invoice_prefix", "default_payment_days"
}

# Create a mock CompanyProfile class or dict for default company data
DEFAULT_COMPANY_DATA = {
    "company_name": "Your Company",
    "address": "123 Business St",
    "city": "Business City",
    "state": "BS",
    "zip_code": "12345",
    "phone": "(555) 123-4567",
    "email": "contact@yourcompany.com",
    "website": "https://www.yourcompany.com",
    "tagline": "Your business tagline here"
}

def get_user_data(user_id: int, db_session=None) -> Dict[str, Any]:
    """
    Get user data including company profile if available.

    Args:
        user_id (int): User ID
        db_session: Optional database session to use

    Returns:
        Dict[str, Any]: User data dictionary
    """
    user_data = {}

    try:
        # Use provided session or create a new one
        if db_session is None:
            db_session = get_db_session()

        # Get user info
        user = db_session.query(User).filter(User.id == user_id).first()
        if user:
            user_data["name"] = user.name or "Customer"
            user_data["email"] = user.email or ""
            user_data["phone"] = user.whatsapp_number or ""

        # Since CompanyProfile doesn't exist, use default company data
        user_data.update({
            "company_name": DEFAULT_COMPANY_DATA["company_name"],
            "address": DEFAULT_COMPANY_DATA["address"],
            "city": DEFAULT_COMPANY_DATA["city"],
            "state": DEFAULT_COMPANY_DATA["state"],
            "zip_code": DEFAULT_COMPANY_DATA["zip_code"],
            "phone": DEFAULT_COMPANY_DATA["phone"],
            "email": DEFAULT_COMPANY_DATA["email"],
            "website": DEFAULT_COMPANY_DATA["website"],
            "tagline": DEFAULT_COMPANY_DATA["tagline"]
        })

    except Exception as e:
        logger.error(f"Error getting user data: {str(e)}")

    return user_data

def get_invoice_defaults(invoice_type: str, user_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate default values for invoice fields based on user data.

    Args:
        invoice_type: The type of invoice
        user_data: User data retrieved from the database

    Returns:
        Dictionary of default values for invoice fields
    """
    defaults = {}

    # Map user data fields to invoice fields
    field_mappings = {
        # User profile fields
        "name": "company_name",
        "email": "company_email",
        "phone_number": "company_phone",

        # User preference fields (direct mapping)
        "company_name": "company_name",
        "company_address": "company_address",
        "company_phone": "company_phone",
        "company_email": "company_email",
        "company_fax": "company_fax",
        "company_slogan": "company_slogan",
        "company_website": "company_website",
        "company_tax_id": "company_tax_id",
        "payment_terms": "payment_terms",

        # Client information stored in preferences - properly map to invoice fields
        "client_name": "client_name",
        "client_company": "client_company",
        "client_address": "client_address",
        "client_phone": "client_phone",
        "client_email": "client_email",

        # Last invoice vendor as company name fallback
        "last_vendor": "company_name"
    }

    # Apply field mappings
    for source_field, target_field in field_mappings.items():
        if source_field in user_data and user_data[source_field]:
            defaults[target_field] = user_data[source_field]

    # Add date fields
    now = datetime.now()
    defaults["invoice_date"] = now.strftime("%Y-%m-%d")

    # Add due date based on payment_terms if available
    if "payment_terms" in defaults and defaults["payment_terms"]:
        terms = defaults["payment_terms"]
        # Check for different payment term formats
        days = None
        if isinstance(terms, str):
            if "days" in terms.lower():
                try:
                    # Try to extract number of days from text like "30 days", "Net 30 days", etc.
                    days_match = re.search(r'(\d+)(?:\s+)?(?:days|day)', terms.lower())
                    if days_match:
                        days = int(days_match.group(1))
                except (ValueError, IndexError):
                    pass
            elif "net" in terms.lower():
                try:
                    # Try to extract number from "Net 30" format
                    net_days_match = re.search(r'net\s+(\d+)', terms.lower())
                    if net_days_match:
                        days = int(net_days_match.group(1))
                except (ValueError, IndexError):
                    pass
            else:
                try:
                    # Try direct number
                    days = int(re.findall(r'\d+', terms)[0])
                except (ValueError, IndexError):
                    pass

        # If we successfully extracted the days, calculate due date
        if days:
            from datetime import timedelta
            due_date = now + timedelta(days=days)
            defaults["due_date"] = due_date.strftime("%Y-%m-%d")

    # Set default invoice number with prefix if available
    prefix = user_data.get("default_invoice_prefix", "INV")
    date_str = now.strftime("%Y%m%d")
    defaults["invoice_number"] = f"{prefix}-{date_str}"

    # Set default currency if available
    defaults["currency"] = user_data.get("default_currency", "USD")

    # Ensure recipient_info is populated if client data is available
    if any(field in defaults for field in ["client_name", "client_company", "client_address", "client_phone", "client_email"]):
        recipient_info = {}
        for field in ["client_name", "client_company", "client_address", "client_phone", "client_email"]:
            if field in defaults:
                # Convert client_* to recipient field name (e.g., client_name -> name)
                recipient_field = field.replace("client_", "")
                recipient_info[recipient_field] = defaults[field]

        if recipient_info:
            defaults["recipient_info"] = recipient_info

    logger.info(f"Generated invoice defaults from user profile: {len(defaults)} fields populated")

    return defaults

def enrich_invoice_data(invoice_data: Dict[str, Any], user_id: int) -> Dict[str, Any]:
    """
    Enrich invoice data with user data like company info and defaults.

    Args:
        invoice_data (Dict[str, Any]): Base invoice data
        user_id (int): User ID

    Returns:
        Dict[str, Any]: Enriched invoice data
    """
    # Get user data - will now use default company data
    user_data = get_user_data(user_id)

    # Add user data to invoice data
    enriched_data = {**invoice_data}

    # Add default company information
    for key in DEFAULT_COMPANY_DATA:
        if key not in enriched_data:
            enriched_data[key] = user_data.get(key, DEFAULT_COMPANY_DATA[key])

    # Add default invoice fields if not present
    # Extract invoice type or use default
    invoice_type = invoice_data.get("invoice_type", "default")
    defaults = get_invoice_defaults(invoice_type, user_data)
    for key, value in defaults.items():
        if key not in enriched_data:
            enriched_data[key] = value

    return enriched_data

def save_invoice_to_database(invoice_data: Dict[str, Any], user_id: str, document_path: str = None, pdf_path: str = None, db_session: Session = None) -> Optional[str]:
    """
    Save generated invoice data to the database.

    Args:
        invoice_data: The invoice data to save
        user_id: The user ID who created the invoice
        document_path: Optional path to the generated document
        pdf_path: Optional path to the generated PDF
        db_session: Optional database session

    Returns:
        The ID of the created invoice, or None if failed
    """
    if not db_session:
        logger.warning("Cannot save invoice without a database session")
        return None

    try:
        # Check if the user exists
        user = db_session.query(User).filter(User.id == user_id).first()
        if not user:
            logger.warning(f"User {user_id} not found in database")
            return None

        # Extract basic invoice data
        invoice_number = invoice_data.get("invoice_number", "")
        invoice_date_str = invoice_data.get("invoice_date", "")
        due_date_str = invoice_data.get("due_date", "")
        total_amount = invoice_data.get("total_amount") or invoice_data.get("invoice_total", 0)
        currency = invoice_data.get("currency", "USD")
        vendor = invoice_data.get("vendor") or invoice_data.get("company_name", "")
        payment_terms = invoice_data.get("payment_terms", "")

        # Try to parse dates
        from datetime import datetime
        invoice_date = None
        due_date = None

        if invoice_date_str:
            try:
                for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y"]:
                    try:
                        invoice_date = datetime.strptime(invoice_date_str, fmt).date()
                        break
                    except ValueError:
                        continue
            except Exception as e:
                logger.warning(f"Error parsing invoice date: {e}")

        if due_date_str:
            try:
                for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y"]:
                    try:
                        due_date = datetime.strptime(due_date_str, fmt).date()
                        break
                    except ValueError:
                        continue
            except Exception as e:
                logger.warning(f"Error parsing due date: {e}")

        # Create recipient info JSON
        recipient_info = {}
        for key in ["client_name", "client_company", "client_address", "client_phone", "client_email"]:
            if key in invoice_data and invoice_data[key]:
                # Convert from client_* to just the name (e.g., client_name -> name)
                recipient_key = key.replace("client_", "")
                recipient_info[recipient_key] = invoice_data[key]

        # Create invoice object
        invoice = Invoice(
            user_id=user_id,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            due_date=due_date,
            vendor=vendor,
            total_amount=total_amount,
            currency=currency,
            payment_terms=payment_terms,
            status="created",
            recipient_info=json.dumps(recipient_info),
            document_path=document_path,
            pdf_path=pdf_path,
            created_at=datetime.now()
        )

        # Add to database
        db_session.add(invoice)
        db_session.flush()  # Get the ID without committing

        # Extract and add items
        items = []
        if "items" in invoice_data and invoice_data["items"]:
            for item_data in invoice_data["items"]:
                item = Item(
                    invoice_id=invoice.id,
                    description=item_data.get("description", ""),
                    quantity=item_data.get("quantity", 0),
                    unit_price=item_data.get("unit_price", 0),
                    total_price=item_data.get("total_price", 0),
                    created_at=datetime.now()
                )
                items.append(item)
                db_session.add(item)

        # Add materials and labor as items if present (for time & material invoices)
        if "materials" in invoice_data and invoice_data["materials"]:
            for material in invoice_data["materials"]:
                item = Item(
                    invoice_id=invoice.id,
                    description=f"Material: {material.get('description', '')}",
                    quantity=material.get("quantity", 0),
                    unit_price=material.get("unit_price", 0),
                    total_price=material.get("total_price", 0),
                    item_type="material",
                    created_at=datetime.now()
                )
                items.append(item)
                db_session.add(item)

        if "labor_items" in invoice_data and invoice_data["labor_items"]:
            for labor in invoice_data["labor_items"]:
                item = Item(
                    invoice_id=invoice.id,
                    description=f"Labor: {labor.get('description', '')}",
                    quantity=labor.get("hours", 0),  # Hours as quantity
                    unit_price=labor.get("rate", 0),  # Rate as unit price
                    total_price=labor.get("total_price", 0),
                    item_type="labor",
                    created_at=datetime.now()
                )
                items.append(item)
                db_session.add(item)

        # Commit the transaction
        db_session.commit()

        # Try to generate embeddings for invoice items (optional)
        try:
            from utils.vector_utils import generate_embeddings
            for item in items:
                if hasattr(item, "description") and item.description:
                    # This would ideally be done asynchronously or in a background task
                    item.description_embedding = generate_embeddings(item.description)
                    db_session.add(item)

            db_session.commit()
        except Exception as e:
            logger.warning(f"Error generating embeddings for invoice items: {e}")

        logger.info(f"Successfully saved invoice {invoice.id} to database")
        return invoice.id

    except Exception as e:
        logger.error(f"Error saving invoice to database: {e}", exc_info=True)
        if db_session:
            db_session.rollback()
        return None

# Testing function
def test_user_data():
    """Test the user data enrichment with sample data"""
    # Sample user data that would come from the database
    sample_user_data = {
        "user_id": "user123",
        "name": "ABC Consulting",
        "email": "info@abcconsulting.com",
        "phone_number": "555-1234",
        "company_address": "123 Main St, Suite 100, San Francisco, CA 94105",
        "company_slogan": "Making Business Better",
        "payment_terms": "30 days",
        "last_client_name": "John Smith",
        "last_client_company": "XYZ Corporation",
        "last_client_address": "456 Market St, New York, NY 10001",
        "last_client_phone": "555-5678",
        "last_client_email": "john@xyzcorp.com",
        "default_invoice_prefix": "ABC"
    }

    # Sample invoice data (incomplete)
    sample_invoice_data = {
        "invoice_type": "service invoice",
        "project_description": "Website Development",
        "items": [
            {"description": "Web Design", "quantity": 1, "unit_price": 1500, "total_price": 1500},
            {"description": "Development", "quantity": 20, "unit_price": 100, "total_price": 2000}
        ],
        "total_amount": 3500
    }

    print("\nTesting user data enrichment...")

    # Mock the get_user_data function
    import types
    original_get_user_data = get_user_data
    get_user_data = lambda user_id, db_session=None: sample_user_data

    try:
        # Enrich the invoice data
        enriched_data = enrich_invoice_data(sample_invoice_data, "user123")

        print("\nEnriched invoice data:")
        for key, value in enriched_data.items():
            if key != "items":  # Skip printing items for brevity
                print(f"  {key}: {value}")
            elif key == "items":
                print(f"  {key}: {len(value)} items")

    finally:
        # Restore original function
        get_user_data = original_get_user_data

if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO)

    # Run test
    test_user_data()