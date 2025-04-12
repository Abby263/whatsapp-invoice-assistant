"""
Database service for application components.

This module provides a wrapper for database access to be used by other services and
application components, ensuring consistent database session handling.
"""

import logging
from typing import Generator, Optional
from sqlalchemy.orm import Session

from database.connection import get_db, SessionLocal

logger = logging.getLogger(__name__)

class Database:
    """Database service for managing database sessions and connections."""
    
    @staticmethod
    def get_session() -> Session:
        """
        Get a new database session.
        
        Returns:
            Session: SQLAlchemy session object
        """
        return SessionLocal()
    
    @staticmethod
    def close_session(session: Session) -> None:
        """
        Close a database session.
        
        Args:
            session: SQLAlchemy session to close
        """
        if session:
            session.close()


def get_session() -> Generator[Session, None, None]:
    """
    Get a database session that will be automatically closed when done.
    
    This is a convenience wrapper around the get_db function from database.connection.
    
    Yields:
        Generator[Session, None, None]: SQLAlchemy session
    """
    yield from get_db() 