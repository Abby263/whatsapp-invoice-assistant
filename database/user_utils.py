"""
User-related database utilities.

This module provides functions for user management in the database.
"""
import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from database.connection import get_db
from database import crud, models

# Configure logging
logger = logging.getLogger(__name__)

def create_user(
    session: Session, 
    whatsapp_number: str, 
    name: Optional[str] = None,
    email: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a new user in the database.
    
    Args:
        session: Database session
        whatsapp_number: User's WhatsApp number (required)
        name: User's name (optional)
        email: User's email (optional)
        
    Returns:
        Dictionary with user information including ID
    """
    # Check if user already exists
    existing_user = crud.user.get_by_whatsapp_number(session, whatsapp_number)
    
    if existing_user:
        logger.info(f"User with WhatsApp number {whatsapp_number} already exists")
        return {
            "id": str(existing_user.id),
            "whatsapp_number": existing_user.whatsapp_number,
            "name": existing_user.name,
            "email": existing_user.email,
            "is_active": existing_user.is_active,
            "created_at": existing_user.created_at.isoformat(),
            "updated_at": existing_user.updated_at.isoformat(),
            "is_new": False
        }
    
    # Create new user
    logger.info(f"Creating new user with WhatsApp number {whatsapp_number}")
    
    # Prepare user data
    user_data = {
        "whatsapp_number": whatsapp_number,
        "name": name or f"User {whatsapp_number}",
        "email": email
    }
    
    # Create user with Pydantic model
    user_in = models.UserCreate(**user_data)
    new_user = crud.user.create(session, obj_in=user_in)
    
    logger.info(f"Created new user with ID {new_user.id}")
    
    # Return user info
    return {
        "id": str(new_user.id),
        "whatsapp_number": new_user.whatsapp_number,
        "name": new_user.name,
        "email": new_user.email,
        "is_active": new_user.is_active,
        "created_at": new_user.created_at.isoformat(),
        "updated_at": new_user.updated_at.isoformat(),
        "is_new": True
    } 