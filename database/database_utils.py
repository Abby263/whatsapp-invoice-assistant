"""
Database utility functions.

This module provides utility functions for common database operations.
"""

import logging
from typing import Dict, Any, List, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

from database.connection import get_db_session

logger = logging.getLogger(__name__)

def get_database_stats() -> Dict[str, Any]:
    """
    Get database statistics such as table sizes, record counts, etc.
    
    Returns:
        Dict with database statistics
    """
    session = get_db_session()
    
    try:
        # Get total invoices count
        total_invoices_query = text("SELECT COUNT(*) FROM invoices")
        total_invoices = session.execute(total_invoices_query).scalar() or 0
        
        # Get total items count
        total_items_query = text("SELECT COUNT(*) FROM items")
        total_items = session.execute(total_items_query).scalar() or 0
        
        # Get database size (MB)
        db_size_query = text("""
            SELECT pg_size_pretty(pg_database_size(current_database())) as db_size,
                   pg_database_size(current_database()) as db_size_bytes
        """)
        db_size_result = session.execute(db_size_query).fetchone()
        db_size = db_size_result[0] if db_size_result else "Unknown"
        db_size_bytes = db_size_result[1] if db_size_result else 0
        
        # Get table sizes
        table_sizes_query = text("""
            SELECT
                table_name,
                pg_size_pretty(total_bytes) as total_size,
                total_bytes
            FROM (
                SELECT
                    table_name,
                    pg_total_relation_size(quote_ident(table_name)) as total_bytes
                FROM
                    information_schema.tables
                WHERE
                    table_schema = 'public'
                    AND table_type = 'BASE TABLE'
            ) as tables
            ORDER BY total_bytes DESC
        """)
        table_sizes_result = session.execute(table_sizes_query).fetchall()
        
        tables_size = sum(row[2] for row in table_sizes_result) if table_sizes_result else 0
        tables_size_pretty = f"{tables_size / (1024 * 1024):.2f} MB" if tables_size > 0 else "0 MB"
        
        # Get vector extension status
        vector_status_query = text("""
            SELECT * FROM pg_extension WHERE extname = 'vector'
        """)
        vector_extension_installed = session.execute(vector_status_query).fetchone() is not None
        
        # Get count of items with embeddings
        items_with_embeddings_query = text("""
            SELECT COUNT(*) FROM items WHERE description_embedding IS NOT NULL
        """)
        items_with_embeddings = session.execute(items_with_embeddings_query).scalar() or 0
        
        return {
            "total_invoices": total_invoices,
            "total_items": total_items,
            "db_size": db_size,
            "db_size_bytes": db_size_bytes,
            "tables_size": tables_size_pretty,
            "tables_size_bytes": tables_size,
            "vector_extension_installed": vector_extension_installed,
            "items_with_embeddings": items_with_embeddings,
            "total_items_for_embedding": total_items,
            "embedding_coverage": f"{items_with_embeddings}/{total_items}"
        }
    
    except Exception as e:
        logger.error(f"Error getting database stats: {str(e)}")
        return {
            "error": str(e),
            "total_invoices": 0,
            "total_items": 0,
            "db_size": "Error",
            "tables_size": "Error",
            "vector_extension_installed": False,
            "items_with_embeddings": 0,
            "total_items_for_embedding": 0,
            "embedding_coverage": "0/0"
        }
    
    finally:
        session.close()

def get_user_stats(user_id: int) -> Dict[str, Any]:
    """
    Get statistics for a specific user.
    
    Args:
        user_id: User ID to get statistics for
        
    Returns:
        Dict with user statistics
    """
    session = get_db_session()
    
    try:
        # Get user invoices count
        user_invoices_query = text("SELECT COUNT(*) FROM invoices WHERE user_id = :user_id")
        user_invoices = session.execute(user_invoices_query, {"user_id": user_id}).scalar() or 0
        
        # Get user items count
        user_items_query = text("""
            SELECT COUNT(*) FROM items i 
            JOIN invoices inv ON i.invoice_id = inv.id 
            WHERE inv.user_id = :user_id
        """)
        user_items = session.execute(user_items_query, {"user_id": user_id}).scalar() or 0
        
        return {
            "user_invoices": user_invoices,
            "user_items": user_items
        }
    
    except Exception as e:
        logger.error(f"Error getting user stats for user_id {user_id}: {str(e)}")
        return {
            "error": str(e),
            "user_invoices": 0,
            "user_items": 0
        }
    
    finally:
        session.close() 