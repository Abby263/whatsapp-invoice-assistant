"""
State management for the WhatsApp Invoice Assistant LangGraph workflow.

This module defines the state schema and helper functions for the LangGraph workflow.
"""

from enum import Enum, auto
from typing import Dict, List, Optional, Union, Any
from pydantic import BaseModel, Field
import datetime
from langchain.schema import Document


class InputType(str, Enum):
    """Type of input received from the user"""
    TEXT = "text"
    IMAGE = "image"
    PDF = "pdf" 
    EXCEL = "excel"
    CSV = "csv"
    UNKNOWN = "unknown"


class FileType(str, Enum):
    """Types of files that can be processed"""
    PDF = "pdf"
    IMAGE = "image"
    EXCEL = "excel"
    CSV = "csv"
    BINARY = "binary"
    UNKNOWN = "unknown"


class IntentType(str, Enum):
    """User intent classification types"""
    GREETING = "greeting"
    GENERAL = "general"
    INVOICE_QUERY = "invoice_query"
    INVOICE_CREATOR = "invoice_creator"
    FILE_PROCESSING = "file_processing"
    UNKNOWN = "unknown"
    CREATE_INVOICE = "create_invoice"
    HELP = "help"
    EXIT = "exit"
    UPLOAD_FILE = "upload_file"


class UserInput(BaseModel):
    """User input data structure"""
    content: Union[str, bytes] = Field(description="Text content or file binary data")
    content_type: InputType = Field(default=InputType.TEXT, description="Type of input")
    file_path: Optional[str] = Field(default=None, description="Path to uploaded file if applicable")
    file_name: Optional[str] = Field(default=None, description="Original filename if applicable")
    mime_type: Optional[str] = Field(default=None, description="MIME type of the file if applicable")
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.now, description="When the input was received")


class AgentResponse(BaseModel):
    """Standard response structure from any agent"""
    content: str = Field(description="Text content of the response")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata about the response")
    confidence: float = Field(default=1.0, description="Confidence score of the response (0-1)")
    

class ClassificationResult(BaseModel):
    """Result of intent classification"""
    intent: IntentType = Field(description="Classified intent")
    confidence: float = Field(description="Confidence score (0-1)")
    explanation: Optional[str] = Field(default=None, description="Explanation of classification")


class ValidationResult(BaseModel):
    """Result of file validation"""
    is_valid: bool = Field(description="Whether the file is valid")
    confidence: float = Field(description="Confidence score (0-1)")
    reason: Optional[str] = Field(default=None, description="Reason for validation result")


class QueryData(BaseModel):
    """Data for invoice query"""
    sql_query: Optional[str] = Field(default=None, description="Generated SQL query")
    query_params: Dict[str, Any] = Field(default_factory=dict, description="Query parameters")
    query_results: Optional[List[Dict[str, Any]]] = Field(default=None, description="Query results")
    error_message: Optional[str] = Field(default=None, description="Error message if query fails")


class InvoiceEntity(BaseModel):
    """Extracted invoice entity"""
    vendor: Optional[str] = Field(default=None, description="Vendor name")
    date: Optional[str] = Field(default=None, description="Invoice date")
    total_amount: Optional[float] = Field(default=None, description="Total amount")
    currency: Optional[str] = Field(default=None, description="Currency")
    invoice_number: Optional[str] = Field(default=None, description="Invoice number")
    items: Optional[List[Dict[str, Any]]] = Field(default=None, description="Line items")
    customer: Optional[str] = Field(default=None, description="Customer information")
    payment_method: Optional[str] = Field(default=None, description="Payment method")
    tax_amount: Optional[float] = Field(default=None, description="Tax amount")
    subtotal: Optional[float] = Field(default=None, description="Subtotal amount")
    additional_fields: Dict[str, Any] = Field(default_factory=dict, description="Additional fields")


class ConversationHistory(BaseModel):
    """Conversation history for context"""
    messages: List[Dict[str, Any]] = Field(default_factory=list, description="List of previous messages")
    

class ProcessingStage(str, Enum):
    """Enum for processing stages in workflows."""
    INITIAL = "initial"
    INTENT_DETERMINED = "intent_determined"
    QUERY_PROCESSING = "query_processing"
    CONVERTING_TO_SQL = "converting_to_sql"
    SQL_CONVERSION_COMPLETE = "sql_conversion_complete"
    SQL_EXECUTING = "sql_executing"
    SQL_EXECUTION_COMPLETE = "sql_execution_complete"
    RAG_RETRIEVAL = "rag_retrieval"
    RAG_RETRIEVAL_COMPLETE = "rag_retrieval_complete"
    RESPONSE_FORMATTING = "response_formatting"
    COMPLETED = "completed"
    ERROR = "error"
    FILE_RECEIVED = "file_received"
    FILE_VALIDATED = "file_validated"
    FILE_PROCESSING = "file_processing"
    DATA_EXTRACTION = "data_extraction"
    DATA_VERIFICATION = "data_verification"
    DATA_STORING = "data_storing"
    

class WorkflowState(BaseModel):
    """State for the LangGraph workflow"""
    user_input: Optional[UserInput] = Field(default=None, description="Current user input being processed")
    input_type: InputType = Field(default=InputType.UNKNOWN, description="Detected input type")
    intent: IntentType = Field(default=IntentType.UNKNOWN, description="Classified intent")
    file_validation: Optional[ValidationResult] = Field(default=None, description="File validation result")
    extracted_entities: Optional[InvoiceEntity] = Field(default=None, description="Extracted entities from text")
    extracted_invoice_data: Optional[InvoiceEntity] = Field(default=None, description="Extracted data from invoice file")
    query_data: Optional[QueryData] = Field(default=None, description="Query data for database operations")
    conversation_history: ConversationHistory = Field(default_factory=ConversationHistory, description="Conversation history")
    current_response: Optional[AgentResponse] = Field(default=None, description="Current response being constructed")
    errors: List[str] = Field(default_factory=list, description="Error messages during processing")
    processing_complete: bool = Field(default=False, description="Whether processing is complete")
    stage: ProcessingStage = Field(default=ProcessingStage.INITIAL, description="Current processing stage")
    user_id: Optional[str] = Field(default=None, description="User ID")
    conversation_id: Optional[str] = Field(default=None, description="Conversation ID")
    message_id: Optional[str] = Field(default=None, description="Message ID")
    input_text: Optional[str] = Field(default=None, description="Input text")
    output_text: Optional[str] = Field(default=None, description="Output text")
    error_message: Optional[str] = Field(default=None, description="Error message")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        """Pydantic config."""
        arbitrary_types_allowed = True


class QueryWorkflowState(WorkflowState):
    """State class for query workflow."""
    
    intent: IntentType = Field(default=IntentType.INVOICE_QUERY)
    sql_query: Optional[str] = Field(default=None, description="Generated SQL query")
    use_semantic_search: bool = Field(default=False, description="Whether to use semantic search")
    use_rag: bool = Field(default=False, description="Whether to use RAG")
    query_results: Optional[List[Dict[str, Any]]] = Field(default=None, description="Query results")
    confidence: float = Field(default=0.0, description="Confidence score")
    execution_time: float = Field(default=0.0, description="Execution time")


class FileProcessingState(WorkflowState):
    """State class for file processing workflow."""
    
    intent: IntentType = Field(default=IntentType.UPLOAD_FILE)
    file_path: Optional[str] = Field(default=None, description="Path to the uploaded file")
    file_type: Optional[str] = Field(default=None, description="Type of the file")
    file_size: Optional[int] = Field(default=None, description="Size of the file")
    file_content: Optional[bytes] = Field(default=None, description="Content of the file")
    validation_result: Dict[str, Any] = Field(default_factory=dict, description="Validation result")
    extracted_data: Dict[str, Any] = Field(default_factory=dict, description="Extracted data")
    stored_invoice_id: Optional[Union[str, int]] = Field(default=None, description="Stored invoice ID")

    class Config:
        """Pydantic config."""
        arbitrary_types_allowed = True 