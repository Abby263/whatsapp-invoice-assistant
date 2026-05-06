"""
User-related database utilities.

This module provides functions for user management in the database.
"""
import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from database.connection import get_db
from database import crud, models
from database.schemas import User

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


def serialize_user(user: User, is_new: bool = False) -> Dict[str, Any]:
    """Return a UI/API-safe dictionary for a user row."""

    return {
        "id": str(user.id),
        "whatsapp_number": user.whatsapp_number,
        "clerk_user_id": user.clerk_user_id,
        "name": user.name,
        "email": user.email,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        "is_new": is_new,
    }


def get_user_by_clerk_id(session: Session, clerk_user_id: str) -> Optional[User]:
    """Return the app user linked to a Clerk user id."""

    return session.query(User).filter(User.clerk_user_id == clerk_user_id).first()


def link_clerk_user_to_whatsapp(
    session: Session,
    clerk_user_id: str,
    whatsapp_number: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Link a Clerk web identity to the app user identified by WhatsApp number.

    This is the bridge that lets receipts uploaded through WhatsApp appear in
    the same account after the user signs in on the website.
    """

    existing_link = get_user_by_clerk_id(session, clerk_user_id)
    if existing_link and existing_link.whatsapp_number != whatsapp_number:
        raise ValueError(
            "This Clerk account is already linked to a different WhatsApp number"
        )

    user = crud.user.get_by_whatsapp_number(session, whatsapp_number)
    is_new = False

    if user and user.clerk_user_id and user.clerk_user_id != clerk_user_id:
        raise ValueError("This WhatsApp number is already linked to another account")

    if not user:
        user_in = models.UserCreate(
            whatsapp_number=whatsapp_number,
            clerk_user_id=clerk_user_id,
            name=name or f"User {whatsapp_number}",
            email=email,
        )
        user = crud.user.create(session, obj_in=user_in)
        is_new = True
    else:
        user.clerk_user_id = clerk_user_id
        if name and not user.name:
            user.name = name
        if email and not user.email:
            user.email = email
        session.add(user)
        session.commit()
        session.refresh(user)

    logger.info("Linked Clerk user %s to app user %s", clerk_user_id, user.id)
    return serialize_user(user, is_new=is_new)
