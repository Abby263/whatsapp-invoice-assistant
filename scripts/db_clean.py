#!/usr/bin/env python
"""
Script to clean database and recreate tables.

This script drops and recreates all tables in the database.
It also tries to install the pgvector extension if available.
"""
import logging
import sys
import os
import time
from pathlib import Path

# Add project directory to path for proper imports
script_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(script_dir)
sys.path.insert(0, project_dir)

# Import logging utilities
from utils.logging import get_logs_directory

# Configure logging
logs_dir = get_logs_directory()
log_file = os.path.join(logs_dir, 'db_clean.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file, mode='w')
    ]
)

logger = logging.getLogger(__name__)

from database.connection import engine, SessionLocal
from database.schemas import Base, has_pgvector
import sqlalchemy as sa
from sqlalchemy.exc import OperationalError, ProgrammingError

def clean_database():
    """Clean database and recreate tables."""
    logger.info("Starting database cleaning process")
    start_time = time.time()
    
    # First, try to install pgvector extension if available
    session = SessionLocal()
    pgvector_installed = False
    
    try:
        # Check if pgvector is already installed
        result = session.execute(sa.text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')"))
        pgvector_installed = result.scalar()
        
        if pgvector_installed:
            logger.info("pgvector extension is already installed")
        else:
            logger.info("Attempting to install pgvector extension")
            try:
                session.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
                session.commit()
                logger.info("Vector extension installed successfully")
                pgvector_installed = True
            except (OperationalError, ProgrammingError) as e:
                logger.warning(f"Vector extension not available: {str(e)}")
                session.rollback()
                # We'll continue with the fallback TEXT type for VECTOR
                
    except Exception as e:
        logger.error(f"Error checking/installing pgvector extension: {str(e)}")
        session.rollback()
    finally:
        session.close()
    
    # Log pgvector status
    if pgvector_installed:
        logger.info("Using native pgvector for vector operations")
    else:
        logger.warning("Using TEXT fallback for vector columns - semantic search will not work properly")
    
    # Drop and recreate all tables
    try:
        logger.info("Dropping all tables")
        Base.metadata.drop_all(engine)
        logger.info("Recreating all tables")
        Base.metadata.create_all(engine)
        logger.info("Tables recreated successfully")
    except Exception as e:
        logger.error(f"Error recreating tables: {str(e)}")
        raise
    
    end_time = time.time()
    logger.info(f"Database cleaning completed in {end_time - start_time:.2f} seconds")

if __name__ == "__main__":
    clean_database() 