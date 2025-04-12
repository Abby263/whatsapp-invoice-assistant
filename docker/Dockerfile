FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    git \
    curl \
    postgresql-client \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry==1.6.1

# Copy project configuration files
COPY pyproject.toml poetry.lock* ./

# Configure Poetry to not use a virtual environment in the container
RUN poetry config virtualenvs.create false

# Install dependencies - update the lock file first, then install without root project
RUN poetry lock
RUN poetry install --no-interaction --no-ansi --no-root

# Add additional Python packages for vector support
RUN pip install --no-cache-dir pgvector psycopg2-binary pymongo motor

# Create necessary directories
RUN mkdir -p uploads
RUN mkdir -p logs

# Copy application code
COPY . .

# Ensure the upload directory is writable
RUN chmod 777 uploads
RUN chmod 777 logs

# Expose the ports for the application
EXPOSE 5001
EXPOSE 8000

# Environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Health check to verify the application is running correctly
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:5001/ || exit 1

# Set entry point to ensure proper command execution
ENTRYPOINT ["python"]

# Default command to run the Flask UI test interface
CMD ["ui/app.py", "--host", "0.0.0.0", "--port", "5001"] 