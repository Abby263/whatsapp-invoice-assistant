#!/usr/bin/env python
"""
Script to update vector embeddings for item descriptions in the database.

This script generates embeddings for all items in the database that don't have
embeddings yet. It's useful for initializing the system when semantic search
is first enabled or for updating embeddings after bulk imports.

Usage:
    python update_embeddings.py         # Update only items without embeddings
    python update_embeddings.py --force # Update all items regardless of existing embeddings
"""
import asyncio
import logging
import time
import sys
import os
import argparse

# Add parent directory to path so we can import project modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Parse command line arguments
parser = argparse.ArgumentParser(description='Update vector embeddings for items')
parser.add_argument('--force', action='store_true', help='Force update all embeddings even if they exist')
args = parser.parse_args()

# Print directly to ensure visibility
print("Script started! Importing modules...")
print(f"Force update mode: {args.force}")

from database.connection import db_session
from utils.vector_utils import get_embedding_generator
from database.schemas import Item, InvoiceEmbedding, Invoice
from sqlalchemy import text

print("Modules imported successfully")

async def update_item_embeddings(session, force_update=False):
    """Update embeddings for all items in the database that don't have embeddings."""
    try:
        # Count total items
        total_items = session.query(Item).count()
        print(f"Total items in database: {total_items}")
        
        # Get items that need embeddings
        if force_update:
            # Get all items with descriptions
            items_to_update = session.query(Item).filter(
                Item.description.isnot(None)
            ).all()
            print(f"Force update mode: updating all {len(items_to_update)} items with descriptions")
        else:
            # Only get items without embeddings
            items_to_update = session.query(Item).filter(
                Item.description_embedding.is_(None),
                Item.description.isnot(None)
            ).all()
            print(f"Normal mode: updating {len(items_to_update)} items without embeddings")
        
        if not items_to_update:
            print("No items found to update")
            return {"status": "success", "updated_count": 0, "message": "No items needed embedding updates"}
        
        # Get all descriptions
        descriptions = [item.description for item in items_to_update]
        
        # Log some sample descriptions
        if descriptions:
            print(f"Sample descriptions: {descriptions[:2]}")
        
        # Generate embeddings in batch
        print("Initializing embedding generator...")
        embedding_generator = get_embedding_generator()
        print("Generating embeddings in batch...")
        embeddings = embedding_generator.generate_batch_embeddings(descriptions)
        
        if not embeddings:
            print("Failed to generate embeddings")
            return {"status": "error", "error": "Failed to generate embeddings", "updated_count": 0}
        
        print(f"Generated {len(embeddings)} embeddings")
        
        # Update items with embeddings
        updated_count = 0
        for i, item in enumerate(items_to_update):
            if i < len(embeddings):
                item.description_embedding = embeddings[i]
                updated_count += 1
                if i < 2:  # Log a few examples
                    print(f"Updated item {item.id}: '{item.description}' with embedding (len: {len(embeddings[i])})")
        
        print(f"Updated embeddings for {updated_count} items")
        return {
            "status": "success",
            "updated_count": updated_count,
            "message": f"Successfully updated embeddings for {updated_count} items"
        }
    
    except Exception as e:
        print(f"Error updating item embeddings: {str(e)}")
        import traceback
        traceback.print_exc()
        raise


async def update_invoice_embeddings(session, force_update=False):
    """
    Update embeddings for all invoices in the database that don't have embeddings.
    
    Args:
        session: SQLAlchemy session
        force_update: If True, update all embeddings even if they exist
        
    Returns:
        Dict with status and counts
    """
    try:
        # Count total invoices
        total_invoices = session.query(Invoice).count()
        print(f"Total invoices in database: {total_invoices}")
        
        # Get invoices that need embeddings
        if force_update:
            # Delete existing embeddings first if force updating
            session.execute(text("DELETE FROM invoice_embeddings"))
            session.commit()
            print("Deleted all existing invoice embeddings for force update")
            
            # Get all invoices
            invoices_to_update = session.query(Invoice).all()
            print(f"Force update mode: updating all {len(invoices_to_update)} invoices")
        else:
            # Find invoices without embeddings
            invoice_ids_with_embeddings = [
                row[0] for row in 
                session.query(InvoiceEmbedding.invoice_id).distinct()
            ]
            
            invoices_to_update = session.query(Invoice).filter(
                ~Invoice.id.in_(invoice_ids_with_embeddings) if invoice_ids_with_embeddings else True
            ).all()
            
            print(f"Normal mode: updating {len(invoices_to_update)} invoices without embeddings")
        
        if not invoices_to_update:
            print("No invoices found to update")
            return {"status": "success", "updated_count": 0, "message": "No invoices needed embedding updates"}
        
        # Generate embeddings for each invoice
        embedding_generator = get_embedding_generator()
        updated_count = 0
        
        for invoice in invoices_to_update:
            # Create text representation of the invoice for embedding
            # Include key fields and concatenate with item descriptions
            invoice_text = f"Invoice {invoice.invoice_number or ''} "
            invoice_text += f"from {invoice.vendor or 'Unknown'} "
            invoice_text += f"dated {invoice.invoice_date.strftime('%Y-%m-%d') if invoice.invoice_date else 'Unknown'} "
            invoice_text += f"for {invoice.total_amount or 0} {invoice.currency or ''}"
            
            # Add item descriptions if available
            if invoice.items:
                invoice_text += ". Items: "
                item_descriptions = [item.description for item in invoice.items if item.description]
                invoice_text += ", ".join(item_descriptions)
            
            # Generate embedding
            embedding = embedding_generator.generate_embedding(invoice_text)
            
            if embedding:
                # Create or update invoice embedding
                new_embedding = InvoiceEmbedding(
                    invoice_id=invoice.id,
                    user_id=invoice.user_id,
                    content_text=invoice_text,
                    embedding=embedding,
                    model_name=EMBEDDING_MODEL,
                    embedding_type="invoice_full"
                )
                session.add(new_embedding)
                updated_count += 1
                
                if updated_count <= 2:  # Log a few examples
                    print(f"Created embedding for invoice {invoice.id}: '{invoice_text[:100]}...'")
            
            # Commit every 10 invoices to avoid large transactions
            if updated_count % 10 == 0:
                session.commit()
                print(f"Processed {updated_count} invoices so far")
        
        # Final commit
        session.commit()
        print(f"Updated embeddings for {updated_count} invoices")
        
        return {
            "status": "success", 
            "updated_count": updated_count,
            "message": f"Successfully updated embeddings for {updated_count} invoices"
        }
        
    except Exception as e:
        print(f"Error updating invoice embeddings: {str(e)}")
        import traceback
        traceback.print_exc()
        session.rollback()
        return {
            "status": "error",
            "error": str(e),
            "message": f"Failed to update invoice embeddings: {str(e)}"
        }


async def main():
    """Main function to update item embeddings."""
    print("Starting embedding update process")
    
    start_time = time.time()
    
    try:
        # Use the db_session context manager from database.connection
        print("Creating database session...")
        with db_session() as session:
            print("Database session created successfully")
            
            # Update embeddings for all items that don't have them
            item_result = await update_item_embeddings(session, force_update=args.force)
            
            # Log results
            if item_result["status"] == "success":
                print(f"Successfully updated {item_result['updated_count']} item embeddings")
            else:
                print(f"Error updating item embeddings: {item_result.get('error', 'Unknown error')}")
                
            # Update invoice embeddings
            invoice_result = await update_invoice_embeddings(session, force_update=args.force)
            
            # Log results
            if invoice_result["status"] == "success":
                print(f"Successfully updated {invoice_result['updated_count']} invoice embeddings")
            else:
                print(f"Error updating invoice embeddings: {invoice_result.get('error', 'Unknown error')}")
        
        end_time = time.time()
        print(f"Embedding update process completed in {end_time - start_time:.2f} seconds")
        
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()


# Function that can be called from the UI
async def run_embeddings_update(force_update=False):
    """
    Run embedding updates for both items and invoices.
    
    This function can be called from the UI or other parts of the application.
    
    Args:
        force_update: If True, update all embeddings even if they exist
        
    Returns:
        Dict with status and results
    """
    start_time = time.time()
    
    try:
        from database.connection import db_session
        from utils.vector_utils import get_embedding_generator, EMBEDDING_MODEL
        
        with db_session() as session:
            # Update item embeddings
            item_result = await update_item_embeddings(session, force_update=force_update)
            
            # Update invoice embeddings
            invoice_result = await update_invoice_embeddings(session, force_update=force_update)
        
        end_time = time.time()
        
        return {
            "status": "success",
            "time_taken": f"{end_time - start_time:.2f} seconds",
            "item_embeddings": item_result,
            "invoice_embeddings": invoice_result
        }
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "error": str(e),
            "message": f"Error updating embeddings: {str(e)}"
        }


if __name__ == "__main__":
    print("Running main function...")
    asyncio.run(main())
    print("Script finished!") 