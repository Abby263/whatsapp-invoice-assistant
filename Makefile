.PHONY: start stop restart db-clean install dev test lint format db-migrate db-revision db-downgrade db-history test-db db-seed db-status ui-run ui-install ui-test test-sql update-embeddings memory-cleanup memory-cleanup-dry docker-build docker-run docker-stop poetry-update helm-lint helm-template helm-install helm-upgrade helm-uninstall

# Application management
start:
	@echo "Starting the WhatsApp Invoice Assistant..."
	poetry run uvicorn api.main:app --reload

stop:
	@echo "Stopping all running instances..."
	@-pkill -f "uvicorn api.main:app" || true
	@-pkill -f "celery" || true

restart: stop start

# Poetry management
poetry-update:
	@echo "Updating Poetry lock file..."
	poetry lock
	@echo "Installing dependencies..."
	poetry install --no-root

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

# UI Application
ui-install:
	@echo "Installing UI dependencies..."
	poetry run pip install flask

ui-run:
	@echo "Starting UI application..."
	PYTHONPATH=. USE_MONGODB=false poetry run python ui/app.py --port 5001

ui-test:
	@echo "Running the interactive test from the command line..."
	@PYTHONPATH=. poetry run python -m tests.interactive_test

test-sql:
	@echo "Testing SQL query generation..."
	@PYTHONPATH=. poetry run python tests/test_sql_generation.py

# Update embeddings for vector search
update-embeddings:
	@echo "Updating vector embeddings for all items..."
	PYTHONPATH=. poetry run python scripts/update_embeddings.py

# Memory management
memory-cleanup:
	@echo "Cleaning up old memory entries..."
	@PYTHONPATH=. poetry run python scripts/cleanup_memory.py --sync-db

memory-cleanup-dry:
	@echo "Dry run - checking which memory entries would be cleaned up..."
	@PYTHONPATH=. poetry run python scripts/cleanup_memory.py --sync-db --dry-run

# Docker management
docker-build:
	@echo "Building Docker images..."
	docker-compose build

docker-run:
	@echo "Starting the WhatsApp Invoice Assistant in Docker..."
	./docker-run.sh

docker-stop:
	@echo "Stopping Docker containers..."
	docker-compose down

# Helm chart management
helm-lint:
	@echo "Linting Helm chart..."
	helm lint helm/whatsapp-invoice-assistant

helm-template:
	@echo "Generating Kubernetes manifests from Helm chart..."
	helm template whatsapp-invoice-assistant helm/whatsapp-invoice-assistant -f helm/whatsapp-invoice-assistant/test-values.yaml

helm-install:
	@echo "Installing WhatsApp Invoice Assistant using Helm..."
	@echo "First updating dependencies..."
	helm dependency update helm/whatsapp-invoice-assistant
	@echo "Installing chart..."
	helm install whatsapp-invoice-assistant helm/whatsapp-invoice-assistant -f helm/whatsapp-invoice-assistant/test-values.yaml

helm-upgrade:
	@echo "Upgrading WhatsApp Invoice Assistant using Helm..."
	@echo "First updating dependencies..."
	helm dependency update helm/whatsapp-invoice-assistant
	@echo "Upgrading chart..."
	helm upgrade whatsapp-invoice-assistant helm/whatsapp-invoice-assistant -f helm/whatsapp-invoice-assistant/test-values.yaml

helm-uninstall:
	@echo "Uninstalling WhatsApp Invoice Assistant using Helm..."
	helm uninstall whatsapp-invoice-assistant

# Default target
all: install lint test
