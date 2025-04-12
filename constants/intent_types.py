from enum import Enum, auto


class IntentType(str, Enum):
    """
    Enumeration of possible user intents.
    
    This enum defines the various intents that the system can recognize
    and handle when processing user inputs.
    """
    
    # General conversation intents
    GREETING = "greeting"
    GENERAL = "general"
    HELP = "help"
    GOODBYE = "goodbye"
    
    # Invoice specific intents
    INVOICE_QUERY = "invoice_query"        # User asking about an invoice
    INVOICE_CREATOR = "invoice_creator"    # User wants to create an invoice
    INVOICE_UPLOAD = "invoice_upload"      # User uploading an invoice
    
    # System or meta intents
    FEEDBACK = "feedback"                  # User providing feedback
    SETTINGS = "settings"                  # User wants to change settings
    UNKNOWN = "unknown"                    # Intent could not be determined


class IntentCategory(str, Enum):
    """
    Categorizes intents into broader groups for workflow routing.
    """
    CONVERSATION = "conversation"          # General conversation
    QUERY = "query"                        # Information retrieval
    CREATION = "creation"                  # Content creation
    UPLOAD = "upload"                      # File upload processing
    SYSTEM = "system"                      # System-related requests
    UNKNOWN = "unknown"                    # Unrecognized category


# Mapping of intents to their categories
INTENT_CATEGORY_MAPPING = {
    IntentType.GREETING: IntentCategory.CONVERSATION,
    IntentType.GENERAL: IntentCategory.CONVERSATION,
    IntentType.HELP: IntentCategory.CONVERSATION,
    IntentType.GOODBYE: IntentCategory.CONVERSATION,
    
    IntentType.INVOICE_QUERY: IntentCategory.QUERY,
    IntentType.INVOICE_CREATOR: IntentCategory.CREATION,
    IntentType.INVOICE_UPLOAD: IntentCategory.UPLOAD,
    
    IntentType.FEEDBACK: IntentCategory.SYSTEM,
    IntentType.SETTINGS: IntentCategory.SYSTEM,
    IntentType.UNKNOWN: IntentCategory.UNKNOWN
}


# Confidence thresholds for intent classification
INTENT_CONFIDENCE_THRESHOLDS = {
    "high": 0.85,      # High confidence, proceed with the detected intent
    "medium": 0.70,    # Medium confidence, may require confirmation
    "low": 0.50        # Low confidence, may need clarification
}