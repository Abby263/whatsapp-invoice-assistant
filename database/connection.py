"""
Database connection utilities.

This module provides functions to create database engine and session management.
"""
from typing import Generator
import logging
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from utils.config import get_db_config

logger = logging.getLogger(__name__)

# Get database URL from environment variable if available (for migrations)
ENV_DATABASE_URL = os.environ.get("DATABASE_URL")

if ENV_DATABASE_URL:
    # Use environment variable if set (useful for tests and migrations)
    DATABASE_URL = ENV_DATABASE_URL
else:
    # Get database configuration from config
    db_config = get_db_config()

    # Validate port to avoid empty string
    port = db_config.get('port', '5432')
    if not port:
        port = '5432'

    # Create database URL
    DATABASE_URL = (
        f"{db_config.get('protocol', 'postgresql')}://{db_config.get('username', 'postgres')}:"
        f"{db_config.get('password', '')}@{db_config.get('host', 'localhost')}:"
        f"{port}/{db_config.get('database', 'whatsapp_invoice_assistant')}"
    )

# Create engine with appropriate connection options
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    echo=db_config.get("echo", False) if not ENV_DATABASE_URL else False,
    pool_size=db_config.get("pool_size", 5) if not ENV_DATABASE_URL else 5,
    max_overflow=db_config.get("max_overflow", 10) if not ENV_DATABASE_URL else 10,
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Import Base from schemas to avoid circular imports
from database.schemas import Base


def get_db() -> Generator[Session, None, None]:
    """
    Create and yield a database session, ensuring it's closed after use.
    
    Yields:
        Generator[Session, None, None]: SQLAlchemy session
    """
    db = SessionLocal()
    try:
        logger.debug("Opening database session")
        yield db
    finally:
        logger.debug("Closing database session")
        db.close()


def init_db() -> None:
    """
    Initialize the database by creating all tables defined in the models.
    
    This should be called only when setting up the database from scratch.
    For migrations, use Alembic instead.
    """
    logger.info("Creating database tables (if they don't exist)")
    Base.metadata.create_all(bind=engine) 