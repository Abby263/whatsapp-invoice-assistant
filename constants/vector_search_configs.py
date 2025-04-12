"""
Vector search configuration constants.

This module contains constants used for vector similarity search operations.
"""

# Threshold for vector similarity search (L2 distance)
# Lower values mean more strict matching
# Higher values mean more relaxed matching (will return more results)
# NOTE: With L2 distance, lower values are more similar, but we need to set
# a higher threshold to be more inclusive when semantic similarity is not exact
VECTOR_SIMILARITY_THRESHOLD = 1.3  

# Default vector similarity search parameters
DEFAULT_VECTOR_SEARCH_CONFIG = {
    "similarity_threshold": VECTOR_SIMILARITY_THRESHOLD,
    "max_results": 10,
    "similarity_metric": "l2_distance",  # Other options: "cosine_distance", "inner_product"
    "hybrid_search": True,  # Combine keyword and vector search
    "boost_exact_matches": True  # Apply higher weight to exact keyword matches
}

# Query embedding model configuration
QUERY_EMBEDDING_MODEL = "text-embedding-3-small"
QUERY_EMBEDDING_DIMENSION = 1536 