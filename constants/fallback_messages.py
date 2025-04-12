"""
Constants for fallback messages used across the application.

This module defines all the fallback messages that should be used when primary
response generation fails. Centralizing these messages improves consistency
and makes it easier to update messaging.
"""

from .intent_types import IntentType

# General fallback messages
GENERAL_FALLBACKS = {
    "default": "I'm your WhatsApp Invoice Assistant. I can help you create invoices, extract data from invoice images, and answer questions about your invoices. Is there something specific you'd like help with?",
    "error": "Sorry, I encountered an unexpected error. Please try again or contact support if the issue persists.",
    "no_response": "I wasn't able to generate a response. Please try asking in a different way.",
    "timeout": "Your request timed out. Please try again with a simpler query.",
}

# Intent-based fallback messages
INTENT_FALLBACKS = {
    IntentType.GREETING: "👋 Hello! I'm your Invoice Assistant! Ready to help you manage your business finances. What would you like to know about your expenses today?",
    
    IntentType.GENERAL: """📊 I'm your AI-powered Invoice Assistant!

I can help you:
• Extract data from receipts and invoices
• Track and categorize expenses
• Find specific purchase information
• Analyze your spending patterns

Try asking me:
• "What did I spend at Amazon last month?"
• "Show my top spending categories"
• "Find all invoices over $100"

Or simply upload a receipt/invoice to get started!""",
    
    IntentType.HELP: "I can help you with various invoice-related tasks. You can upload an invoice for processing, create a new invoice, or ask questions about your existing invoices.",
    IntentType.GOODBYE: "Thank you for using WhatsApp Invoice Assistant. Have a great day!",
    IntentType.UNKNOWN: "I'm not sure what you're asking for. You can try rephrasing your question or ask for help to see what I can do.",
}

# File processing fallback messages
FILE_PROCESSING_FALLBACKS = {
    "invalid_file": "The file you've uploaded doesn't appear to be a valid invoice. Please try uploading a clear image of an invoice or receipt.",
    "unsupported_format": "Sorry, this file format is not supported. Please upload a PDF, image (JPG, PNG), Excel, or CSV file.",
    "extraction_failed": "I couldn't extract information from this file. Please try uploading a clearer image or a different invoice.",
    "upload_failed": "There was a problem uploading your file. Please try again later.",
}

# File validation fallback prompts
FILE_VALIDATION_PROMPTS = {
    "image_validation": """
Analyze this image and determine if it contains a valid invoice or receipt. Be liberal in your interpretation - this is for a WhatsApp Invoice Assistant that helps users track their expenses.

A valid invoice/receipt includes:
1. ANY document showing a purchase transaction (store receipts, invoices, online order confirmations, etc.)
2. Documents showing goods or services purchased with pricing
3. Any payment confirmation with vendor and amount information

IMPORTANT GUIDELINES:
- Retail receipts, store receipts, and simple payment confirmations ARE valid invoice documents
- If you can identify a vendor/merchant name and a total amount, it's likely a valid invoice/receipt
- Documents don't need to have ALL formal invoice elements to be valid
- When in doubt about borderline cases, classify as valid rather than invalid
- Even simple receipts with just store name, date and total ARE valid for our purposes

Respond with a JSON object with the following structure:
{
    "is_valid_invoice": true/false,
    "confidence_score": 0.0-1.0,
    "missing_elements": ["list of missing formal elements if any"],
    "reasons": "detailed explanation for the decision"
}
"""
}

# File validation messages
FILE_VALIDATION_MESSAGES = {
    "plain_text_invalid": "Plain text is not a valid invoice file format",
    "parse_validation_failed": "Failed to parse validation response",
    "validation_failed": "Could not properly validate the file",
    "image_validation_failed": "Could not properly validate image"
}

# Invoice query fallback messages
QUERY_FALLBACKS = {
    "no_results": "I couldn't find any invoices matching your query. You might not have any invoices uploaded yet, or try a different search term.",
    "query_error": "I encountered an error while searching for your invoices. Please try a simpler query.",
    "ambiguous_query": "Your query could match multiple invoices. Could you be more specific about what you're looking for?",
    "missing_embeddings": "I couldn't find any embeddings for semantic search. You may need to update your embeddings with 'make update-embeddings'.",
    "sql_conversion_failed": "I couldn't convert your question into a valid database query. Please try rephrasing your question.",
}

# Invoice creation fallback messages
CREATION_FALLBACKS = {
    "missing_info": "I need more information to create an invoice. Please provide details like vendor name, date, items, and amounts.",
    "validation_failed": "Some of the information provided doesn't seem valid. Please check and try again.",
    "creation_error": "There was a problem creating your invoice. Please try again with complete information.",
}

# Database fallback messages
DB_FALLBACKS = {
    "connection_error": "I'm having trouble connecting to the database. Please try again later.",
    "storage_error": "I couldn't store your information in the database. Please try again later.",
    "retrieval_error": "I couldn't retrieve the requested information from the database. Please try again later.",
}

# Storage fallback messages
STORAGE_FALLBACKS = {
    "upload_failure": "Failed to upload file to cloud storage. Please try again later.",
    "download_failure": "Failed to download file from cloud storage. Please try again later.",
    "missing_credentials": "Cloud storage credentials are missing or invalid. Please check your configuration.",
}

# API fallback messages
API_FALLBACKS = {
    "internal_error": "Internal server error. Please try again later.",
    "bad_request": "The request was malformed. Please check your input and try again.",
    "not_found": "The requested resource was not found.",
    "unauthorized": "You are not authorized to access this resource.",
}

# Get fallback message by intent type
def get_intent_fallback(intent_type: str) -> str:
    """
    Get the appropriate fallback message for a given intent type.
    
    Args:
        intent_type: The intent type string to get a fallback message for
        
    Returns:
        The fallback message for the given intent type, or a default message
    """
    return INTENT_FALLBACKS.get(intent_type, GENERAL_FALLBACKS["default"]) 