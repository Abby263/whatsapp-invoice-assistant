"""
Test for workflow modules.

This module tests the various workflow components to ensure they function
correctly and integrate properly with each other.
"""

import pytest
import os
import asyncio
from typing import Dict, Any, List, Optional
from unittest.mock import MagicMock, patch
import tempfile
import logging
from pathlib import Path

from langchain_app.text_processing_workflow import process_text_message, classify_intent
from langchain_app.general_response_workflow import process_general_response, process_greeting
from langchain_app.invoice_query_workflow import process_invoice_query, convert_to_sql, execute_query
from langchain_app.invoice_creator_workflow import process_invoice_creation, extract_invoice_entities
from langchain_app.file_processing_workflow import process_file_message, validate_file, detect_file_type
from langchain_app.state import IntentType, FileType

# Configure logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.fixture
def sample_text_input():
    return "Hello, I need help with invoices"


@pytest.fixture
def sample_query_input():
    return "How many invoices do I have from Amazon?"


@pytest.fixture
def sample_creation_input():
    return "Create an invoice for Office Depot for $120 for office supplies dated yesterday"


@pytest.fixture
def sample_greeting_input():
    return "Hi there, how are you?"


@pytest.fixture
def sample_file_path():
    # Create a temporary PDF file for testing
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(b"%PDF-1.4\n")  # Add PDF header
        file_path = tmp.name
    
    # Return the path and ensure it's cleaned up after the test
    yield file_path
    try:
        os.unlink(file_path)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_intent_classification(sample_text_input, sample_query_input, 
                                   sample_creation_input, sample_greeting_input):
    """Test that intent classification works correctly for different input types."""
    # Patch the IntentClassifierAgent to return predetermined intents
    with patch("agents.text_intent_classifier.TextIntentClassifierAgent.process") as mock_process:
        # Set up mock returns for different inputs
        async def mock_process_side_effect(input_data):
            content = input_data.get("content", "")
            
            if "hello" in content.lower() or "hi there" in content.lower():
                return {"intent": IntentType.GREETING.value}
            elif "how many" in content.lower() or "query" in content.lower():
                return {"intent": IntentType.INVOICE_QUERY.value}
            elif "create" in content.lower():
                return {"intent": IntentType.INVOICE_CREATOR.value}
            else:
                return {"intent": IntentType.GENERAL.value}
                
        mock_process.side_effect = mock_process_side_effect
        
        # Test greeting intent
        intent = await classify_intent(sample_greeting_input)
        assert intent == IntentType.GREETING.value
        
        # Test query intent
        intent = await classify_intent(sample_query_input)
        assert intent == IntentType.INVOICE_QUERY.value
        
        # Test creation intent
        intent = await classify_intent(sample_creation_input)
        assert intent == IntentType.INVOICE_CREATOR.value
        
        # Test general intent
        intent = await classify_intent("What can you do?")
        assert intent == IntentType.GENERAL.value


@pytest.mark.asyncio
async def test_text_processing_workflow(sample_greeting_input):
    """Test the text processing workflow for greeting messages."""
    # Patch the dependent functions to avoid actual API calls, including the entire general_response_workflow module
    with patch("langchain_app.text_processing_workflow.classify_intent") as mock_classify:
        # Set up mock returns
        mock_classify.return_value = IntentType.GREETING.value
        
        # Call the function under test
        result = await process_text_message(sample_greeting_input)
        
        # Verify the result
        assert "WhatsApp Invoice Assistant" in result["content"]
        assert result["metadata"]["intent"] == IntentType.GREETING.value
        assert 0.4 <= result["confidence"] <= 0.9  # Allow for a range of confidence values
        
        # Verify the mock was called correctly
        mock_classify.assert_called_once_with(sample_greeting_input, None)


@pytest.mark.asyncio
async def test_general_response_workflow():
    """Test the general response workflow."""
    # Patch the ResponseFormatterAgent to return a predetermined response
    with patch("agents.response_formatter.ResponseFormatterAgent.process") as mock_process:
        mock_process.return_value = {
            "content": "I'm your WhatsApp Invoice Assistant. How can I help you?",
            "confidence": 0.8
        }
        
        # Call the function under test
        result = await process_general_response("What can you do?")
        
        # Verify the result
        assert "I'm your WhatsApp Invoice Assistant" in result["content"]
        assert result["metadata"]["intent"] == IntentType.GENERAL.value
        assert result["confidence"] == 0.8
        
        # Also test greeting process
        result = await process_greeting("Hello")
        assert "I'm your WhatsApp Invoice Assistant" in result["content"]
        assert result["metadata"]["intent"] == IntentType.GREETING.value


@pytest.mark.asyncio
async def test_invoice_query_workflow():
    """Test the invoice query workflow."""
    # Patch the necessary functions and agents
    with patch("langchain_app.invoice_query_workflow.convert_to_sql") as mock_convert, \
         patch("langchain_app.invoice_query_workflow.execute_query") as mock_execute, \
         patch("langchain_app.invoice_query_workflow.format_query_response") as mock_format:
        
        # Set up mock returns
        mock_convert.return_value = {
            "sql_query": "SELECT * FROM invoices WHERE vendor = 'Amazon'",
            "explanation": "Query to find Amazon invoices"
        }
        
        mock_execute.return_value = {
            "success": True,
            "results": [
                {"id": 1, "vendor": "Amazon", "total_amount": 100.0},
                {"id": 2, "vendor": "Amazon", "total_amount": 200.0}
            ],
            "query": "SELECT * FROM invoices WHERE vendor = 'Amazon'"
        }
        
        mock_format.return_value = {
            "content": "I found 2 invoices from Amazon totaling $300.",
            "confidence": 0.9
        }
        
        # Create mock session
        mock_session = MagicMock()
        
        # Call the function under test with mocked session
        result = await process_invoice_query(
            "How many invoices do I have from Amazon?",
            db_session=mock_session
        )
        
        # Verify the result
        assert "I found 2 invoices from Amazon" in result["content"]
        assert result["metadata"]["intent"] == IntentType.INVOICE_QUERY.value
        assert result["metadata"]["results_count"] == 2
        assert result["confidence"] == 0.9
        
        # Test without session - should return a message about not being able to execute
        result_no_session = await process_invoice_query(
            "How many invoices do I have from Amazon?"
        )
        
        assert "I've generated a database query" in result_no_session["content"]
        assert "SELECT * FROM invoices WHERE vendor = 'Amazon'" in result_no_session["content"]
        assert result_no_session["metadata"]["intent"] == IntentType.INVOICE_QUERY.value
        assert result_no_session["metadata"]["query"] == "SELECT * FROM invoices WHERE vendor = 'Amazon'"
        assert not result_no_session["metadata"]["success"]


@pytest.mark.asyncio
async def test_invoice_creation_workflow():
    """Test the invoice creation workflow."""
    # Patch the necessary functions and agents
    with patch("langchain_app.invoice_creator_workflow.extract_invoice_entities") as mock_extract, \
         patch("langchain_app.invoice_creator_workflow.validate_invoice_entities") as mock_validate, \
         patch("langchain_app.invoice_creator_workflow.generate_invoice_pdf") as mock_generate, \
         patch("langchain_app.invoice_creator_workflow.format_invoice_creation_response") as mock_format:
        
        # Set up mock returns
        mock_extract.return_value = {
            "vendor": "Office Depot",
            "total_amount": 120.0,
            "items": [{"description": "Office supplies", "quantity": 1, "unit_price": 120.0}]
        }
        
        # Pass through the validated entities
        mock_validate.side_effect = lambda x: x
        
        mock_generate.return_value = "/tmp/invoice_123.pdf"
        
        mock_format.return_value = {
            "content": "I've created an invoice for Office Depot for $120.00.",
            "confidence": 0.9
        }
        
        # Call the function under test
        result = await process_invoice_creation(
            "Create an invoice for Office Depot for $120 for office supplies"
        )
        
        # Verify the result
        assert "I've created an invoice for Office Depot" in result["content"]
        assert result["metadata"]["invoice"]["vendor"] == "Office Depot"
        assert result["metadata"]["invoice"]["total_amount"] == 120.0
        assert result["metadata"]["pdf_path"] == "/tmp/invoice_123.pdf"
        assert result["confidence"] == 0.9


@pytest.mark.asyncio
async def test_file_processing_workflow(sample_file_path):
    """Test the file processing workflow."""
    # Patch the necessary functions and agents
    with patch("langchain_app.file_processing_workflow.validate_file") as mock_validate, \
         patch("langchain_app.file_processing_workflow.extract_invoice_data") as mock_extract, \
         patch("langchain_app.file_processing_workflow.format_extraction_response") as mock_format:
        
        # Set up mock returns for a valid invoice file
        mock_validate.return_value = {
            "is_valid": True,
            "is_invoice": True,
            "confidence": 0.9,
            "file_type": FileType.PDF.value
        }
        
        mock_extract.return_value = {
            "data": {
                "vendor": "Office Depot",
                "invoice_number": "INV-12345",
                "total_amount": 120.0,
                "currency": "USD",
                "invoice_date": "2023-09-15"
            },
            "file_type": FileType.PDF.value
        }
        
        mock_format.return_value = {
            "content": "I've extracted data from your invoice. Vendor: Office Depot, Amount: $120.00",
            "confidence": 0.8
        }
        
        # Call the function under test
        result = await process_file_message(
            sample_file_path,
            "application/pdf",
            "invoice.pdf",
            "user123"
        )
        
        # Verify the result
        assert "I've extracted data from your invoice" in result["content"]
        assert result["metadata"]["intent"] == IntentType.FILE_PROCESSING.value
        assert result["metadata"]["file_type"] == FileType.PDF.value
        assert result["metadata"]["invoice_data"]["vendor"] == "Office Depot"
        assert result["confidence"] == 0.8
        
        # Test invalid file handling
        mock_validate.return_value = {
            "is_valid": False,
            "is_invoice": False,
            "reason": "Not a valid PDF file",
            "file_type": FileType.BINARY.value
        }
        
        with patch("langchain_app.file_processing_workflow.format_invalid_file_response") as mock_invalid_format:
            mock_invalid_format.return_value = {
                "content": "I couldn't process your file. Not a valid PDF file.",
                "metadata": {"intent": IntentType.FILE_PROCESSING.value, "success": False},
                "confidence": 0.5
            }
            
            result = await process_file_message(
                sample_file_path,
                "application/octet-stream",
                "unknown.bin",
                "user123"
            )
            
            assert "I couldn't process your file" in result["content"]
            assert not result["metadata"].get("success", True)


@pytest.mark.asyncio
async def test_file_type_detection():
    """Test file type detection."""
    # Test PDF detection
    assert detect_file_type("/path/to/file.pdf", "application/pdf") == FileType.PDF.value
    
    # Test image detection
    assert detect_file_type("/path/to/file.jpg", "image/jpeg") == FileType.IMAGE.value
    assert detect_file_type("/path/to/file.png", "image/png") == FileType.IMAGE.value
    
    # Test Excel detection
    assert detect_file_type("/path/to/file.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") == FileType.EXCEL.value
    
    # Test CSV detection
    assert detect_file_type("/path/to/file.csv", "text/csv") == FileType.CSV.value
    
    # Test fallback to binary
    assert detect_file_type("/path/to/file.unknown", "application/octet-stream") == FileType.BINARY.value 