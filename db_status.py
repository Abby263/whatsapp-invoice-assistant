"""
Database status utility to check the current database state.

This script checks the current database state including:
- Number of tables and their names
- Latest migration applied
- Row counts for key tables
"""
import subprocess
from database.connection import engine
import sqlalchemy as sa
from database.schemas import Base

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