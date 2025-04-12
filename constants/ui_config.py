"""
Constants for UI configuration.

This module contains configuration values for the UI application.
"""

import os
import uuid

# Default conversation values
DEFAULT_WHATSAPP_NUMBER = "+1234567890"
DEFAULT_CONVERSATION_ID = str(uuid.uuid4())

# Maximum number of messages to display in chat history
MAX_CHAT_HISTORY = 50

# UI settings
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload

# Directory settings
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'uploads')

# Vector database configuration
VECTOR_EXTENSION_NAME = "vector"  # Name of the PostgreSQL extension for vectors
DEFAULT_VECTOR_DIMENSION = 1536   # Default dimension for OpenAI embeddings
DEFAULT_VECTOR_OPS = "vector_cosine_ops"  # Default vector operator for similarity searches 