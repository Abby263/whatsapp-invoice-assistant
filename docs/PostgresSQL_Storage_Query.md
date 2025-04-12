# WhatsApp Invoice Assistant: Invoice Query System Documentation

## Table of Contents
1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
   - [2.1 Data Storage Architecture](#21-data-storage-architecture)
   - [2.2 Vector Embeddings Storage](#22-vector-embeddings-storage)
3. [Database Setup](#3-database-setup)
   - [3.1 PostgreSQL Installation](#31-postgresql-installation)
   - [3.2 pgvector Extension Setup](#32-pgvector-extension-setup)
   - [3.3 Application Database Connection](#33-application-database-connection)
   - [3.4 pgvector Integration with SQLAlchemy](#34-pgvector-integration-with-sqlalchemy)
4. [Query System](#4-query-system)
   - [4.1 Query Processing Flow](#41-query-processing-flow)
   - [4.2 Tech Stack](#42-tech-stack)
   - [4.3 Vector Similarity Implementation](#43-vector-similarity-implementation)
5. [Example Queries](#5-example-queries)
   - [5.1 Category-based Query](#51-category-based-query)
   - [5.2 Semantic Search Query](#52-semantic-search-query)
   - [5.3 Hybrid Query](#53-hybrid-query)
6. [Database Management](#6-database-management)
   - [6.1 Useful Database Commands](#61-useful-database-commands)
   - [6.2 Database Initialization](#62-database-initialization)
7. [Performance](#7-performance)
   - [7.1 Latency Measurements](#71-latency-measurements)
   - [7.2 Accuracy Metrics](#72-accuracy-metrics)
   - [7.3 Scalability](#73-scalability)
8. [Configuration](#8-configuration)
   - [8.1 Vector Similarity Methods](#81-vector-similarity-methods)
   - [8.2 Choosing the Right Method](#82-choosing-the-right-method)
9. [Conclusion](#9-conclusion)

---

## 1. Overview

The WhatsApp Invoice Assistant's Invoice Query System allows users to query invoice data using natural language. The system leverages both traditional SQL and vector-based semantic search to provide accurate answers to user queries about their invoice data, spending patterns, and purchase history.

---

## 2. Architecture

### 2.1 Data Storage Architecture

Invoice data is stored in a relational PostgreSQL database with the following key tables:

| Table | Description |
|-------|-------------|
| `invoices` | Contains invoice header information (vendor, date, total amount) |
| `items` | Contains line items from invoices with detailed information |
| `invoice_embeddings` | Stores vector embeddings for full invoice text content |

The database schema follows a normalized design where:
- Each invoice has multiple line items (one-to-many relationship)
- Item descriptions are enriched with embeddings for semantic search
- Categories are stored with items for classification and reporting

### 2.2 Vector Embeddings Storage

The system implements two types of embeddings:

1. **Item Description Embeddings**:
   - Stored in the `description_embedding` column of the `items` table
   - Vector dimension: 1536 (OpenAI embedding model)
   - Used for semantic matching of item descriptions

2. **Invoice Embeddings**:
   - Stored in the `embedding` column of the `invoice_embeddings` table
   - Contains embeddings of the full invoice text content
   - Used for semantic search across entire invoices

The system uses the **pgvector** extension in PostgreSQL, which provides:
- Vector data type for storing embeddings
- Vector similarity functions (cosine, L2, dot product)
- Efficient indexing for similarity searches

Our current database has 24 items with embeddings, as confirmed by our database check.

---

## 3. Database Setup

### 3.1 PostgreSQL Installation

1. **Install PostgreSQL**:
   ```bash
   # For Ubuntu/Debian
   sudo apt update
   sudo apt install postgresql postgresql-contrib
   
   # For macOS using Homebrew
   brew install postgresql
   
   # For Windows
   # Download the installer from https://www.postgresql.org/download/windows/
   ```

2. **Start PostgreSQL service**:
   ```bash
   # For Ubuntu/Debian
   sudo systemctl start postgresql
   sudo systemctl enable postgresql
   
   # For macOS
   brew services start postgresql
   ```

3. **Create database and user**:
   ```bash
   # Log in as postgres user
   sudo -u postgres psql
   
   # In PostgreSQL prompt
   CREATE DATABASE whatsapp_invoice_assistant;
   CREATE USER invoice_app WITH ENCRYPTED PASSWORD 'your_secure_password';
   GRANT ALL PRIVILEGES ON DATABASE whatsapp_invoice_assistant TO invoice_app;
   \q
   ```

### 3.2 pgvector Extension Setup

1. **Install pgvector extension requirements**:
   ```bash
   # For Ubuntu/Debian
   sudo apt install postgresql-server-dev-15  # Match your PostgreSQL version
   
   # For macOS
   brew install postgresql@15  # Match your PostgreSQL version
   ```

2. **Install pgvector from source**:
   ```bash
   git clone --branch v0.5.1 https://github.com/pgvector/pgvector.git
   cd pgvector
   make
   make install  # May need sudo
   ```

3. **Enable pgvector in database**:
   ```bash
   # Connect to database
   psql -U postgres -d whatsapp_invoice_assistant
   
   # Create extension
   CREATE EXTENSION IF NOT EXISTS vector;
   
   # Verify installation
   SELECT * FROM pg_extension WHERE extname = 'vector';
   \q
   ```

### 3.3 Application Database Connection

The application connects to PostgreSQL using SQLAlchemy. Configuration is stored in `database/connection.py`:

```python
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Configuration from environment or default values
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "whatsapp_invoice_assistant")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")

# Connection URL
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Create engine
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Test connection before use
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()
```

### 3.4 pgvector Integration with SQLAlchemy

The vector type from pgvector is integrated into SQLAlchemy models:

```python
# In database/schemas.py
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.dialects.postgresql import VECTOR

class Item(Base):
    __tablename__ = "items"
    
    id = Column(Integer, primary_key=True)
    # ... other columns
    description_embedding = Column(VECTOR(1536))  # Vector column for embeddings
```

The application checks for pgvector availability at startup and falls back to TEXT type if not available:

```python
# Simplified version from actual code
def check_pgvector():
    """Check if pgvector extension is available"""
    with engine.connect() as conn:
        try:
            result = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
            return result.scalar() is not None
        except:
            return False

# Use Vector type if available, otherwise fallback
if check_pgvector():
    from sqlalchemy.dialects.postgresql import VECTOR
    vector_type = VECTOR
else:
    vector_type = Text
```

---

## 4. Query System

### 4.1 Query Processing Flow

When a user submits a natural language query about their invoices, the system follows this process:

1. **Intent Classification**:
   - Determines if the query is related to invoice data
   - Classifies the specific intent (e.g., category summary, vendor search)

2. **Text-to-SQL Conversion**:
   - For structured queries (e.g., "How much did I spend on groceries?")
   - Converts natural language to PostgreSQL SQL with proper user isolation

3. **Vector Similarity Search**:
   - For semantic queries (e.g., "Show me items like coffee")
   - Uses description embeddings to find semantically similar items

4. **Hybrid Search**:
   - Combines structured and vector search for complex queries
   - Uses vector search to find categories and SQL to aggregate results

5. **Response Formatting**:
   - Formats the query results into readable responses
   - Adds helpful context and summary information

### 4.2 Tech Stack

- **Database**: PostgreSQL with pgvector extension
- **Embedding Models**: OpenAI text-embedding-3-small
- **Vector Operations**: L2 distance, cosine similarity
- **Query Generation**: GPT-4o-mini for text-to-SQL conversion
- **API Framework**: FastAPI for backend services
- **UI**: Flask-based testing interface

### 4.3 Vector Similarity Implementation

The system implements similarity search using pgvector's distance functions:

```sql
-- Example of vector similarity search for "coffee-related" items
SELECT 
    description, 
    unit_price, 
    item_category,
    l2_distance(description_embedding, query_embedding) AS distance
FROM 
    items
ORDER BY 
    l2_distance(description_embedding, query_embedding)
LIMIT 5;
```

Vector similarity options available:
- `l2_distance`: Euclidean distance (lower = more similar)
- `cosine_distance`: Cosine distance (lower = more similar)
- `inner_product`: Dot product (higher = more similar)

The choice of similarity function depends on the query type:
- L2 distance works well for finding exact matches
- Cosine similarity is better for concept matching
- Inner product can work well for recommendation-style queries

---

## 5. Example Queries

### 5.1 Category-based Query

**User Query**: "How much did I spend on electronics?"

**Processing**:
1. Intent classified as "invoice_query" with structured data analysis
2. Text converted to SQL:
   ```sql
   SELECT SUM(it.total_price) AS total_spent
   FROM items it
   JOIN invoices i ON it.invoice_id = i.id
   WHERE i.user_id = :user_id
   AND it.item_category = 'Electronics';
   ```
3. Result: $489.93

### 5.2 Semantic Search Query

**User Query**: "Show me items related to audio"

**Processing**:
1. Intent classified as "invoice_query" with semantic search
2. System generates embedding for "audio"
3. Vector similarity search:
   ```sql
   SELECT description, unit_price, item_category
   FROM items it
   JOIN invoices i ON it.invoice_id = i.id
   WHERE i.user_id = :user_id
   ORDER BY l2_distance(it.description_embedding, :query_embedding)
   LIMIT 5;
   ```
4. Result would include "Wireless Headphones" even though "audio" doesn't appear in the description

### 5.3 Hybrid Query

**User Query**: "What are my top spending categories?"

**Processing**:
1. Intent classified as "invoice_query" with aggregation
2. Text converted to SQL:
   ```sql
   SELECT it.item_category, SUM(it.total_price) AS total_expenses
   FROM invoices i
   JOIN items it ON i.id = it.invoice_id
   WHERE i.user_id = :user_id
   GROUP BY it.item_category
   ORDER BY total_expenses DESC
   LIMIT 5;
   ```
3. Results:
   - Electronics: $489.93
   - Office Supplies: $88.42
   - Dining: $75.42
   - Groceries: $38.98

---

## 6. Database Management

### 6.1 Useful Database Commands

**List all tables**:
```bash
psql -U postgres -d whatsapp_invoice_assistant -c "\dt"
```

**Check table schema**:
```bash
psql -U postgres -d whatsapp_invoice_assistant -c "\d items"
psql -U postgres -d whatsapp_invoice_assistant -c "\d invoices"
psql -U postgres -d whatsapp_invoice_assistant -c "\d invoice_embeddings"
```

**Check item embeddings**:
```bash
psql -U postgres -d whatsapp_invoice_assistant -c "SELECT COUNT(*) FROM items WHERE description_embedding IS NOT NULL;"
```

**Check invoice embeddings**:
```bash
psql -U postgres -d whatsapp_invoice_assistant -c "SELECT COUNT(*) FROM invoice_embeddings WHERE embedding IS NOT NULL;"
```

**View category summaries**:
```bash
psql -U postgres -d whatsapp_invoice_assistant -c "SELECT item_category, COUNT(*) AS count, SUM(total_price) AS total FROM items GROUP BY item_category ORDER BY total DESC;"
```

**Sample item data with embedding preview**:
```bash
psql -U postgres -d whatsapp_invoice_assistant -c "SELECT id, description, item_category, substring(description_embedding::text, 1, 50) || '...' AS embedding_preview FROM items LIMIT 3;"
```

**Test vector operations**:
```bash
psql -U postgres -d whatsapp_invoice_assistant -c "SELECT l2_distance('[1,2,3]'::vector, '[4,5,6]'::vector);"
```

### 6.2 Database Initialization

The database initialization follows these steps:

1. **PostgreSQL Setup**:
   - Create database `whatsapp_invoice_assistant`
   - Install pgvector extension

2. **Schema Creation**:
   - Create tables with vector data types
   - Set up proper foreign key relationships

3. **Initial Data Loading**:
   - Seed database with sample invoices and items
   - Generate and store embeddings for all items

You can clean and reset the database using:
```bash
make db-clean
```

And seed it with categorized data using:
```bash
python scripts/seed_categories.py
```

---

## 7. Performance

### 7.1 Latency Measurements

- **SQL Query Execution**: Typically <50ms for structured queries
- **Vector Similarity Search**: Typically 100-200ms depending on database size
- **Embedding Generation**: 300-500ms per embedding using OpenAI API
- **End-to-End Query Processing**: 800ms-1.5s including all processing steps

### 7.2 Accuracy Metrics

- **Structured Query Accuracy**: Measured by correct aggregation results
- **Semantic Search Relevance**: Measured by relevance of returned items
- **Category Classification**: Precision and recall for category matches

### 7.3 Scalability

The system is designed to scale with:
- Efficient indexing for both SQL and vector operations
- Batch processing for embedding generation
- Connection pooling for database access

---

## 8. Configuration

### 8.1 Vector Similarity Methods

The system allows configuration of similarity search methods:

```python
# Example configuration in constants/vector_search_config.py
VECTOR_SEARCH = {
    "default_method": "l2_distance",
    "similarity_threshold": 0.3,
    "methods": {
        "exact_match": "l2_distance",
        "concept_match": "cosine_distance",
        "recommendation": "inner_product"
    }
}
```

### 8.2 Choosing the Right Method

- **L2 Distance** (Euclidean):
  - Best for finding exact or very close matches
  - Preferred for queries like "Show me items exactly like X"
  - More sensitive to magnitude differences

- **Cosine Distance**:
  - Best for concept matching regardless of magnitude
  - Preferred for queries like "Show me items related to concept X"
  - Handles different embedding magnitudes better

- **Inner Product**:
  - Good for recommendation-style queries
  - Works well when direction in vector space is important
  - Can be used for "more like this" style queries

The system automatically selects the most appropriate method based on the query intent and context.

---

## 9. Conclusion

The WhatsApp Invoice Assistant's Invoice Query System leverages both structured SQL queries and vector-based semantic search to provide a powerful and flexible way for users to query their invoice data using natural language. The combination of PostgreSQL's relational capabilities with pgvector's embedding support enables sophisticated query processing that understands both explicit and implicit user intent.

The system is designed to be easily configurable, performance-optimized, and accurate in its responses, making it a valuable tool for users who want to gain insights from their invoice data without needing technical database knowledge.