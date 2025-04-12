"""
Alembic environment configuration.

This script provides the environment for Alembic migrations.
It sets up the MetaData and connects to the database using 
configuration from the application.
"""
from logging.config import fileConfig
import os
import sys

# Add the project root directory to the Python path
# This ensures that the 'database' package can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.exc import OperationalError
from sqlalchemy.sql import text

from alembic import context

# Import all SQLAlchemy models here to make them available to Alembic
from database.schemas import Base
from database.connection import get_database_url

# This is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Set the SQLAlchemy URL in the Alembic config
config.set_main_option("sqlalchemy.url", get_database_url())

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = get_database_url()
    
    # Try to create the pgvector extension
    try:
        context.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    except Exception as e:
        print(f"Warning: Could not create pgvector extension: {e}")
    
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    # Override the URL in the alembic.ini file
    config_section = config.get_section(config.config_ini_section)
    config_section["sqlalchemy.url"] = get_database_url()
    
    connectable = engine_from_config(
        config_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # Try to create the pgvector extension
        try:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            connection.commit()
        except OperationalError as e:
            print(f"Warning: Could not create pgvector extension: {e}")
        
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online() 