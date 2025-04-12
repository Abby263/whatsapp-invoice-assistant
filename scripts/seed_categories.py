#!/usr/bin/env python
"""
Script to seed the database with categorized invoice items.

This script adds sample invoices with categorized items to demonstrate
category-based reporting and queries.
"""
import logging
import sys
import os
import time
from datetime import datetime, timedelta

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

# Add parent directory to path so we can import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.connection import SessionLocal
from database import schemas
from utils.vector_utils import get_embedding_generator
from sqlalchemy.orm import Session

# Categories to demonstrate
CATEGORIES = [
    "Groceries", 
    "Electronics", 
    "Office Supplies",
    "Dining",
    "Entertainment",
    "Travel",
    "Utilities",
    "Healthcare"
]

def create_test_user(db: Session) -> schemas.User:
    """Create a test user if it doesn't already exist."""
    test_user = db.query(schemas.User).filter(schemas.User.id == 0).first()
    
    if test_user:
        logger.info(f"Test user already exists with ID: {test_user.id}")
        return test_user
    
    # Create a new test user
    test_user = schemas.User(
        id=0,  # Use ID 0 for testing
        whatsapp_number="+12025550000",
        name="Test User",
        email="test@example.com",
        is_active=True,
        created_at=datetime.utcnow()
    )
    
    db.add(test_user)
    db.commit()
    db.refresh(test_user)
    logger.info(f"Created test user with ID: {test_user.id}")
    
    return test_user

def create_categorized_invoices(db: Session, user_id: int) -> None:
    """Create sample invoices with categorized items."""
    logger.info("Creating invoices with categorized items")
    
    # Initialize embedding generator for item descriptions
    embedding_generator = get_embedding_generator()
    
    # Invoice 1: Grocery Store
    grocery_invoice = schemas.Invoice(
        user_id=user_id,
        invoice_number="GRO-2025-001",
        invoice_date=datetime.utcnow() - timedelta(days=5),
        vendor="Whole Foods Market",
        total_amount=126.75,
        currency="USD",
        notes="Weekly grocery shopping",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(grocery_invoice)
    db.flush()  # Get the ID without committing
    
    # Grocery items
    grocery_items = [
        ("Organic Bananas", 1.5, 0.49, "Groceries", "FRT-001"),
        ("Almond Milk", 1, 3.99, "Groceries", "DRY-002"),
        ("Free-Range Eggs", 1, 5.49, "Groceries", "DRY-003"),
        ("Whole Wheat Bread", 1, 4.29, "Groceries", "BKY-001"),
        ("Organic Chicken Breast", 1, 12.99, "Groceries", "MEA-001"),
        ("Cheddar Cheese", 1, 6.49, "Groceries", "DRY-004"),
        ("Fresh Strawberries", 1, 4.99, "Groceries", "PRD-001")
    ]
    
    # Create embeddings for all descriptions at once
    grocery_descriptions = [item[0] for item in grocery_items]
    grocery_embeddings = embedding_generator.generate_batch_embeddings(grocery_descriptions)
    
    # Add grocery items with embeddings
    for i, (description, quantity, unit_price, category, item_code) in enumerate(grocery_items):
        embedding = grocery_embeddings[i] if i < len(grocery_embeddings) else None
        total_price = quantity * unit_price
        
        item = schemas.Item(
            invoice_id=grocery_invoice.id,
            description=description,
            quantity=quantity,
            unit_price=unit_price,
            total_price=total_price,
            item_category=category,
            item_code=item_code,
            description_embedding=embedding,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(item)
    
    # Invoice 2: Electronics Store
    electronics_invoice = schemas.Invoice(
        user_id=user_id,
        invoice_number="ELEC-2025-001",
        invoice_date=datetime.utcnow() - timedelta(days=10),
        vendor="Best Buy",
        total_amount=529.97,
        currency="USD",
        notes="Home office equipment",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(electronics_invoice)
    db.flush()
    
    # Electronics items
    electronics_items = [
        ("Wireless Headphones", 1, 149.99, "Electronics", "AUD-001"),
        ("External SSD Drive", 1, 129.99, "Electronics", "STR-001"),
        ("USB-C Hub", 1, 49.99, "Electronics", "ACC-001"),
        ("Wireless Mouse", 1, 39.99, "Electronics", "ACC-002"),
        ("HDMI Cable", 2, 19.99, "Electronics", "CAB-001"),
        ("Laptop Stand", 1, 79.99, "Electronics", "ACC-003")
    ]
    
    # Create embeddings for all descriptions at once
    electronics_descriptions = [item[0] for item in electronics_items]
    electronics_embeddings = embedding_generator.generate_batch_embeddings(electronics_descriptions)
    
    # Add electronics items with embeddings
    for i, (description, quantity, unit_price, category, item_code) in enumerate(electronics_items):
        embedding = electronics_embeddings[i] if i < len(electronics_embeddings) else None
        total_price = quantity * unit_price
        
        item = schemas.Item(
            invoice_id=electronics_invoice.id,
            description=description,
            quantity=quantity,
            unit_price=unit_price,
            total_price=total_price,
            item_category=category,
            item_code=item_code,
            description_embedding=embedding,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(item)
    
    # Invoice 3: Office Supplies
    office_invoice = schemas.Invoice(
        user_id=user_id,
        invoice_number="OFF-2025-001",
        invoice_date=datetime.utcnow() - timedelta(days=15),
        vendor="Staples",
        total_amount=87.45,
        currency="USD",
        notes="Office supplies for home office",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(office_invoice)
    db.flush()
    
    # Office items
    office_items = [
        ("Premium Notebook", 2, 12.99, "Office Supplies", "PAP-001"),
        ("Gel Pens (Pack of 12)", 1, 16.99, "Office Supplies", "WRT-001"),
        ("Desk Organizer", 1, 24.99, "Office Supplies", "ORG-001"),
        ("Printer Paper", 1, 9.99, "Office Supplies", "PAP-002"),
        ("Sticky Notes", 3, 3.49, "Office Supplies", "PAP-003")
    ]
    
    # Create embeddings for all descriptions at once
    office_descriptions = [item[0] for item in office_items]
    office_embeddings = embedding_generator.generate_batch_embeddings(office_descriptions)
    
    # Add office items with embeddings
    for i, (description, quantity, unit_price, category, item_code) in enumerate(office_items):
        embedding = office_embeddings[i] if i < len(office_embeddings) else None
        total_price = quantity * unit_price
        
        item = schemas.Item(
            invoice_id=office_invoice.id,
            description=description,
            quantity=quantity,
            unit_price=unit_price,
            total_price=total_price,
            item_category=category,
            item_code=item_code,
            description_embedding=embedding,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(item)
    
    # Invoice 4: Restaurant
    restaurant_invoice = schemas.Invoice(
        user_id=user_id,
        invoice_number="DIN-2025-001",
        invoice_date=datetime.utcnow() - timedelta(days=3),
        vendor="Olive Garden",
        total_amount=86.45,
        currency="USD",
        notes="Family dinner",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(restaurant_invoice)
    db.flush()
    
    # Restaurant items
    restaurant_items = [
        ("Fettuccine Alfredo", 1, 16.99, "Dining", "PASTA-001"),
        ("Chicken Parmesan", 1, 18.99, "Dining", "ENTR-001"),
        ("Tiramisu", 2, 8.99, "Dining", "DSRT-001"),
        ("Sparkling Water", 2, 3.99, "Dining", "BEV-001"),
        ("House Salad", 1, 7.99, "Dining", "APP-001"),
        ("Breadsticks", 1, 5.49, "Dining", "APP-002")
    ]
    
    # Create embeddings for all descriptions at once
    restaurant_descriptions = [item[0] for item in restaurant_items]
    restaurant_embeddings = embedding_generator.generate_batch_embeddings(restaurant_descriptions)
    
    # Add restaurant items with embeddings
    for i, (description, quantity, unit_price, category, item_code) in enumerate(restaurant_items):
        embedding = restaurant_embeddings[i] if i < len(restaurant_embeddings) else None
        total_price = quantity * unit_price
        
        item = schemas.Item(
            invoice_id=restaurant_invoice.id,
            description=description,
            quantity=quantity,
            unit_price=unit_price,
            total_price=total_price,
            item_category=category,
            item_code=item_code,
            description_embedding=embedding,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(item)
    
    # Commit all changes
    db.commit()
    logger.info("Successfully created invoices with categorized items")

def seed_categorized_data():
    """Main function to seed the database with categorized data."""
    logger.info("Starting database seeding with categorized items")
    start_time = time.time()
    
    # Get database session
    db = SessionLocal()
    
    try:
        # Create test user
        test_user = create_test_user(db)
        
        # Create categorized invoices
        create_categorized_invoices(db, test_user.id)
        
        end_time = time.time()
        logger.info(f"Database seeding completed in {end_time - start_time:.2f} seconds")
        
    except Exception as e:
        logger.error(f"Error seeding database: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed_categorized_data() 