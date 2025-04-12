"""
Test data fixtures for WhatsApp Invoice Assistant tests.
"""

import os
from pathlib import Path
from typing import Dict, List, Any

# Base directories
DATA_DIR = Path("data")
VALID_INVOICES_DIR = DATA_DIR / "valid_invoices"
INVALID_INVOICES_DIR = DATA_DIR / "invalid_invoice"

# Paths to invoice files
VALID_INVOICE_PATH = VALID_INVOICES_DIR / "image.png"
INVALID_INVOICE_PATH = INVALID_INVOICES_DIR / "image.png"

# Sample text inputs by intent type
GREETING_INPUTS = [
    "Hi",
    "Hello there",
    "Hey",
    "Good morning",
    "Hi, how are you?",
]

GENERAL_INPUTS = [
    "What's the weather like today?",
    "Tell me a joke",
    "Who's the president?",
    "How far is the moon?",
    "What's your favorite color?",
]

INVOICE_QUERY_INPUTS = [
    "What did I spend at Amazon last month?",
    "Show me all invoices from March",
    "How much have I spent on office supplies?",
    "Find all invoices over $100",
    "What's my total spending for Q1?",
]

INVOICE_CREATION_INPUTS = [
    "Create an invoice for $100 from Amazon on March 5",
    "Generate an invoice for $50 from Walmart today",
    "Make an invoice for $200 from Office Depot on April 10",
    "I need a new invoice for $75 from Target",
    "Create a receipt for my coffee purchase of $4.50",
]

# Sample conversation history
SAMPLE_CONVERSATION_HISTORY = [
    {
        "role": "user",
        "content": "Hi there",
        "timestamp": "2023-04-01T10:00:00Z"
    },
    {
        "role": "assistant",
        "content": "👋 Welcome to InvoiceAgent! I'm your AI-powered financial assistant for business expenses.",
        "timestamp": "2023-04-01T10:00:10Z"
    },
    {
        "role": "user",
        "content": "What did I spend at Amazon last month?",
        "timestamp": "2023-04-01T10:01:00Z"
    },
    {
        "role": "assistant",
        "content": "I don't have any records of Amazon purchases from last month in the database yet.",
        "timestamp": "2023-04-01T10:01:10Z"
    }
]

# Sample extracted invoice data
SAMPLE_INVOICE_DATA = {
    "vendor": "Amazon",
    "date": "2023-03-15",
    "total_amount": 125.99,
    "currency": "USD",
    "invoice_number": "INV-12345",
    "items": [
        {
            "description": "Office Chair",
            "quantity": 1,
            "unit_price": 89.99,
            "amount": 89.99
        },
        {
            "description": "Desk Lamp",
            "quantity": 2,
            "unit_price": 18.00,
            "amount": 36.00
        }
    ],
    "subtotal": 125.99,
    "tax_amount": 0.0,
    "payment_method": "Credit Card"
}

# Sample query results
SAMPLE_QUERY_RESULTS = [
    {
        "id": 1,
        "vendor": "Amazon",
        "date": "2023-03-15",
        "total_amount": 125.99,
        "invoice_number": "INV-12345"
    },
    {
        "id": 2,
        "vendor": "Amazon",
        "date": "2023-03-22",
        "total_amount": 54.32,
        "invoice_number": "INV-67890"
    }
]

# Sample SQL query
SAMPLE_SQL_QUERY = """
SELECT id, vendor, date, total_amount, invoice_number 
FROM invoices 
WHERE vendor = 'Amazon' AND date >= '2023-03-01' AND date <= '2023-03-31'
"""

# Expected response formats based on intent
EXPECTED_RESPONSE_FORMATS = {
    "greeting": {
        "contains": ["Welcome", "InvoiceAgent", "what I can do", "ask me things like"]
    },
    "general": {
        "contains": ["invoice-related queries", "what I can help you with"]
    },
    "invoice_query": {
        "contains": ["expenses", "Total Spent", "Number of Invoices"]
    },
    "invoice_creation": {
        "contains": ["invoice has been created", "Vendor", "Date", "Amount"]
    },
    "invalid_invoice": {
        "contains": ["not a valid invoice", "upload a clear image"]
    },
    "valid_invoice": {
        "contains": ["Invoice uploaded", "processed successfully", "Vendor", "Date", "Amount"]
    }
} 