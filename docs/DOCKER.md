# Running WhatsApp Invoice Assistant with Docker

This guide explains how to run the WhatsApp Invoice Assistant using Docker, which allows you to run the application in a containerized environment without installing dependencies directly on your system.

## Prerequisites

- Docker installed on your system
- Docker Compose installed on your system
- OpenAI API key for LLM functionality

## Quick Start

The easiest way to start the application is using the provided script:

```bash
# Make sure the script is executable
chmod +x docker-run.sh

# Run the application
./docker-run.sh
```

Or you can use the Makefile commands:

```bash
# Build the Docker images
make docker-build

# Run the application
make docker-run

# Stop the application
make docker-stop
```

## Manual Setup

If you prefer to run the commands manually:

1. Make sure you have an OpenAI API key set in your environment:

```bash
export OPENAI_API_KEY=your-api-key-here
```

Or create a `.env` file with:

```
OPENAI_API_KEY=your-api-key-here
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
S3_BUCKET_NAME=your-s3-bucket-name
S3_REGION=us-east-1
```

2. Build and start the containers:

```bash
docker-compose up --build
```

3. Open your browser and navigate to:

```
http://localhost:5001
```

## Docker Components

The Docker setup includes:

- **UI Service**: A Flask application that provides a test interface for the WhatsApp Invoice Assistant
- **Database Service**: PostgreSQL with pgvector extension enabled for vector similarity search

## Configuration

The following environment variables can be configured:

- `OPENAI_API_KEY`: Your OpenAI API key for LLM functionality
- `DATABASE_URL`: The PostgreSQL connection string (default: `postgresql://postgres:postgres@db/whatsapp_invoice_assistant`)
- `AWS_ACCESS_KEY_ID`: Your AWS access key for S3 storage
- `AWS_SECRET_ACCESS_KEY`: Your AWS secret key for S3 storage
- `S3_BUCKET_NAME`: The S3 bucket name for file storage
- `S3_REGION`: The AWS region for S3 (default: `us-east-1`)

You can set these environment variables before running or add them to a `.env` file:

```
OPENAI_API_KEY=your-api-key-here
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
S3_BUCKET_NAME=your-s3-bucket-name
S3_REGION=us-east-1
```

If you don't provide AWS credentials, the application will use a fallback mode that simulates S3 storage with local placeholders.

## Data Persistence

Data is persisted in the following ways:

- **Database**: PostgreSQL data is stored in a Docker volume for persistence between restarts
- **Uploads**: Files uploaded to the application are stored in the `./uploads` directory, which is mounted as a volume

## Troubleshooting

### Database Connection Issues

If you encounter database connection issues:

1. Ensure the PostgreSQL container is running:
   ```bash
   docker-compose ps
   ```

2. Check the database logs:
   ```bash
   docker-compose logs db
   ```

### pgvector Extension Issues

If you encounter issues with the pgvector extension:

1. Connect to the database container:
   ```bash
   docker-compose exec db psql -U postgres -d whatsapp_invoice_assistant
   ```

2. Verify the extension is installed:
   ```sql
   SELECT * FROM pg_extension WHERE extname = 'vector';
   ```

### OpenAI API Issues

If the LLM functionality isn't working:

1. Ensure your OpenAI API key is correctly set in the environment
2. Check the UI service logs for any API errors:
   ```bash
   docker-compose logs ui
   ``` 