#!/usr/bin/env python
"""
Invoice Template Constants Module

This module provides centralized constants for the invoice template service.
Keeping these constants separate allows for easier maintenance and configuration.
"""
import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = BASE_DIR / "template"
DEFAULT_OUTPUT_DIR = (
    "/tmp/generated_invoices"
    if os.environ.get("VERCEL") == "1"
    else str(BASE_DIR / "data" / "generated_invoices")
)
OUTPUT_DIR = Path(os.environ.get("GENERATED_INVOICE_OUTPUT_DIR", DEFAULT_OUTPUT_DIR))

# Default templates
DEFAULT_TEMPLATE = "InvoiceDocument.docx"

# Template types with relevant keywords and required fields
TEMPLATE_TYPES = {
    "default": {
        "name": "Modern Invoice Template",
        "file": "InvoiceDocument.docx",
        "keywords": [
            "professional",
            "default",
            "service",
            "goods",
            "invoice",
            "hours",
            "products",
            "general",
            "standard",
        ],
        "required_fields": [
            "company_name",
            "invoice_number",
            "invoice_date",
            "items",
            "total_amount"
        ],
        "optional_fields": [
            "company_address",
            "company_phone",
            "company_email",
            "company_website",
            "client_name",
            "client_company",
            "client_address",
            "client_phone",
            "client_email",
            "payment_terms",
            "due_date",
            "subtotal",
            "tax_rate",
            "tax_amount",
            "discount_rate",
            "discount_amount",
            "status"
        ]
    },
    "bracket_template": {
        "name": "Bracket Placeholder Template",
        "file": "BracketInvoice.docx",
        "keywords": ["bracket", "placeholder", "general", "standard", "modern"],
        "required_fields": [
            "company_name",
            "invoice_number",
            "invoice_date",
            "items",
            "total_amount"
        ],
        "optional_fields": [
            "company_address",
            "company_phone",
            "company_email",
            "company_website",
            "client_name",
            "client_company",
            "client_address",
            "client_phone",
            "client_email",
            "payment_terms",
            "due_date",
            "subtotal",
            "tax_rate",
            "tax_amount",
            "discount_rate",
            "discount_amount",
            "status"
        ]
    }
    # Note: We've removed all other template types to simplify
}

# Field mappings for placeholders in the template
FIELD_MAPPINGS = {
    # Company information - placeholders in the template
    "Company Name": "company_name",
    "Your Company Slogan": "company_slogan",
    "Street Address": "company_address",
    "City, ST ZIP Code": "company_city",
    "[Phone]": "company_phone",
    "[Fax]": "company_fax",
    "555-1234": "company_phone",
    "[555-1234]": "company_phone",

    # Invoice information
    "[100]": "invoice_number",
    "[Date]": "invoice_date",
    "04/13/2025": "invoice_date",
    "[04/13/2025]": "invoice_date",
    "#INV-": "invoice_number",

    # Client information
    "To:": "client_name",
    "Assist Gen Ai": "client_name",
    "[Recipient Name]": "client_name",
    "Company Name": "client_company",
    "Street Address": "client_address",
    "City, ST ZIP Code": "client_city",
    "[Phone]": "client_phone",

    # Financial information
    "$500.00": "total_amount",
    "SUBTOTAL": "subtotal",
    "SALES TAX": "tax_amount",
    "SHIPPING & HANDLING": "shipping_amount"
}

# Direct replacements for Company Name and Client Name
# to avoid conflicts in the field_mappings
DIRECT_REPLACEMENTS = [
    {
        "placeholder": "Company Name",
        "field": "company_name",
        "section": "header" # This is the company section at the top
    },
    {
        "placeholder": "Assist Gen Ai",
        "field": "client_name",
        "section": "recipient" # This is the client section
    }
]

# Field variations for normalization
FIELD_VARIATIONS = {
    # Company profile fields
    "company_name": ["company_name", "vendor", "business_name"],
    "company_address": ["company_address", "address", "business_address"],
    "company_phone": ["company_phone", "phone", "business_phone", "telephone"],
    "company_email": ["company_email", "email", "business_email"],
    "company_website": ["company_website", "website", "business_website"],
    "company_slogan": ["company_slogan", "tagline", "business_tagline"],
    "company_fax": ["company_fax", "fax", "business_fax"],
    "payment_terms": ["payment_terms", "terms"],

    # Client profile fields
    "client_name": ["client_name", "customer_name", "recipient_name"],
    "client_company": ["client_company", "customer_company", "recipient_company"],
    "client_address": ["client_address", "customer_address", "recipient_address"],
    "client_phone": ["client_phone", "customer_phone", "recipient_phone"],
    "client_email": ["client_email", "customer_email", "recipient_email"],
}

# Important template fields to look for
IMPORTANT_TEMPLATE_FIELDS = [
    "Company Name",
    "Street Address",
    "City, ST ZIP Code",
    "555-1234",
    "Your Company Slogan"
]

# Currency symbols mapping
CURRENCY_SYMBOLS = {
    'USD': '$',
    'EUR': '€',
    'GBP': '£',
    'JPY': '¥',
    'INR': '₹',
    'CAD': 'C$',
    'AUD': 'A$',
    'CHF': 'CHF',
    'CNY': '¥',
    'NZD': 'NZ$',
}

# Monetary field indicators
MONETARY_FIELDS = ["price", "amount", "total", "cost", "subtotal", "tax", "shipping"]
