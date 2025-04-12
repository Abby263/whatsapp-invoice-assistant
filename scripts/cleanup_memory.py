#!/usr/bin/env python
"""
Memory cleanup script for the WhatsApp Invoice Assistant.

This script periodically cleans up old conversation entries from memory
to prevent memory leaks and ensure optimal performance.
"""
import os
import sys
import logging
import time
import argparse
from datetime import datetime, timedelta

# Add project directory to path for proper imports
script_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(script_dir)
sys.path.insert(0, project_dir)

# Import logging utilities
from utils.logging import get_logs_directory

# Configure logging
logs_dir = get_logs_directory()
log_file = os.path.join(logs_dir, 'memory_cleanup.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file, mode='a')
    ]
)

logger = logging.getLogger("memory_cleanup")

def clean_memory(max_age_hours=24, dry_run=False):
    """
    Clean up memory entries older than the specified age.
    
    Args:
        max_age_hours: Maximum age in hours for memory entries before cleanup
        dry_run: If True, only report what would be deleted without actually deleting
        
    Returns:
        Tuple of (count_cleaned, count_kept)
    """
    # Import memory manager and database context manager
    from memory.langgraph_memory import memory_manager
    
    # Calculate cleanup threshold time
    max_age_seconds = max_age_hours * 60 * 60
    cutoff_time = time.time() - max_age_seconds
    
    # Track statistics
    count_cleaned = 0
    count_kept = 0
    
    # Process each memory entry
    entries_to_clean = []
    for conversation_id, entry in memory_manager._memory.items():
        # Check age
        if entry.last_accessed < cutoff_time:
            entries_to_clean.append(conversation_id)
            
            if not dry_run:
                logger.info(f"Conversation {conversation_id} marked for cleanup - last accessed: {datetime.fromtimestamp(entry.last_accessed)}")
            else:
                logger.info(f"[DRY RUN] Would clean conversation {conversation_id} - last accessed: {datetime.fromtimestamp(entry.last_accessed)}")
        else:
            count_kept += 1
            
    # Clean marked entries
    if not dry_run:
        for conversation_id in entries_to_clean:
            memory_manager.clear(conversation_id)
            count_cleaned += 1
    else:
        count_cleaned = len(entries_to_clean)
        
    # Log summary
    logger.info(f"Memory cleanup complete: {count_cleaned} conversations cleaned, {count_kept} kept")
    logger.info(f"Current memory usage: {len(memory_manager._memory)} active conversations")
    
    return count_cleaned, count_kept


def sync_db_memory(dry_run=False):
    """
    Sync memory entries to the database before cleanup.
    
    Args:
        dry_run: If True, only report what would be synced without actually syncing
        
    Returns:
        Count of conversations synced to the database
    """
    # Import memory manager and database context manager
    from memory.langgraph_memory import memory_manager
    from memory.context_manager import context_manager
    from database.connection import SessionLocal
    import asyncio
    
    # Track statistics
    count_synced = 0
    
    try:
        # Get database session
        db = SessionLocal()
        
        # Process each memory entry
        for conversation_id, entry in memory_manager._memory.items():
            try:
                if not dry_run:
                    # Run sync in asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(context_manager.sync_memory_to_db(db, conversation_id, entry.user_id))
                    loop.close()
                    
                    logger.info(f"Synced conversation {conversation_id} to database")
                else:
                    logger.info(f"[DRY RUN] Would sync conversation {conversation_id} to database")
                
                count_synced += 1
            except Exception as e:
                logger.error(f"Error syncing conversation {conversation_id} to database: {str(e)}")
        
        # Log summary
        logger.info(f"Memory sync complete: {count_synced} conversations synced to database")
        
    except Exception as e:
        logger.error(f"Error initializing database session for memory sync: {str(e)}")
    finally:
        db.close()
    
    return count_synced


def main():
    parser = argparse.ArgumentParser(description="Clean up old conversation memory entries")
    parser.add_argument("--max-age", type=int, default=24, help="Maximum age in hours for memory entries before cleanup")
    parser.add_argument("--dry-run", action="store_true", help="Only report what would be deleted without actually deleting")
    parser.add_argument("--sync-db", action="store_true", help="Sync memory to database before cleanup")
    args = parser.parse_args()
    
    logger.info(f"Starting memory cleanup with max age: {args.max_age} hours")
    
    # First sync to database if requested
    if args.sync_db:
        logger.info("Syncing memory to database before cleanup")
        sync_db_memory(args.dry_run)
    
    # Clean memory
    clean_memory(args.max_age, args.dry_run)
    
    logger.info("Memory cleanup complete")


if __name__ == "__main__":
    main() 