"""
Database utilities for managing vector embeddings.

This module provides utilities for updating and managing vector embeddings
in the database, enabling semantic search capabilities for item descriptions.
"""
import logging
from typing import List, Dict, Any, Optional, Union
from sqlalchemy import text
from sqlalchemy.orm import Session

from database.schemas import Item
from database.connection import get_db_session
from utils.vector_utils import get_embedding_generator, generate_embedding_for_text

logger = logging.getLogger(__name__)

async def update_item_embeddings(session: Optional[Session] = None) -> Dict[str, Any]:
    """
    Update embeddings for all items in the database that don't have embeddings.
    
    Args:
        session: Optional database session
        
    Returns:
        Dictionary with results of the update operation
    """
    close_session = False
    if session is None:
        session = get_db_session()
        close_session = True
    
    try:
        # Get items without embeddings
        items_without_embeddings = session.query(Item).filter(
            Item.description_embedding.is_(None),
            Item.description.isnot(None)
        ).all()
        
        if not items_without_embeddings:
            logger.info("No items without embeddings found")
            return {"status": "success", "updated_count": 0, "message": "No items needed embedding updates"}
        
        logger.info(f"Found {len(items_without_embeddings)} items without embeddings")
        
        # Get all descriptions
        descriptions = [item.description for item in items_without_embeddings]
        
        # Generate embeddings in batch
        embedding_generator = get_embedding_generator()
        embeddings = embedding_generator.generate_batch_embeddings(descriptions)
        
        # Update items with embeddings
        updated_count = 0
        for i, item in enumerate(items_without_embeddings):
            item.description_embedding = embeddings[i]
            updated_count += 1
        
        # Commit changes
        session.commit()
        
        logger.info(f"Updated embeddings for {updated_count} items")
        return {
            "status": "success",
            "updated_count": updated_count,
            "message": f"Successfully updated embeddings for {updated_count} items"
        }
    
    except Exception as e:
        logger.error(f"Error updating item embeddings: {str(e)}")
        session.rollback()
        return {
            "status": "error",
            "error": str(e),
            "message": f"Failed to update embeddings: {str(e)}"
        }
    
    finally:
        if close_session:
            session.close()


async def find_similar_items(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Find items similar to the query text using vector similarity search.
    
    Args:
        query: The search query text
        limit: Maximum number of results to return
        
    Returns:
        List of items with similarity scores
    """
    session = get_db_session()
    
    try:
        # Generate embedding for the query
        query_embedding = generate_embedding_for_text(query)
        
        # Convert embedding to PostgreSQL vector format
        embedding_str = ','.join(map(str, query_embedding))
        
        # Perform similarity search using PostgreSQL
        sql = text(f"""
        SELECT 
            i.id,
            i.description,
            i.unit_price,
            inv.vendor,
            inv.invoice_date,
            1 - (i.description_embedding <=> '[{embedding_str}]') as similarity
        FROM 
            items i
        JOIN
            invoices inv ON i.invoice_id = inv.id
        WHERE 
            i.description_embedding IS NOT NULL
        ORDER BY 
            i.description_embedding <=> '[{embedding_str}]'
        LIMIT :limit
        """)
        
        results = session.execute(sql, {"limit": limit})
        
        # Format results
        similar_items = []
        for row in results:
            similar_items.append({
                "id": row.id,
                "description": row.description,
                "unit_price": float(row.unit_price) if row.unit_price else None,
                "vendor": row.vendor,
                "invoice_date": row.invoice_date.isoformat() if row.invoice_date else None,
                "similarity": float(row.similarity)
            })
        
        return similar_items
    
    except Exception as e:
        logger.error(f"Error finding similar items: {str(e)}")
        return []
    
    finally:
        session.close()


def get_item_categories_with_embeddings(user_id: int) -> List[Dict[str, Any]]:
    """
    Get a list of item categories with their embeddings.
    
    Args:
        user_id: User ID to filter by
        
    Returns:
        List of categories with embeddings
    """
    session = get_db_session()
    
    try:
        # Get unique item categories and generate representative embeddings
        sql = text("""
        SELECT DISTINCT
            it.item_category,
            it.description_embedding
        FROM 
            items it
        JOIN
            invoices inv ON it.invoice_id = inv.id
        WHERE 
            inv.user_id = :user_id
            AND it.item_category IS NOT NULL
            AND it.description_embedding IS NOT NULL
        """)
        
        results = session.execute(sql, {"user_id": user_id})
        
        # Format results
        categories = []
        for row in results:
            categories.append({
                "category": row.item_category,
                "embedding": row.description_embedding
            })
        
        return categories
    
    except Exception as e:
        logger.error(f"Error getting item categories: {str(e)}")
        return []
    
    finally:
        session.close()


async def check_embedding_status() -> Dict[str, Any]:
    """
    Check the status of embeddings in the database and log detailed information.
    
    Returns:
        Dictionary with embedding status information
    """
    session = get_db_session()
    
    try:
        # Check total items count
        total_items_query = text("SELECT COUNT(*) FROM items")
        total_items = session.execute(total_items_query).scalar() or 0
        
        # Check items with embeddings count
        items_with_embeddings_query = text("SELECT COUNT(*) FROM items WHERE description_embedding IS NOT NULL")
        items_with_embeddings = session.execute(items_with_embeddings_query).scalar() or 0
        
        # Check if vector extension is installed
        vector_extension_query = text("SELECT * FROM pg_extension WHERE extname = 'vector'")
        vector_extension_installed = session.execute(vector_extension_query).fetchone() is not None
        
        # Get sample embeddings dimension
        embedding_dimension_query = text("SELECT array_length(description_embedding, 1) FROM items WHERE description_embedding IS NOT NULL LIMIT 1")
        dimension_result = session.execute(embedding_dimension_query).scalar()
        embedding_dimension = dimension_result if dimension_result else "Unknown"
        
        # Get sample items containing "coffee" or related terms
        coffee_items_query = text("""
            SELECT description, array_length(description_embedding, 1) as dim
            FROM items 
            WHERE description ILIKE '%coffee%' OR description ILIKE '%latte%' OR description ILIKE '%espresso%'
            LIMIT 10
        """)
        coffee_items = session.execute(coffee_items_query).fetchall()
        coffee_items_list = [{"description": row.description, "embedding_dimension": row.dim} for row in coffee_items]
        
        # Log the results
        logger.info("=== EMBEDDING STATUS ===")
        logger.info(f"Total items in database: {total_items}")
        logger.info(f"Items with embeddings: {items_with_embeddings} ({round(items_with_embeddings/total_items*100 if total_items else 0, 2)}%)")
        logger.info(f"Vector extension installed: {vector_extension_installed}")
        logger.info(f"Embedding dimension: {embedding_dimension}")
        
        if coffee_items_list:
            logger.info(f"Found {len(coffee_items_list)} items containing coffee/latte/espresso:")
            for i, item in enumerate(coffee_items_list):
                logger.info(f"  Item {i+1}: '{item['description']}' - Embedding dimension: {item['embedding_dimension']}")
        else:
            logger.info("No coffee/latte/espresso items found in database")
        
        return {
            "total_items": total_items,
            "items_with_embeddings": items_with_embeddings,
            "vector_extension_installed": vector_extension_installed,
            "embedding_dimension": embedding_dimension,
            "coffee_items": coffee_items_list
        }
    
    except Exception as e:
        logger.error(f"Error checking embedding status: {str(e)}")
        return {
            "error": str(e),
            "total_items": 0,
            "items_with_embeddings": 0,
            "vector_extension_installed": False,
            "embedding_dimension": "Unknown",
            "coffee_items": []
        }
    
    finally:
        session.close() 