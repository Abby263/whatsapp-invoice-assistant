# WhatsApp Invoice Assistant

An AI-powered WhatsApp bot for processing and managing invoice data. The application allows users to upload invoices via WhatsApp, receive AI-generated summaries, and ask questions about their invoices.

## Features

- Uploads and processes invoices from various formats (images, PDFs, Excel, CSV)
- Extracts invoice data using AI (GPT-4o-mini)
- Stores structured invoice data in PostgreSQL
- Answers natural language queries about invoice data
- Handles multiple types of user interactions through WhatsApp

## Technology Stack

- **Backend Framework**: FastAPI
- **Database**: PostgreSQL with SQLAlchemy ORM and Alembic for migrations
- **AI Model**: GPT-4o-mini via OpenAI API
- **Workflow Orchestration**: LangGraph
- **Agent Definition**: Pydantic models
- **Asynchronous Tasks**: Celery with Redis
- **File Storage**: Amazon S3
- **WhatsApp Integration**: Twilio
- **Containerization**: Docker and Kubernetes

## Getting Started

### Prerequisites

- Python 3.9+
- PostgreSQL
- Redis
- OpenAI API key
- Twilio account with WhatsApp integration
- AWS S3 bucket

### Installation

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/whatsapp-invoice-assistant.git
   cd whatsapp-invoice-assistant
   ```

2. Set up environment variables:
   ```
   cp .env.example .env
   # Edit .env with your credentials
   ```

3. Install dependencies using Poetry:
   ```
   make install
   ```

4. Start the development environment:
   ```
   make dev
   ```

### Database Setup

1. Ensure PostgreSQL is running and accessible with the credentials specified in your `.env` file.

2. Run database migrations to create the schema:
   ```
   make db-migrate
   ```

3. (Optional) Seed the database with test data:
   ```
   make db-seed
   ```

### Configuration Management

The application uses a centralized configuration system with multiple layers:

1. **Environment Variables**: Core settings are loaded from `.env` file or system environment variables.

2. **YAML Configuration**: Extended settings are managed in `config/env.yaml`. The values in this file can reference environment variables.

3. **Runtime Configuration**: The `utils/config.py` module provides utilities to access all configuration settings.

Example configuration usage:
```python
from utils.config import config

# Access a database setting
db_host = config.get("database", "host")

# Access the full database section
db_config = config.get("database")
```

### Working with Migrations

To manage database schema changes:

1. Create a new migration:
   ```
   make db-revision description="Add new column"
   ```

2. Apply pending migrations:
   ```
   make db-migrate
   ```

3. Downgrade to a previous migration:
   ```
   make db-downgrade
   ```

4. View migration history:
   ```
   make db-history
   ```

## Project Structure

```
project_root/
│
├── agents/                    # Agent-related code
├── workflows/                 # Workflow definitions
├── memory/                    # Memory management for state
├── database/                  # Database models and operations
│   ├── schemas.py            # SQLAlchemy ORM models
│   ├── models.py             # Pydantic validation models
│   ├── crud.py               # CRUD operations
│   ├── connection.py         # Database connection utilities
│   └── migrations/           # Alembic migration scripts
├── storage/                   # S3 storage integration
├── services/                  # External service integrations
├── tasks/                     # Celery async tasks
├── utils/                     # Utility functions
│   ├── config.py             # Configuration utilities
│   └── logging.py            # Logging setup
├── constants/                 # Constant definitions
├── prompts/                   # LLM prompt templates
├── templates/                 # Response templates
├── api/                       # FastAPI application
├── tests/                     # Test suite
│   ├── database/             # Database tests
│   └── utils/                # Utility tests
├── docker/                    # Docker configuration
└── kubernetes/                # Kubernetes manifests
```

## Development

### Running Tests

```
# Run all tests
make test

# Run database-specific tests
make test-db

# Run specific test file
poetry run pytest tests/database/test_models.py
```

### Database Management

```
# Reset database (drop and recreate all tables)
make db-clean

# Apply migrations
make db-migrate

# Create a new migration
make db-revision description="Description of the change"
```

### Code Formatting and Linting

```
make format
make lint
```

### Starting the Application

```
make start
```

## License

[Specify the license here]

## Contributors

[List the contributors here] 