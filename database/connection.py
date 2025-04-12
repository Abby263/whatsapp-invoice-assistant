"""
Database connection setup and utility functions.

This module provides functions for setting up the SQLAlchemy engine,
creating database sessions, and initializing the database schema.
"""

import logging
import os
from typing import Generator, Optional, Dict, Any, Callable, ContextManager
from contextlib import contextmanager

import sqlalchemy
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from utils.config import config
from constants.ui_config import DEFAULT_VECTOR_DIMENSION, VECTOR_EXTENSION_NAME

# Configure logging
logger = logging.getLogger(__name__)

# Create Base class for declarative models
Base = declarative_base()

# Get database configuration from settings
settings = config.get("database") if "database" in config.config else {}

def get_database_url() -> str:
    """
    Get the database URL from environment variables or settings.
    
    Prioritizes DATABASE_URL from environment variables for consistency.
    
    Returns:
        str: Database URL string
    """
    # First check for DATABASE_URL in environment variables (highest priority)
    env_db_url = os.environ.get("DATABASE_URL")
    if env_db_url:
        logger.debug("Using DATABASE_URL from environment variables")
        return env_db_url
    
    # Then check for url in settings from config file
    if "url" in settings and settings["url"]:
        logger.debug("Using database URL from config file")
        return settings["url"]
    
    # Fallback to constructing URL from parts (lowest priority)
    logger.warning("No DATABASE_URL found, constructing from config parts")
    db_config = config.get("database", {})
    protocol = db_config.get("protocol", "postgresql")
    username = db_config.get("username", "postgres")
    password = db_config.get("password", "password")
    
    # Check if we're running in Docker
    default_host = "localhost"
    if os.environ.get("PYTHONPATH") == "/app" or os.path.exists("/.dockerenv"):
        default_host = "whatsapp-invoice-assistant-db"
    
    host = db_config.get("host", default_host)
    port = db_config.get("port", "5432")
    database = db_config.get("database", "whatsapp_invoice_assistant")
    
    return f"{protocol}://{username}:{password}@{host}:{port}/{database}"

# Create SQLAlchemy engine with connection pooling
engine = create_engine(
    get_database_url(),
    pool_size=settings.get("pool_size", 10),
    max_overflow=settings.get("max_overflow", 20),
    echo=settings.get("echo", False),
)

def check_pgvector_extension() -> bool:
    """
    Check if pgvector extension is installed in the database
    
    Returns:
        bool: True if pgvector is installed, False otherwise
    """
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"SELECT * FROM pg_extension WHERE extname = '{VECTOR_EXTENSION_NAME}'"))
            installed = result.rowcount > 0
            if installed:
                logger.info(f"pgvector extension '{VECTOR_EXTENSION_NAME}' is installed in the database")
            else:
                logger.warning(f"pgvector extension '{VECTOR_EXTENSION_NAME}' is NOT installed in the database")
            return installed
    except Exception as e:
        logger.error(f"Error checking for pgvector extension: {e}")
        return False

def create_pgvector_extension() -> bool:
    """
    Create pgvector extension in the database if it doesn't exist
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        with engine.connect() as conn:
            conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {VECTOR_EXTENSION_NAME};"))
            conn.commit()
            logger.info(f"Successfully created pgvector extension '{VECTOR_EXTENSION_NAME}' in PostgreSQL")
            return True
    except Exception as e:
        logger.error(f"Failed to create pgvector extension: {e}")
        return False

# Try to register pgvector with the engine
try:
    import pgvector
    from pgvector.sqlalchemy import Vector
    logger.info("Successfully imported pgvector Vector type")
    
    # Register pgvector extension with PostgreSQL if not already
    extension_created = create_pgvector_extension()
    extension_installed = check_pgvector_extension()
    
    if extension_installed:
        # The Vector type is now available
        logger.info(f"Vector type is available for use with dimension {DEFAULT_VECTOR_DIMENSION}")
    else:
        logger.warning("pgvector extension is not installed. Vector searches will not work.")
except ImportError:
    logger.warning("pgvector not installed. Vector operations will not be available.")
except Exception as e:
    logger.error(f"Error setting up pgvector: {str(e)}")

# Create sessionmaker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db() -> Generator[Session, None, None]:
    """
    Get a database session.
    
    Yields:
        Session: SQLAlchemy database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@contextmanager
def db_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.
    
    Yields:
        Session: SQLAlchemy database session
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database session error: {e}")
        raise
    finally:
        session.close()

def get_db_session() -> Session:
    """
    Get a database session directly.
    
    Returns:
        Session: SQLAlchemy database session
    """
    return SessionLocal()

def initialize_database() -> None:
    """
    Initialize the database by creating tables and extensions.
    """
    from database.schemas import User  # Import here to avoid circular imports
    
    logger.info("Initializing database")
    
    # Check and create pgvector extension
    extension_installed = check_pgvector_extension()
    if not extension_installed:
        logger.info("Attempting to create pgvector extension")
        create_pgvector_extension()
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created")
    
    # Create test user if in development
    if os.environ.get("ENVIRONMENT", "development") == "development":
        create_test_user()

def create_test_user() -> None:
    """
    Create a test user for development purposes.
    """
    from database.schemas import User  # Import here to avoid circular imports
    
    with db_session() as session:
        # Check if test user already exists
        test_user = session.query(User).filter(User.email == "test@example.com").first()
        
        if not test_user:
            logger.info("Creating test user")
            test_user = User(
                email="test@example.com",
                name="Test User",
                whatsapp_number="+1234567890",
                is_active=True
            )
            session.add(test_user)
            session.commit()
            logger.info(f"Created test user with ID: {test_user.id}")
        else:
            logger.info(f"Test user already exists with ID: {test_user.id}")

def ensure_test_user_exists() -> None:
    """
    Ensure that a test user exists in the database.
    
    This function is used by tests and the UI to ensure a test user is available.
    """
    from database.schemas import User  # Import here to avoid circular imports
    
    logger.info("Ensuring test user exists")
    
    with db_session() as session:
        # Check if test user already exists
        test_user = session.query(User).filter(User.whatsapp_number == "+1234567890").first()
        
        if not test_user:
            # Create tables if they don't exist yet
            Base.metadata.create_all(bind=engine)
            
            logger.info("Creating test user")
            test_user = User(
                email="test@example.com",
                name="Test User",
                whatsapp_number="+1234567890",
                is_active=True
            )
            session.add(test_user)
            session.commit()
            logger.info(f"Created test user with ID: {test_user.id}")
        else:
            logger.info(f"Test user already exists with ID: {test_user.id}") 