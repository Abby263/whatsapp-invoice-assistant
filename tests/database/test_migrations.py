"""Tests for database migrations."""

import pytest
import subprocess
import os
import tempfile
from pathlib import Path
from sqlalchemy import create_engine, inspect

from database.schemas import Base


@pytest.fixture
def test_alembic_ini():
    """Create a temporary alembic.ini file for testing."""
    alembic_content = """
[alembic]
script_location = database/migrations
prepend_sys_path = .

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as temp:
        temp.write(alembic_content)
        temp_path = temp.name

    yield temp_path

    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.mark.skip(reason="This test needs to be run in a clean environment without existing migrations")
def test_generate_migration(test_alembic_ini):
    """Test generating a migration script."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a temporary database
        db_path = Path(temp_dir) / "test.db"
        db_url = f"sqlite:///{db_path}"

        # Create the database with the current schema
        engine = create_engine(db_url)
        Base.metadata.create_all(engine)

        # Set environment variables for testing
        env = os.environ.copy()
        env["PYTHONPATH"] = "."
        env["DATABASE_URL"] = db_url

        # First, create an initial migration (necessary for subsequent migrations)
        initial_result = subprocess.run(
            [
                "alembic", 
                "-c", test_alembic_ini, 
                "revision", 
                "--autogenerate", 
                "-m", "initial"
            ],
            env=env,
            capture_output=True,
            text=True
        )
        assert initial_result.returncode == 0, f"Initial migration failed: {initial_result.stderr}"
        
        # Apply the initial migration
        upgrade_result = subprocess.run(
            ["alembic", "-c", test_alembic_ini, "upgrade", "head"],
            env=env,
            capture_output=True,
            text=True
        )
        assert upgrade_result.returncode == 0, f"Upgrade failed: {upgrade_result.stderr}"

        # Now make a schema change to test a new migration
        # This could be a simple table addition, column change, etc.
        # For the test, we'll just generate another migration
        
        # Run alembic command to generate a new migration
        result = subprocess.run(
            [
                "alembic", 
                "-c", test_alembic_ini, 
                "revision", 
                "--autogenerate", 
                "-m", "test_migration"
            ],
            env=env,
            capture_output=True,
            text=True
        )

        # Check if command was successful
        assert result.returncode == 0, f"Migration failed: {result.stderr}"
        assert "Generating" in result.stdout or "No changes detected" in result.stdout


def test_run_migration(test_alembic_ini):
    """Test running a migration."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a temporary database
        db_path = Path(temp_dir) / "test.db"
        db_url = f"sqlite:///{db_path}"

        # Create an empty database
        engine = create_engine(db_url)
        
        # Set environment variables for testing
        env = os.environ.copy()
        env["PYTHONPATH"] = "."
        env["DATABASE_URL"] = db_url

        # Generate a migration
        subprocess.run(
            [
                "alembic", 
                "-c", test_alembic_ini, 
                "revision", 
                "--autogenerate", 
                "-m", "create_tables"
            ],
            env=env,
            capture_output=True
        )

        # Run the migration
        result = subprocess.run(
            ["alembic", "-c", test_alembic_ini, "upgrade", "head"],
            env=env,
            capture_output=True,
            text=True
        )

        # Check if command was successful
        assert result.returncode == 0, f"Migration failed: {result.stderr}"

        # Verify tables were created
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        # Check for expected tables
        expected_tables = [
            "users", "invoices", "items", "conversations", 
            "messages", "whatsapp_messages", "media", "usage"
        ]
        for table in expected_tables:
            assert table in tables, f"Table {table} was not created" 