# MongoDB Memory Management

## Overview

This document explains how MongoDB is used for memory management in the WhatsApp Invoice Assistant. The application uses MongoDB as a persistence layer for conversation memory and LangGraph workflow state, providing stateful conversation capabilities across user interactions.

## Key Features

- **Conversation Persistence**: Store and retrieve conversation history between user sessions
- **LangGraph Checkpoint Storage**: Save workflow state for resuming conversations
- **Configurable Memory Settings**: Adjust memory parameters through environment variables
- **Graceful Fallback**: Automatic fallback to in-memory storage if MongoDB is unavailable
- **Automatic Memory Management**: Time-based expiration and message limiting

## Architecture

The memory system in WhatsApp Invoice Assistant consists of three main components:

1. **LangGraphMemory**: High-level memory management with configurable settings
2. **MongoDBMemory**: Direct MongoDB persistence implementation
3. **MongoDBCheckpointSaver**: LangGraph checkpoint integration for workflow state

### MongoDB Collections

- **conversations**: Stores metadata about conversations (user_id, conversation_id, last_accessed)
- **messages**: Stores individual messages in conversations
- **langgraph_checkpoints**: Stores LangGraph workflow state for resuming conversations

## Setup Instructions

### Prerequisites

- MongoDB 4.4+ (6.0 recommended)
- PyMongo library
- LangGraph with checkpoint support

### Docker Compose Setup

The easiest way to set up MongoDB for the application is using the provided Docker Compose configuration:

```bash
# Start MongoDB using Docker Compose
docker-compose up -d mongodb
```

The MongoDB service in Docker Compose is configured with:
- Port: 27018 (mapped from internal 27017)
- Volume: mongodb_data for persistent storage
- Health check: Ensures MongoDB is running before starting dependent services
- Database: whatsapp_invoice_assistant

### Manual Setup

If you prefer to set up MongoDB manually:

1. Install MongoDB following the [official documentation](https://www.mongodb.com/docs/manual/installation/)

2. Start MongoDB server:
   ```bash
   mongod --dbpath /path/to/data/directory
   ```

3. Create the necessary database:
   ```bash
   mongo
   > use whatsapp_invoice_assistant
   ```

## Configuration

### Environment Variables

The following environment variables can be used to configure MongoDB memory:

| Variable | Description | Default |
|----------|-------------|---------|
| MONGODB_URI | MongoDB connection URI | mongodb://mongodb:27017/whatsapp_invoice_assistant |
| USE_MONGODB | Whether to use MongoDB for persistence | true |
| MONGODB_MAX_MESSAGES | Maximum messages to store per conversation | 50 |
| MONGODB_MAX_MEMORY_AGE | Maximum age of memory in seconds | 3600 (1 hour) |
| MONGODB_MESSAGE_WINDOW | Number of recent messages to include in context | 10 |
| MONGODB_ENABLE_CONTEXT_WINDOW | Whether to enable context windowing | true |
| MONGODB_PERSIST_MEMORY | Whether to persist memory | true |

### Configuration in env.yaml

The memory settings can also be configured in `config/env.yaml`:

```yaml
mongodb:
  uri: ${MONGODB_URI:-mongodb://localhost:27017/whatsapp_invoice_assistant}
  use_mongodb: ${USE_MONGODB:-true}
  db_name: "whatsapp_invoice_assistant"
  checkpoint_collection: "langgraph_checkpoints"
  ttl_seconds: 86400  # 24 hours
  memory:
    max_messages: ${MONGODB_MAX_MESSAGES:-50}
    max_memory_age: ${MONGODB_MAX_MEMORY_AGE:-3600}
    message_window: ${MONGODB_MESSAGE_WINDOW:-10}
    enable_context_window: ${MONGODB_ENABLE_CONTEXT_WINDOW:-true}
    persist_memory: ${MONGODB_PERSIST_MEMORY:-true}
```

## Usage

### Basic Usage in Code

The main memory manager is instantiated automatically when the application starts:

```python
from memory.langgraph_memory import memory_manager

# Store state in memory
memory_manager.store(conversation_id, user_id, state_dict)

# Retrieve state from memory
memory_entry = memory_manager.retrieve(conversation_id)

# Get windowed conversation history
windowed_history = memory_manager.get_windowed_history(conversation_history)
```

### Updating Memory Configuration

Memory settings can be updated at runtime using the API:

```python
# Update memory settings
memory_manager.update_config(
    max_messages=100,
    message_window=15,
    max_memory_age=7200,  # 2 hours
    enable_context_window=True,
    persist_memory=True
)

# Get current memory configuration
config = memory_manager.get_config()
```

### Checking MongoDB Status

You can check the status of the MongoDB memory system:

```bash
# Using MongoDB CLI
mongo mongodb://localhost:27018/whatsapp_invoice_assistant
> db.conversations.count()
> db.messages.count()
> db.langgraph_checkpoints.count()

# Or using the UI
# Navigate to http://localhost:5001 and check the Memory Settings panel
```

## Implementation Details

### Integration with LangGraph

The application integrates MongoDB with LangGraph using a custom checkpoint saver:

```python
from memory.langgraph_mongodb_checkpoint import create_mongodb_checkpoint_saver

# Create a MongoDB checkpoint saver for a LangGraph workflow
mongo_saver = create_mongodb_checkpoint_saver()
graph = builder.compile(checkpointer=mongo_saver)
```

### Fallback Mechanism

If MongoDB is unavailable or disabled, the system automatically falls back to in-memory storage:

```python
try:
    # Try to use MongoDB
    result = mongodb_memory.store(conversation_id, user_id, state)
except Exception as e:
    logger.error(f"Error storing in MongoDB: {str(e)}")
    # Fall back to in-memory storage
    result = in_memory_store(conversation_id, user_id, state)
```

## Best Practices

1. **Indexing**: The application automatically creates appropriate indexes for efficient querying:
   - Unique index on `conversation_id` in the conversations collection
   - Compound index on `(conversation_id, timestamp)` in the messages collection
   - TTL index on `last_accessed` for automatic expiration

2. **Memory Management**: Configure memory settings based on your application needs:
   - For chatbots with complex tasks, increase `message_window` to 15-20
   - For simple assistants, reduce `message_window` to 5-8
   - Set appropriate `max_memory_age` based on expected user session duration

3. **Performance Monitoring**:
   - Monitor MongoDB performance using MongoDB Compass or similar tools
   - Check database size and growth rate periodically
   - Consider adding additional indexes if query performance degrades

4. **Security**:
   - Use MongoDB authentication with username/password
   - Set up network security rules to restrict access to MongoDB
   - Consider encrypting sensitive conversation data

## Troubleshooting

### Common Issues

1. **Connection Errors**:
   - Check that MongoDB is running and accessible from the application
   - Verify the MONGODB_URI environment variable is correctly set
   - Check network configuration if MongoDB is on a different host

2. **High Memory Usage**:
   - Reduce the `max_messages` setting to store fewer messages per conversation
   - Decrease the `max_memory_age` to expire old conversations more quickly
   - Consider adding database cleanup scripts for very large deployments

3. **Slow Queries**:
   - Check MongoDB logs for slow operations
   - Verify that indexes are being used correctly
   - Consider adding additional indexes based on your query patterns

### Diagnostic Commands

```bash
# Check MongoDB logs
docker-compose logs mongodb

# Connect to MongoDB shell
docker-compose exec mongodb mongosh

# Check application logs for MongoDB-related errors
grep "MongoDB" logs/app.log
```

## Related Documentation

- [MongoDB Documentation](https://www.mongodb.com/docs/)
- [LangGraph Persistence Documentation](https://langchain-ai.github.io/langgraph/concepts/persistence/)
- [PyMongo Documentation](https://pymongo.readthedocs.io/) 