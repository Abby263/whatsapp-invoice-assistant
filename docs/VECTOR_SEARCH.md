# Vector Search Implementation in WhatsApp Invoice Assistant

## Overview

The WhatsApp Invoice Assistant employs advanced semantic search capabilities using vector embeddings to provide intelligent, context-aware responses to user queries. This document explains the vector search implementation, including embedding generation, storage, retrieval, and the hybrid search approach that combines semantic similarity with traditional keyword matching.

## Table of Contents

1. [Architecture](#architecture)
2. [Embedding Generation](#embedding-generation)
3. [Vector Storage](#vector-storage)
4. [Search Implementation](#search-implementation)
5. [Hybrid Search Technique](#hybrid-search-technique)
6. [Configuration Options](#configuration-options)
7. [Performance Considerations](#performance-considerations)
8. [Examples](#examples)
9. [Implementation Details](#implementation-details)
10. [Validation Results](#validation-results)

## Architecture

The semantic search capability consists of several components:

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  Text/Invoice Input │     │  EmbeddingGenerator │     │  PostgreSQL         │
│  (items, queries)   │────▶│  (OpenAI/Sentence   │────▶│  (pgvector          │
└─────────────────────┘     │   Transformers)     │     │   extension)        │
                            └─────────────────────┘     └─────────────────────┘
                                                                    │
┌─────────────────────┐     ┌─────────────────────┐                │
│  Formatted Results  │     │  Search Service     │◀───────────────┘
│  to User            │◀────│  (Vector + Keyword) │
└─────────────────────┘     └─────────────────────┘
```

## Embedding Generation

The system generates vector embeddings for item descriptions and user queries using a hierarchical approach:

1. **Primary Method**: OpenAI's `text-embedding-3-small` model (1536 dimensions)
2. **Fallback Method**: Sentence Transformers library with `all-MiniLM-L6-v2` model (384 dimensions)
3. **Emergency Fallback**: Deterministic random embeddings when both methods fail

### Key Features

- **Caching**: Embeddings are cached to reduce API calls and improve performance
- **Batch Processing**: Multiple items can be processed in a single batch for efficiency
- **Error Handling**: Graceful degradation with fallback mechanisms
- **Dimension Standardization**: All embeddings are standardized to the configured dimension

## Vector Storage

Vector embeddings are stored in PostgreSQL using the `pgvector` extension, which enables:

1. **Vector Data Type**: A specialized column type for storing embeddings
2. **Similarity Metrics**: Support for various distance measures (L2, cosine, inner product)
3. **Efficient Indexing**: Approximate nearest neighbor search with IVFFlat indexing
4. **SQL Integration**: Seamless integration with standard SQL queries

### Schema Implementation

Two primary tables in our database store vector embeddings:

```sql
-- Items table with embeddings for individual line items
TABLE "public.items"
        Column         |            Type             | Collation | Nullable
-----------------------+-----------------------------+-----------+----------
 id                    | integer                     |           | not null
 invoice_id            | integer                     |           |         
 description           | character varying(255)      |           | not null
 quantity              | double precision            |           |         
 unit_price            | double precision            |           | not null
 total_price           | double precision            |           | not null
 item_category         | character varying(50)       |           |         
 item_code             | character varying(50)       |           |         
 description_embedding | vector(1536)                |           |         
 created_at            | timestamp without time zone |           |         
 updated_at            | timestamp without time zone |           |         

-- Invoice embeddings table for full document embeddings
TABLE "public.invoice_embeddings"
     Column     |            Type             | Collation | Nullable
----------------+-----------------------------+-----------+----------
 id             | integer                     |           | not null
 invoice_id     | integer                     |           | not null
 user_id        | integer                     |           | not null
 content_text   | text                        |           |         
 embedding      | vector(1536)                |           |         
 model_name     | character varying(100)      |           |         
 embedding_type | character varying(50)       |           |         
 created_at     | timestamp without time zone |           |         
 updated_at     | timestamp without time zone |           |         
```

## Search Implementation

The system performs vector similarity search using:

1. **L2 Distance**: Euclidean distance between vectors (lower values = more similar)
2. **Configurable Threshold**: Similarity cutoff point, currently set to 1.3
3. **Result Limiting**: Default configured to return top 10 matches

### Sample SQL Query

```sql
SELECT 
    i.description,
    i.quantity,
    i.unit_price,
    i.total_price,
    i.item_category,
    inv.vendor,
    inv.invoice_date,
    l2_distance(i.description_embedding, $1) as similarity_score
FROM 
    items i
JOIN 
    invoices inv ON i.invoice_id = inv.id
WHERE 
    i.user_id = $2
    AND l2_distance(i.description_embedding, $1) < $3
ORDER BY 
    similarity_score
LIMIT $4;
```

## Hybrid Search Technique

The WhatsApp Invoice Assistant combines vector similarity with keyword matching for optimal results:

1. **Vector Search**: Finds semantically similar items even when exact keywords aren't present
2. **Keyword Matching**: Prioritizes exact matches for higher precision
3. **Score Combination**: Weighted scoring that can boost exact matches while preserving semantic results

### Algorithm

The hybrid search process follows these steps:

1. Generate embeddings for the user query
2. Perform vector similarity search with configured threshold
3. Optionally perform keyword-based search
4. If hybrid search is enabled, combine and re-rank results
5. Return the top N results based on combined relevance score

## Configuration Options

The vector search system is highly configurable through `constants/vector_search_configs.py`:

```python
# Main configuration
VECTOR_SIMILARITY_THRESHOLD = 1.3  # L2 distance threshold (lower = more strict)
EMBEDDING_MODEL = "text-embedding-3-small"  # OpenAI model
EMBEDDING_DIMENSION = 1536  # Embedding dimension

# Search configuration
DEFAULT_VECTOR_SEARCH_CONFIG = {
    "similarity_threshold": VECTOR_SIMILARITY_THRESHOLD,
    "max_results": 10,
    "similarity_metric": "l2_distance",  # Options: l2_distance, cosine_similarity, dot_product
    "hybrid_search": True,
    "boost_exact_matches": True
}
```

## Performance Considerations

The vector search implementation includes several optimizations:

1. **Embedding Caching**: Prevents redundant API calls for the same text
2. **Batch Processing**: Reduces API overhead for multiple items
3. **PostgreSQL Indexing**: IVFFlat index for efficient similarity search
4. **Similarity Threshold**: Configurable to balance precision and recall
5. **Selective Embedding**: Only embedding relevant fields to reduce storage

## Examples

### Example 1: Semantic Item Search

```
User: "Show me items related to printing supplies"
```

Even if no items contain the exact phrase "printing supplies," the vector search will return semantically related items like:
- Printer ink cartridges
- Toner refills
- Copy paper
- Printer maintenance kits

### Example 2: Finding Similar Expenses

```
User: "What did I spend on beverages last month?"
```

This query would match items like:
- Coffee
- Tea
- Soft drinks
- Bottled water
- Energy drinks

### Example 3: Hybrid Search Advantage

For the query "Office desk chair," the system would:
1. Find exact matches for "office desk chair" (if any)
2. Find semantically similar items like "ergonomic chair," "computer chair," etc.
3. Rank the results with exact matches first, followed by semantic matches

## Implementation Details

The vector search is implemented in `utils/vector_utils.py` and includes:

### Embedding Generation Class

```python
class EmbeddingGenerator:
    def __init__(self, model_name=EMBEDDING_MODEL, embedding_dimension=EMBEDDING_DIMENSION):
        self.model_name = model_name
        self.embedding_dimension = embedding_dimension
        self.embedding_cache = {}
        self.openai_client = None
        self.sentence_transformer_model = None
        
    def generate_embedding(self, text):
        """Generate embedding for a single text"""
        # Implementation details...
        
    def generate_batch_embeddings(self, texts):
        """Generate embeddings for multiple texts in batch"""
        # Implementation details...
```

### Similarity Calculation

```python
def calculate_similarity(embedding1, embedding2, method="l2_distance"):
    """Calculate similarity between two embeddings using the specified method"""
    if method == "cosine_similarity":
        return cosine_similarity(embedding1, embedding2)
    elif method == "dot_product":
        return np.dot(embedding1, embedding2)
    else:  # Default to L2 distance
        return np.linalg.norm(np.array(embedding1) - np.array(embedding2))
```

### Database Integration

```python
def search_items_by_vector_similarity(db, query_embedding, user_id, 
                                     similarity_threshold=VECTOR_SIMILARITY_THRESHOLD, 
                                     max_results=10):
    """Search for similar items using vector similarity"""
    # Implementation details...
```

### Fallback Mechanism

```python
def generate_random_embedding(text, dimension=EMBEDDING_DIMENSION):
    """Generate a deterministic random embedding as fallback"""
    # Implementation details...
```

## Validation Results

The vector search implementation has been validated with:

### Environment
- PostgreSQL version: 14.17 (Homebrew)  
- pgvector extension: 0.8.0
- Vector dimension: 1536 (matching OpenAI's text-embedding-3-small model)

### Database Content
- 28 items with vector embeddings (100% of items have embeddings)
- Each item embedding is a 1536-dimensional vector
- 5 invoices in the database
- No IVFFlat index currently implemented (recommended for future scaling)

### Validation Queries

```sql
-- Confirmed pgvector extension installation
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';

-- Validated items with embeddings
SELECT COUNT(*) FROM items WHERE description_embedding IS NOT NULL;
> 28 (All items have embeddings)

-- Checked for vector indexes (none currently implemented)
SELECT indexname, indexdef FROM pg_indexes WHERE indexdef LIKE '%vector%';
> 0 rows
```

The WhatsApp Invoice Assistant's vector search implementation provides a powerful semantic understanding capability, allowing users to find information even when they don't know exact terms or item names. The hybrid approach balances precision and recall, ensuring both exact and semantically similar matches are returned. 