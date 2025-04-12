"""
Constants for invoice processing messages used across the application.

This module defines messages related to invoice processing that should be used
when formatting or presenting invoice data. Centralizing these messages improves
consistency and makes it easier to update messaging.
"""

# Invoice processing messages
INVOICE_PROCESSING_MESSAGES = {
    "formatting_error": "I've processed your invoice, but encountered an issue with the formatting.",
    "details_formatting_error": "I've processed your invoice, but encountered an issue formatting the details.",
}

# Get the appropriate invoice processing message
def get_invoice_processing_message(message_type: str) -> str:
    """
    Get the appropriate invoice processing message for a given message type.
    
    Args:
        message_type: The message type to get a message for
        
    Returns:
        The message for the given type, or a default message
    """
    return INVOICE_PROCESSING_MESSAGES.get(message_type, "I've processed your invoice information.") 