"""
Database status utility to check the current database state.

This module checks the current database state including:
- Number of tables and their names
- Latest migration applied
- Row counts for key tables
- Vector embedding statistics
- Database size information
"""
import subprocess
from database.connection import engine
import sqlalchemy as sa
from database.schemas import Base, has_pgvector

def check_database_status():
    """
    Check and print the current database status.
    """
    # Get table information
    inspector = sa.inspect(engine)
    tables = inspector.get_table_names()
    
    # Print table information
    print("\n=== Database Tables ===")
    print(f"Total tables: {len(tables)}")
    print("Tables:")
    for table in sorted(tables):
        print(f"  - {table}")
    
    # Check row counts for key tables
    print("\n=== Table Row Counts ===")
    with engine.connect() as conn:
        for table in sorted(tables):
            try:
                result = conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                print(f"  - {table}: {count} rows")
            except Exception as e:
                print(f"  - {table}: Error counting rows - {str(e)}")
    
    # Check database size information
    print("\n=== Database Size Information ===")
    try:
        with engine.connect() as conn:
            # Get database name
            db_url = engine.url
            db_name = db_url.database if db_url.database else "Unknown"
            
            # Get total database size
            db_size_query = sa.text("""
            SELECT pg_size_pretty(pg_database_size(current_database())) as db_size,
                   pg_size_pretty(sum(pg_total_relation_size(relid))) as tables_size
            FROM pg_catalog.pg_statio_user_tables
            """)
            result = conn.execute(db_size_query)
            size_info = result.first()
            
            if size_info:
                print(f"  Database: {db_name}")
                print(f"  Total database size: {size_info[0] if size_info[0] else 'Unknown'}")
                print(f"  Tables size: {size_info[1] if size_info[1] else 'Unknown'}")
            
            # Get table sizes
            table_size_query = sa.text("""
            SELECT relname as table_name, 
                   pg_size_pretty(pg_total_relation_size(relid)) as total_size
            FROM pg_catalog.pg_statio_user_tables
            ORDER BY pg_total_relation_size(relid) DESC
            LIMIT 5
            """)
            
            result = conn.execute(table_size_query)
            print("\n  Top 5 tables by size:")
            for row in result:
                print(f"  - {row[0]}: {row[1]}")
    
    except Exception as e:
        print(f"  Error retrieving database size information: {str(e)}")
    
    # Check vector embedding statistics
    print("\n=== Vector Embeddings Status ===")
    try:
        # Check if pgvector extension is installed
        with engine.connect() as conn:
            result = conn.execute(sa.text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')"))
            pgvector_installed = result.scalar()
            
            if pgvector_installed:
                print("  pgvector extension is installed")
                
                # Count items with and without embeddings
                if 'items' in tables:
                    result = conn.execute(sa.text("SELECT COUNT(*) FROM items WHERE description_embedding IS NOT NULL"))
                    with_embeddings = result.scalar() or 0
                    
                    result = conn.execute(sa.text("SELECT COUNT(*) FROM items WHERE description_embedding IS NULL"))
                    without_embeddings = result.scalar() or 0
                    
                    total_items = with_embeddings + without_embeddings
                    if total_items > 0:
                        coverage_pct = (with_embeddings / total_items) * 100
                    else:
                        coverage_pct = 0
                        
                    print(f"  Items with embeddings: {with_embeddings}/{total_items} ({coverage_pct:.1f}%)")
                    print(f"  Items missing embeddings: {without_embeddings}")
                    
                    if with_embeddings > 0:
                        # Get embedding size using pgvector's length function
                        try:
                            # First try to get a sample embedding to examine
                            result = conn.execute(sa.text("SELECT description_embedding FROM items WHERE description_embedding IS NOT NULL LIMIT 1"))
                            sample = result.scalar()
                            
                            if sample:
                                # Use the vector_dims() function if available
                                try:
                                    result = conn.execute(sa.text("SELECT vector_dims(description_embedding) FROM items WHERE description_embedding IS NOT NULL LIMIT 1"))
                                    dimension = result.scalar()
                                    print(f"  Embedding dimension: {dimension}")
                                except Exception:
                                    # Fallback: Check if vectors has dim property
                                    try:
                                        result = conn.execute(sa.text("SELECT length(description_embedding) FROM items WHERE description_embedding IS NOT NULL LIMIT 1"))
                                        dimension = result.scalar()
                                        print(f"  Embedding dimension: {dimension}")
                                    except Exception:
                                        print("  Could not determine embedding dimension - no compatible function found")
                            else:
                                print("  Could not determine embedding dimension - no embeddings found")
                        except Exception as e:
                            print(f"  Cannot calculate embedding dimensions: {str(e)}")
            else:
                print("  pgvector extension is NOT installed")
                if has_pgvector:
                    print("  pgvector package is installed in Python environment")
                else:
                    print("  pgvector package is NOT installed in Python environment")
                
    except Exception as e:
        print(f"  Error checking vector embeddings: {str(e)}")
    
    # Check latest migration
    print("\n=== Migration Status ===")
    try:
        result = subprocess.run(
            ["alembic", "current"], 
            capture_output=True, 
            text=True,
            check=False
        )
        if result.returncode == 0:
            print(result.stdout.strip())
        else:
            print("  Error getting migration status:")
            print(f"  {result.stderr.strip()}")
    except Exception as e:
        print(f"  Error running alembic command: {str(e)}")

if __name__ == "__main__":
    check_database_status() 