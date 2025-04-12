"""
Constants for database schema information used across the application.

This module defines the database schema description that can be referenced by
various components that need information about the database structure.
"""

# Full database schema description for SQL generation and other uses
DB_SCHEMA_INFO = """
Database Schema:

users:
- id (INTEGER): Primary key
- whatsapp_number (TEXT): User's WhatsApp phone number
- name (TEXT): User's full name
- email (TEXT): User's email address
- is_active (BOOLEAN): Whether the user is active
- created_at (TIMESTAMP): When the user was created

invoices:
- id (INTEGER): Primary key
- user_id (INTEGER): Foreign key to users.id - IMPORTANT: Always filter by this field
- invoice_number (TEXT): The invoice number
- invoice_date (TIMESTAMP): The date the invoice was issued
- vendor (TEXT): The company/person who issued the invoice
- total_amount (FLOAT): The total amount of the invoice
- tax_amount (FLOAT): Tax portion of the invoice (nullable)
- currency (TEXT): The currency code (USD, EUR, etc.)
- file_url (TEXT): URL to the stored invoice file
- file_content_type (TEXT): MIME type of the file
- notes (TEXT): Additional notes about the invoice
- created_at (TIMESTAMP): When the invoice was created
- updated_at (TIMESTAMP): When the invoice was last updated

items:
- id (INTEGER): Primary key
- invoice_id (INTEGER): Foreign key to invoices.id
- description (TEXT): Description of the item
- quantity (FLOAT): The quantity purchased
- unit_price (FLOAT): The price per unit
- total_price (FLOAT): The total price for this item (quantity * unit_price)
- item_category (TEXT): Category of the item (nullable)
- item_code (TEXT): Code or SKU for the item (nullable)
- description_embedding (VECTOR): Vector embedding of the item description
- created_at (TIMESTAMP): When the item was created
- updated_at (TIMESTAMP): When the item was last updated

conversations:
- id (INTEGER): Primary key
- user_id (INTEGER): Foreign key to users.id - IMPORTANT: Always filter by this field
- created_at (TIMESTAMP): When the conversation was created
- is_active (BOOLEAN): Whether the conversation is active

messages:
- id (INTEGER): Primary key
- user_id (INTEGER): Foreign key to users.id - IMPORTANT: Always filter by this field
- conversation_id (INTEGER): Foreign key to conversations.id
- content (TEXT): The message content
- role (ENUM): The role of the message (user, assistant, system)
- created_at (TIMESTAMP): When the message was created

media:
- id (INTEGER): Primary key
- user_id (INTEGER): Foreign key to users.id - IMPORTANT: Always filter by this field
- invoice_id (INTEGER): Foreign key to invoices.id
- filename (TEXT): The name of the file
- file_path (TEXT): Path to the file
- mime_type (TEXT): MIME type of the file
- file_size (INTEGER): Size of the file in bytes
- created_at (TIMESTAMP): When the file was uploaded

IMPORTANT SECURITY REQUIREMENTS:
1. Every query MUST include a filter on the user_id field to ensure data isolation.
2. For direct table queries, add "WHERE user_id = :user_id" to filter for the current user.
3. For JOINs, ensure the primary table is filtered by user_id (e.g., "WHERE invoices.user_id = :user_id").
4. Never return data for all users - always filter by the specific user making the request.
5. Use :user_id as a parameter in all queries to enable proper binding during execution.
6. IMPORTANT: The user_id is stored as an INTEGER, not a UUID. Don't use UUID functions or casting.
7. ALWAYS assume user_id is an integer field in all tables.
8. NEVER use the 'status' column in the invoices table - it doesn't exist in the actual database.
"""

# Simplified database schema that includes only table names and column names
DB_SCHEMA_SIMPLE = """
users(id, whatsapp_number, name, email, is_active, created_at)
invoices(id, user_id, invoice_number, invoice_date, vendor, total_amount, tax_amount, currency, file_url, file_content_type, notes, created_at, updated_at)
items(id, invoice_id, description, quantity, unit_price, total_price, item_category, item_code, description_embedding, created_at, updated_at)
conversations(id, user_id, created_at, is_active)
messages(id, user_id, conversation_id, content, role, created_at)
media(id, user_id, invoice_id, filename, file_path, mime_type, file_size, created_at)
""" 