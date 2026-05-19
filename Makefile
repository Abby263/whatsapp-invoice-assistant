.PHONY: all install poetry-update test test-db lint format db-clean db-status db-migrate db-revision db-downgrade db-history db-seed ui-run test-sql update-embeddings validate-env

# Dependency management
install:
	@echo "Installing dependencies..."
	poetry install
	poetry run pre-commit install

poetry-update:
	@echo "Updating Poetry lock file..."
	poetry lock
	@echo "Installing dependencies..."
	poetry install --no-root

# Environment validation
validate-env:
	@echo "Validating local environment file..."
	python3 scripts/validate_env.py --env-file .env

# Database management
db-clean:
	@echo "Cleaning database tables..."
	@PYTHONPATH=. poetry run python scripts/db_clean.py
	@echo "Database tables have been dropped and recreated."

db-status:
	@echo "Checking database status..."
	@PYTHONPATH=. poetry run python -c "import asyncio; from database.connection import test_database_connection; print(asyncio.run(test_database_connection()))"

db-migrate:
	@echo "Running database migrations..."
	PYTHONPATH=. poetry run alembic upgrade head

db-downgrade:
	@echo "Downgrading database to previous revision..."
	PYTHONPATH=. poetry run alembic downgrade -1

db-revision:
	@echo "Creating new migration revision..."
	PYTHONPATH=. poetry run alembic revision --autogenerate -m "$(description)"

db-history:
	@echo "Showing migration history..."
	PYTHONPATH=. poetry run alembic history

db-seed:
	@echo "Seeding database with test data..."
	@poetry run python -c "from tests.database.seed import seed_database; seed_database()"

# Local UI
ui-run:
	@echo "Starting local UI on http://localhost:5001 ..."
	PYTHONPATH=. poetry run python ui/app.py --port 5001

# Tests and code quality
test:
	@echo "Running tests..."
	poetry run pytest

test-db:
	@echo "Running database tests..."
	poetry run pytest tests/database/

test-sql:
	@echo "Testing SQL query generation..."
	@PYTHONPATH=. poetry run python tests/test_sql_generation.py

lint:
	@echo "Running linters..."
	poetry run flake8
	poetry run mypy .

format:
	@echo "Formatting code..."
	poetry run black .

# Vector operations
update-embeddings:
	@echo "Updating vector embeddings for all items..."
	PYTHONPATH=. poetry run python scripts/update_embeddings.py

all: install lint test
