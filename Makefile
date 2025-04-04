.PHONY: start stop restart db-clean install dev test lint format db-migrate db-revision db-downgrade db-history test-db db-seed db-status

# Application management
start:
	@echo "Starting the WhatsApp Invoice Assistant..."
	poetry run uvicorn api.main:app --reload

stop:
	@echo "Stopping all running instances..."
	@-pkill -f "uvicorn api.main:app" || true
	@-pkill -f "celery" || true

restart: stop start

# Database management
db-clean:
	@echo "Cleaning database tables..."
	@poetry run python -c "from database.schemas import Base; from database.connection import engine; Base.metadata.drop_all(engine); Base.metadata.create_all(engine)"
	@echo "Database tables have been dropped and recreated."

db-status:
	@echo "Checking database status..."
	@PYTHONPATH=. poetry run python db_status.py

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

# Development tools
install:
	@echo "Installing dependencies..."
	poetry install
	poetry run pre-commit install

dev: install
	@echo "Starting development environment..."
	docker-compose up -d

test:
	@echo "Running tests..."
	poetry run pytest

test-db:
	@echo "Running database tests..."
	poetry run pytest tests/database/

lint:
	@echo "Running linters..."
	poetry run flake8
	poetry run mypy .

format:
	@echo "Formatting code..."
	poetry run black .

# Generate documentation
docs:
	@echo "Generating documentation..."
	# Add documentation generation commands here

# Default target
all: install lint test 