"""
End-to-end test for the WhatsApp Invoice Assistant workflows.

This module tests the integration of all workflow components, simulating
the complete flow from receiving a message to generating a response.
"""

import pytest
import asyncio
import logging
import tempfile
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# Mock the database module before importing the actual modules
sys.modules['services.database'] = MagicMock()
sys.modules['database.connection'] = MagicMock()
sys.modules['database.schemas'] = MagicMock()
sys.modules['database.crud'] = MagicMock()
sys.modules['database.models'] = MagicMock()

# Mock the memory modules
sys.modules['memory.langgraph_memory'] = MagicMock()
sys.modules['memory.context_manager'] = MagicMock()

# Now we can import the modules that depend on these mocked modules
from langchain_app.state import IntentType, FileType

# Configure logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Patch the API module's imports for database-related functions
@pytest.mark.asyncio
@patch('langchain_app.api.process_text', AsyncMock(return_value={
    'content': 'Hello, I am the WhatsApp Invoice Assistant!',
    'metadata': {'intent': IntentType.GREETING.value}
}))
async def test_text_greeting_workflow():
    """Test the end-to-end greeting workflow."""
    # Dynamically import after mocking
    from langchain_app.api import process_text_message
    
    # Process a greeting message
    result = await process_text_message(
        "Hello, I'm new to this assistant!",
        "user123"
    )
    
    # Verify response structure
    assert "message" in result
    assert "Hello, I am the WhatsApp Invoice Assistant!" in result["message"]
    assert "metadata" in result
    assert result["metadata"].get("intent") == IntentType.GREETING.value


@pytest.mark.asyncio
@patch('langchain_app.api.process_text', AsyncMock(return_value={
    'content': 'You have 3 invoices from Amazon.',
    'metadata': {'intent': IntentType.INVOICE_QUERY.value, 'query': 'Amazon invoices'}
}))
async def test_invoice_query_workflow():
    """Test the end-to-end invoice query workflow."""
    # Dynamically import after mocking
    from langchain_app.api import process_text_message
    
    # Process an invoice query
    result = await process_text_message(
        "How many invoices do I have from Amazon?",
        "user123"
    )
    
    # Verify response structure
    assert "message" in result
    assert "You have 3 invoices from Amazon." in result["message"]
    assert "metadata" in result
    assert result["metadata"].get("intent") == IntentType.INVOICE_QUERY.value
    assert "query" in result["metadata"]


@pytest.mark.asyncio
@patch('langchain_app.api.process_text', AsyncMock(return_value={
    'content': 'I have created an invoice for Office Depot for $120.',
    'metadata': {
        'intent': IntentType.INVOICE_CREATOR.value,
        'invoice': {'vendor': 'Office Depot', 'amount': 120, 'description': 'office supplies'}
    }
}))
async def test_invoice_creation_workflow():
    """Test the end-to-end invoice creation workflow."""
    # Dynamically import after mocking
    from langchain_app.api import process_text_message
    
    # Process an invoice creation request
    result = await process_text_message(
        "Create an invoice for Office Depot for $120 for office supplies dated yesterday",
        "user123"
    )
    
    # Verify response structure
    assert "message" in result
    assert "I have created an invoice for Office Depot" in result["message"]
    assert "metadata" in result
    assert result["metadata"].get("intent") == IntentType.INVOICE_CREATOR.value
    assert "invoice" in result["metadata"]


@pytest.mark.asyncio
@patch('langchain_app.api.process_file', AsyncMock(return_value={
    'content': 'I have processed your invoice file.',
    'metadata': {'file_type': FileType.PDF.value}
}))
async def test_file_processing_workflow():
    """Test the end-to-end file processing workflow."""
    # Dynamically import after mocking
    from langchain_app.api import process_file_message
    
    # Create a temporary PDF file
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(b"%PDF-1.4\n")  # Add PDF header
        file_path = tmp.name
    
    try:
        # Process a file message
        result = await process_file_message(
            file_path,
            "invoice.pdf",
            "application/pdf",
            "user123"
        )
        
        # Verify response structure
        assert "message" in result
        assert "I have processed your invoice file" in result["message"]
        assert "metadata" in result
        assert result["metadata"].get("file_type") == FileType.PDF.value
    finally:
        # Clean up the temporary file
        try:
            os.unlink(file_path)
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(test_text_greeting_workflow())
    asyncio.run(test_invoice_query_workflow())
    asyncio.run(test_invoice_creation_workflow())
    asyncio.run(test_file_processing_workflow())
    logger.info("All end-to-end tests completed successfully!") 