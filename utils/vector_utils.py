"""
Vector embedding utilities for semantic search.

This module provides utilities for generating and managing vector embeddings
for item descriptions, enabling semantic search capabilities.
"""
import logging
from typing import List, Dict, Any, Optional, Union
import numpy as np
import random
import hashlib
import functools

from utils.config import config

# Get settings
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536

# Try to import sentence_transformers, use fallback if not available
sentence_transformers_available = True
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    sentence_transformers_available = False
    logging.warning("sentence-transformers not installed, using random embedding fallback")

logger = logging.getLogger(__name__)

# Embedding cache
_embedding_cache = {}  # Simple in-memory cache
_cache_size_limit = 1000  # Limit cache size to avoid memory issues

# Function to generate a deterministic cache key
def _cache_key(text: str) -> str:
    """Generate a unique, deterministic cache key for text."""
    return hashlib.md5(text.encode('utf-8')).hexdigest()

try:
    import openai
    from openai import OpenAI
    OPENAI_AVAILABLE = True
    logger.info("OpenAI API successfully imported")
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI API not available. Please install with: pip install openai")

# Try to import the sentence_transformers package
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
    logger.info("Sentence Transformers successfully imported")
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning("Sentence Transformers not available. Please install with: pip install sentence-transformers")

class EmbeddingGenerator:
    """Class for generating vector embeddings for text."""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize the embedding generator.
        
        Args:
            model_name: Name of the model to use for sentence transformers (not used for OpenAI)
        """
        self.model = None
        self.model_name = model_name
        self.embedding_dim = EMBEDDING_DIMENSION  # Default dimension from config
        self.use_openai = False
        self.openai_client = None
        
        # First try OpenAI
        if OPENAI_AVAILABLE:
            try:
                self.openai_client = OpenAI()
                self.use_openai = True
                logger.info(f"Using OpenAI for embeddings generation with model: {EMBEDDING_MODEL}")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {str(e)}")
                self.use_openai = False
        
        # Fall back to Sentence Transformers if OpenAI is not available
        if not self.use_openai and SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                logger.info(f"Initializing embedding generator with model: {model_name}")
                self.model = SentenceTransformer(model_name)
                self.embedding_dim = self.model.get_sentence_embedding_dimension()
                logger.info(f"Embedding model loaded successfully with dimension: {self.embedding_dim}")
            except Exception as e:
                logger.error(f"Failed to load embedding model: {str(e)}")
                self.model = None

    def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate an embedding for a piece of text.
        
        Args:
            text: The text to generate an embedding for
            
        Returns:
            A list of floats representing the embedding, or None if generation failed
        """
        if not text or len(text.strip()) == 0:
            logger.warning("Empty text provided for embedding generation")
            return None
            
        # Check cache first
        cache_key = _cache_key(text)
        if cache_key in _embedding_cache:
            logger.debug(f"Using cached embedding for text: {text[:50]}...")
            return _embedding_cache[cache_key]
            
        # OpenAI approach
        if self.use_openai and self.openai_client:
            try:
                logger.info(f"Generating OpenAI embedding for text: {text[:50]}...")
                response = self.openai_client.embeddings.create(
                    input=text,
                    model=EMBEDDING_MODEL
                )
                
                embedding = response.data[0].embedding
                
                # Cache the embedding
                if len(_embedding_cache) < _cache_size_limit:
                    _embedding_cache[cache_key] = embedding
                    logger.debug(f"Added OpenAI embedding to cache. Cache size: {len(_embedding_cache)}")
                
                return embedding
            except Exception as e:
                logger.error(f"Error generating OpenAI embedding: {str(e)}")
                # Fall through to sentence-transformers or random fallback
        
        # Sentence Transformers approach
        if self.model:
            try:
                logger.debug(f"Generating sentence transformer embedding for text: {text[:50]}...")
                embedding = self.model.encode(text).tolist()
                
                # Cache the embedding
                if len(_embedding_cache) < _cache_size_limit:
                    _embedding_cache[cache_key] = embedding
                    logger.debug(f"Added embedding to cache. Cache size: {len(_embedding_cache)}")
                
                return embedding
            except Exception as e:
                logger.error(f"Error generating embedding: {str(e)}")
                # Fall through to random fallback
        
        # If we reach here, use a fallback random embedding approach
        logger.warning("Using random embedding fallback")
        
        # Deterministic random embedding based on text hash
        # This ensures the same text always gets the same "random" embedding
        seed = int(hashlib.md5(text.encode('utf-8')).hexdigest(), 16) % 10000000
        random.seed(seed)
        
        # Generate a random embedding of the correct dimension (384 for sentence-transformers, 1536 for OpenAI)
        embedding = [(random.random() * 2 - 1) * 0.1 for _ in range(self.embedding_dim)]
        
        # Cache the fallback embedding
        if len(_embedding_cache) < _cache_size_limit:
            _embedding_cache[cache_key] = embedding
            logger.debug(f"Added fallback embedding to cache. Cache size: {len(_embedding_cache)}")
        
        return embedding

    def generate_batch_embeddings(self, texts: List[str]) -> List[Optional[List[float]]]:
        """
        Generate embeddings for a batch of texts.
        
        Args:
            texts: List of texts to generate embeddings for
            
        Returns:
            List of embeddings, one for each input text
        """
        if not texts:
            logger.warning("Empty text list provided for batch embedding generation")
            return []
            
        # Use OpenAI for batch embeddings if available
        if self.use_openai and self.openai_client:
            try:
                # Filter out empty texts
                valid_texts = [t for t in texts if t and len(t.strip()) > 0]
                if not valid_texts:
                    return [None] * len(texts)
                
                # Check cache for all texts
                embeddings = []
                uncached_indices = []
                uncached_texts = []
                
                for i, text in enumerate(valid_texts):
                    cache_key = _cache_key(text)
                    if cache_key in _embedding_cache:
                        embeddings.append(_embedding_cache[cache_key])
                    else:
                        embeddings.append(None)  # Placeholder
                        uncached_indices.append(i)
                        uncached_texts.append(text)
                
                # If there are uncached texts, get their embeddings
                if uncached_texts:
                    logger.info(f"Generating batch OpenAI embeddings for {len(uncached_texts)} texts")
                    response = self.openai_client.embeddings.create(
                        input=uncached_texts,
                        model=EMBEDDING_MODEL
                    )
                    
                    # Update embeddings list and cache
                    for i, embedding_data in enumerate(response.data):
                        original_idx = uncached_indices[i]
                        embedding = embedding_data.embedding
                        embeddings[original_idx] = embedding
                        
                        # Cache the embedding
                        cache_key = _cache_key(uncached_texts[i])
                        if len(_embedding_cache) < _cache_size_limit:
                            _embedding_cache[cache_key] = embedding
                
                # Map back to original texts order (including empty texts)
                result = []
                valid_idx = 0
                for text in texts:
                    if text and len(text.strip()) > 0:
                        result.append(embeddings[valid_idx])
                        valid_idx += 1
                    else:
                        result.append(None)
                
                return result
            except Exception as e:
                logger.error(f"Error generating batch OpenAI embeddings: {str(e)}")
                # Fall through to individual processing
        
        # Process one by one if batch processing fails or is not available
        return [self.generate_embedding(text) for text in texts]


# Create a singleton instance for ease of use
_embedding_generator = None

def get_embedding_generator() -> EmbeddingGenerator:
    """Get or create the embedding generator singleton."""
    global _embedding_generator
    if _embedding_generator is None:
        _embedding_generator = EmbeddingGenerator()
    return _embedding_generator

@functools.lru_cache(maxsize=100)
def generate_embedding_for_text(text: str) -> Optional[List[float]]:
    """
    Generate an embedding for text.
    
    Args:
        text: The text to generate an embedding for
        
    Returns:
        A list of floats representing the embedding
    """
    if not text or len(text.strip()) == 0:
        logger.warning("Empty text provided for embedding generation")
        return None
        
    # Check cache first
    cache_key = _cache_key(text)
    if cache_key in _embedding_cache:
        logger.debug(f"Cache hit for embedding: {text[:50]}...")
        return _embedding_cache[cache_key]
    
    # Generate embedding
    generator = get_embedding_generator()
    embedding = generator.generate_embedding(text)
    
    # Cache if valid
    if embedding and len(_embedding_cache) < _cache_size_limit:
        _embedding_cache[cache_key] = embedding
        logger.debug(f"Added embedding to cache. Cache size: {len(_embedding_cache)}")
    
    return embedding

def generate_batch_embeddings_for_texts(texts: List[str]) -> List[Optional[List[float]]]:
    """
    Generate embeddings for a batch of texts.
    
    Args:
        texts: The texts to generate embeddings for
        
    Returns:
        A list of embeddings, one for each input text
    """
    generator = get_embedding_generator()
    return generator.generate_batch_embeddings(texts)

def calculate_similarity(embedding1: List[float], embedding2: List[float]) -> float:
    """
    Calculate cosine similarity between two embeddings.
    
    Args:
        embedding1: First embedding vector
        embedding2: Second embedding vector
        
    Returns:
        Cosine similarity score (0-1)
    """
    try:
        # Convert to numpy arrays
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)
        
        # Calculate cosine similarity
        dot_product = np.dot(vec1, vec2)
        norm_a = np.linalg.norm(vec1)
        norm_b = np.linalg.norm(vec2)
        
        # Avoid division by zero
        if norm_a == 0 or norm_b == 0:
            return 0.0
            
        return dot_product / (norm_a * norm_b)
    except Exception as e:
        logger.error(f"Error calculating similarity: {str(e)}")
        return 0.0 