"""
Database connection module for managing connections to Supabase PostgreSQL.
Only Supabase connections are supported by this application.
"""

import os
import logging
import asyncpg
from contextlib import contextmanager
from typing import Iterator, Optional, Dict, Any
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from config.env import get_env_variable

logger = logging.getLogger(__name__)

# Define the base model class
Base = declarative_base()

# Create engine and session factory
# Check for Supabase DATABASE_URL
SQLALCHEMY_DATABASE_URL = get_env_variable("DATABASE_URL", None)

# Fallback to SUPABASE_DATABASE_URL if exists
if not SQLALCHEMY_DATABASE_URL:
    SQLALCHEMY_DATABASE_URL = get_env_variable("SUPABASE_DATABASE_URL", None)

if not SQLALCHEMY_DATABASE_URL:
    # Try to build URL from Supabase specific components
    supabase_project_id = get_env_variable("SUPABASE_PROJECT_ID", None)
    supabase_password = get_env_variable("SUPABASE_DB_PASSWORD", None)

    if supabase_project_id and supabase_password:
        # Direct connection format for Supabase
        SQLALCHEMY_DATABASE_URL = f"postgresql://postgres:{supabase_password}@db.{supabase_project_id}.supabase.co:5432/postgres"
        logger.info("Using Supabase direct connection format")
    else:
        # No Supabase connection details found
        error_msg = "No Supabase connection details found. Please set DATABASE_URL, SUPABASE_DATABASE_URL, or SUPABASE_PROJECT_ID and SUPABASE_DB_PASSWORD."
        logger.error(error_msg)
        raise ValueError(error_msg)

if "@" in SQLALCHEMY_DATABASE_URL:
    logger.info(
        "Using database URL: %s",
        SQLALCHEMY_DATABASE_URL.replace(SQLALCHEMY_DATABASE_URL.split("@")[0], "***"),
    )
else:
    logger.info("Using database URL: %s", SQLALCHEMY_DATABASE_URL)

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_database_url() -> str:
    """Return the configured SQLAlchemy database URL."""
    return SQLALCHEMY_DATABASE_URL

def get_db() -> Iterator[Session]:
    """
    Get a database session.

    Yields:
        SQLAlchemy Session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_db_session() -> Session:
    """Return a SQLAlchemy session that the caller must close."""
    return SessionLocal()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transactional session scope for scripts and services."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def db_session(func):
    """
    Decorator to provide a database session to a function.
    """
    def wrapper(*args, **kwargs):
        db = SessionLocal()
        try:
            result = func(*args, **kwargs, db=db)
            return result
        finally:
            db.close()
    return wrapper

async def get_connection_string():
    """
    Build and return a PostgreSQL connection string from environment variables.
    Only Supabase connections are supported.
    """
    # First check for complete DATABASE_URL
    database_url = get_env_variable("DATABASE_URL", None)
    if database_url:
        return database_url

    # Next check for Supabase specific URL
    supabase_db_url = get_env_variable("SUPABASE_DATABASE_URL", None)
    if supabase_db_url:
        return supabase_db_url

    # Check for Supabase components
    supabase_project_id = get_env_variable("SUPABASE_PROJECT_ID", None)
    supabase_password = get_env_variable("SUPABASE_DB_PASSWORD", None)

    if supabase_project_id and supabase_password:
        # Direct connection format for Supabase
        return f"postgresql://postgres:{supabase_password}@db.{supabase_project_id}.supabase.co:5432/postgres"

    # No valid connection configuration found
    error_msg = "No Supabase connection details found. Please set DATABASE_URL, SUPABASE_DATABASE_URL, or SUPABASE_PROJECT_ID and SUPABASE_DB_PASSWORD."
    logger.error(error_msg)
    raise ValueError(error_msg)

async def get_connection_pool(min_size=5, max_size=10):
    """
    Create and return a connection pool for PostgreSQL.

    Args:
        min_size: Minimum number of connections in the pool
        max_size: Maximum number of connections in the pool

    Returns:
        asyncpg.Pool: Connection pool object
    """
    connection_string = await get_connection_string()

    try:
        pool = await asyncpg.create_pool(
            connection_string,
            min_size=min_size,
            max_size=max_size
        )
        logger.info("Successfully created database connection pool")
        return pool
    except Exception as e:
        logger.error(f"Failed to create connection pool: {str(e)}")
        raise

async def create_postgres_tables():
    """
    Create application tables from the SQLAlchemy schema.
    """
    try:
        from database.schemas import Base as SchemaBase

        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        SchemaBase.metadata.create_all(bind=engine)
        logger.info("Application tables created successfully")
    except Exception as e:
        logger.error(f"Error creating application tables: {str(e)}")
        raise

async def ensure_test_user_exists(db: Optional[Session] = None) -> Dict[str, Any]:
    """
    Ensure a test user exists in the database.

    Args:
        db: Optional database session

    Returns:
        Dict with user information
    """
    logger.info("Ensuring test user exists in the database")

    # If SQLAlchemy session provided, use it to create user
    if db:
        try:
            # Import here to avoid circular imports
            from database import models, crud

            # Check if test user exists
            test_user = crud.user.get_by_email(db, email="test@example.com")

            if not test_user:
                # Create test user
                user_data = models.UserCreate(
                    name="Test User",
                    email="test@example.com",
                    whatsapp_number="+1234567890"
                )
                test_user = crud.user.create(db, obj_in=user_data)
                logger.info(f"Created test user with ID: {test_user.id}")
            else:
                logger.info(f"Test user already exists with ID: {test_user.id}")

            # Return user data
            return {
                "id": test_user.id,
                "name": test_user.name,
                "email": test_user.email,
                "whatsapp_number": test_user.whatsapp_number
            }
        except Exception as e:
            logger.error(f"Error ensuring test user exists: {str(e)}")

    # Use asyncpg if no SQLAlchemy session
    try:
        connection_string = await get_connection_string()
        conn = await asyncpg.connect(connection_string)

        # Check if test user exists
        user = await conn.fetchrow(
            "SELECT id, name, email, whatsapp_number FROM users WHERE email = $1",
            "test@example.com"
        )

        if not user:
            # Create test user
            user_id = await conn.fetchval(
                """
                INSERT INTO users (name, email, whatsapp_number)
                VALUES ($1, $2, $3)
                RETURNING id
                """,
                "Test User", "test@example.com", "+1234567890"
            )

            # Get created user
            user = await conn.fetchrow(
                "SELECT id, name, email, whatsapp_number FROM users WHERE id = $1",
                user_id
            )

            logger.info(f"Created test user with ID: {user['id']}")
        else:
            logger.info(f"Test user already exists with ID: {user['id']}")

        # Close connection
        await conn.close()

        # Return user data
        return dict(user)
    except Exception as e:
        logger.error(f"Error ensuring test user exists with asyncpg: {str(e)}")

        # Return dummy user data if all else fails
        return {
            "id": 1,
            "name": "Test User",
            "email": "test@example.com",
            "whatsapp_number": "+1234567890"
        }

async def check_pgvector_extension(conn=None):
    """
    Check if the pgvector extension is installed and available.

    Args:
        conn: Optional database connection

    Returns:
        bool: True if pgvector is available, False otherwise
    """
    close_conn = False
    try:
        if not conn:
            connection_string = await get_connection_string()
            conn = await asyncpg.connect(connection_string)
            close_conn = True

        # Check if pgvector extension exists
        result = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')"
        )

        logger.info(f"pgvector extension status: {'Available' if result else 'Not available'}")
        return result
    except Exception as e:
        logger.error(f"Error checking pgvector extension: {str(e)}")
        return False
    finally:
        if close_conn and conn:
            await conn.close()

async def test_database_connection():
    """
    Test database connection and return status information.

    Returns:
        dict: Connection status information
    """
    logger.info("Testing database connection...")
    status = {
        "success": False,
        "message": "",
        "connection_info": {}
    }

    try:
        # Get connection string
        connection_string = await get_connection_string()
        logger.info(f"Using connection string (partial): {connection_string.split('@')[0].split(':')[0]}:***@{connection_string.split('@')[1] if '@' in connection_string else 'unknown'}")

        # Parse connection string for info
        if '@' in connection_string:
            user_part = connection_string.split('://')[1].split(':')[0] if '://' in connection_string else "unknown"
            host_part = connection_string.split('@')[1].split('/')[0].split(':')[0] if '@' in connection_string else "unknown"
            port_part = connection_string.split('@')[1].split('/')[0].split(':')[1] if '@' in connection_string and ':' in connection_string.split('@')[1].split('/')[0] else "5432"
            db_part = connection_string.split('/')[-1] if '/' in connection_string else "unknown"

            status["connection_info"] = {
                "user": user_part,
                "host": host_part,
                "port": port_part,
                "database": db_part
            }

        # Try to connect
        conn = await asyncpg.connect(connection_string)

        # Test query
        result = await conn.fetchval('SELECT current_timestamp')
        status["success"] = True
        status["message"] = f"Successfully connected to database. Server time: {result}"
        logger.info(status["message"])

        # Test for pgvector
        has_pgvector = await check_pgvector_extension(conn)
        status["pgvector"] = has_pgvector

        # Close connection
        await conn.close()
    except Exception as e:
        status["success"] = False
        status["message"] = f"Database connection error: {str(e)}"
        logger.error(status["message"])

    return status
