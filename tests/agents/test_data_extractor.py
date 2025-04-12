"""
Tests for the DataExtractorAgent.
"""

import pytest
import json
import logging
import os
from pathlib import Path

from agents.data_extractor import DataExtractorAgent
from services.llm_factory import LLMFactory
from utils.base_agent import AgentInput, AgentOutput, AgentContext
from tests.fixtures.test_data import (
    VALID_INVOICE_PATH,
    INVALID_INVOICE_PATH,
    SAMPLE_INVOICE_DATA
)

logger = logging.getLogger(__name__)

@pytest.fixture
def llm_factory():
    """Create a real LLM factory instance."""
    return LLMFactory()

@pytest.fixture
def data_extractor_agent(llm_factory):
    """Create a data extractor agent."""
    return DataExtractorAgent(llm_factory=llm_factory)

@pytest.mark.asyncio
async def test_init_data_extractor(llm_factory):
    """Test initializing the DataExtractorAgent."""
    agent = DataExtractorAgent(llm_factory=llm_factory)
    assert agent is not None
    assert isinstance(agent.llm_factory, LLMFactory)

@pytest.mark.asyncio
async def test_extract_data_from_valid_invoice(data_extractor_agent, monkeypatch):
    """Test extracting data from a valid invoice file."""
    
    # Create a function that returns sample invoice data
    async def mock_extract_invoice_data(*args, **kwargs):
        return json.dumps(SAMPLE_INVOICE_DATA)
    
    # Patch the LLM factory method
    monkeypatch.setattr(data_extractor_agent.llm_factory, "extract_invoice_data", mock_extract_invoice_data)
    
    # Create file input
    with open(VALID_INVOICE_PATH, 'rb') as f:
        file_content = f.read()
    
    agent_input = AgentInput(
        content=file_content,
        metadata={
            'file_path': str(VALID_INVOICE_PATH),
            'input_type': 'image'
        }
    )
    
    # Process the input
    result = await data_extractor_agent.process(agent_input)
    
    assert isinstance(result, AgentOutput)
    assert result.content is not None
    assert "vendor" in result.content
    assert result.content["vendor"] == "Amazon"
    assert "date" in result.content
    assert result.content["date"] == "2023-03-15"
    assert "total_amount" in result.content
    assert result.content["total_amount"] == 125.99
    assert "items" in result.content
    assert len(result.content["items"]) == 2
    assert result.content["items"][0]["description"] == "Office Chair"
    assert result.content["items"][1]["description"] == "Desk Lamp"
    assert result.status == "success"
    
    logger.info(f"Extracted invoice data: {result.content}")

@pytest.mark.asyncio
async def test_extract_data_from_unsupported_file(data_extractor_agent, monkeypatch):
    """Test extracting data from an unsupported file."""
    
    # Create a function that returns an error for unsupported files
    async def mock_extract_invoice_data(*args, **kwargs):
        return json.dumps({
            "vendor": "Unknown",
            "date": None,
            "total_amount": 0.0,
            "currency": "USD",
            "invoice_number": None,
            "items": [],
            "error": "Could not extract data from this file"
        })
    
    # Patch the LLM factory method
    monkeypatch.setattr(data_extractor_agent.llm_factory, "extract_invoice_data", mock_extract_invoice_data)
    
    # Create file input with invalid file
    with open(INVALID_INVOICE_PATH, 'rb') as f:
        file_content = f.read()
    
    agent_input = AgentInput(
        content=file_content,
        metadata={
            'file_path': str(INVALID_INVOICE_PATH),
            'input_type': 'image'
        }
    )
    
    # Process the input
    result = await data_extractor_agent.process(agent_input)
    
    assert isinstance(result, AgentOutput)
    assert result.content is not None
    assert "error" in result.content
    assert "Could not extract data" in result.content["error"]
    assert result.status == "error"
    
    logger.info(f"Error extracting from unsupported file: {result.error}")

@pytest.mark.asyncio
async def test_handle_different_file_types(data_extractor_agent, monkeypatch):
    """Test handling different file types."""
    
    # Create a function that returns different data for different file types
    async def mock_extract_invoice_data(content, *args, **kwargs):
        # We're testing the agent's handling of metadata here
        if 'image' in str(content):
            return json.dumps(SAMPLE_INVOICE_DATA)
        else:
            return json.dumps({
                "vendor": "Test Vendor",
                "date": "2023-01-01",
                "total_amount": 50.0,
                "currency": "USD",
                "invoice_number": "TEST-123",
                "items": []
            })
    
    # Patch the LLM factory method
    monkeypatch.setattr(data_extractor_agent.llm_factory, "extract_invoice_data", mock_extract_invoice_data)
    
    # Create file input with valid invoice file
    with open(VALID_INVOICE_PATH, 'rb') as f:
        file_content = f.read()
    
    # Test with different file types
    file_types = ['image', 'pdf', 'excel', 'csv']
    
    for file_type in file_types:
        agent_input = AgentInput(
            content=file_content,
            metadata={
                'file_path': str(VALID_INVOICE_PATH),
                'input_type': file_type
            }
        )
        
        # Process the input
        result = await data_extractor_agent.process(agent_input)
        
        assert isinstance(result, AgentOutput)
        assert result.content is not None
        assert "vendor" in result.content
        assert result.status == "success"
        
        # The input type should be recorded in metadata
        assert result.metadata["file_type"] == file_type
        
        logger.info(f"Processed {file_type} file, vendor: {result.content.get('vendor')}")

@pytest.mark.asyncio
async def test_handle_missing_file(data_extractor_agent):
    """Test handling a missing file path."""
    
    # Create input with non-existent file path but empty content
    agent_input = AgentInput(
        content="",  # Empty content
        metadata={
            'file_path': 'non_existent_file.png',
            'input_type': 'image'
        }
    )
    
    # Process the input
    result = await data_extractor_agent.process(agent_input)
    
    assert isinstance(result, AgentOutput)
    assert result.status == "error"
    assert result.error is not None
    assert "empty" in result.error.lower() or "invalid" in result.error.lower()
    
    logger.info(f"Error with missing file: {result.error}")

@pytest.mark.asyncio
async def test_error_handling(data_extractor_agent, monkeypatch):
    """Test error handling in the data extractor agent."""
    
    # Create a function that raises an exception
    async def mock_extract_error(*args, **kwargs):
        raise Exception("Test extraction error")
    
    # Patch the LLM factory method
    monkeypatch.setattr(data_extractor_agent.llm_factory, "extract_invoice_data", mock_extract_error)
    
    # Create input
    with open(VALID_INVOICE_PATH, 'rb') as f:
        file_content = f.read()
    
    agent_input = AgentInput(
        content=file_content,
        metadata={
            'file_path': str(VALID_INVOICE_PATH),
            'input_type': 'image'
        }
    )
    
    # Process the input
    result = await data_extractor_agent.process(agent_input)
    
    assert isinstance(result, AgentOutput)
    assert result.status == "error"
    assert result.error is not None
    assert "Test extraction error" in result.error
    assert result.confidence == 0.0
    
    logger.info(f"Error handling result: {result.error}")

@pytest.mark.asyncio
async def test_invalid_llm_response(data_extractor_agent, monkeypatch):
    """Test handling invalid LLM responses."""
    
    # Create a function that returns an invalid response
    async def mock_invalid_response(*args, **kwargs):
        return "Not a valid JSON"
    
    # Patch the LLM factory method
    monkeypatch.setattr(data_extractor_agent.llm_factory, "extract_invoice_data", mock_invalid_response)
    
    # Create input
    with open(VALID_INVOICE_PATH, 'rb') as f:
        file_content = f.read()
    
    agent_input = AgentInput(
        content=file_content,
        metadata={
            'file_path': str(VALID_INVOICE_PATH),
            'input_type': 'image'
        }
    )
    
    # Process the input
    result = await data_extractor_agent.process(agent_input)
    
    assert isinstance(result, AgentOutput)
    assert result.content is not None
    assert "error" in result.content
    assert "Failed to parse" in result.content["error"]
    assert result.confidence == 0.0
    
    logger.info(f"Invalid response handling result: {result.error}")

@pytest.mark.asyncio
async def test_extract_specific_fields(data_extractor_agent, monkeypatch):
    """Test extracting specific fields from an invoice."""
    
    # Custom response for specific field extraction
    custom_response = {
        "vendor": {
            "name": "Acme Corp",
            "address": "123 Main St"
        },
        "transaction": {
            "date": "2023-04-01",
            "receipt_no": "INV-2023-1234"
        },
        "items": [
            {
                "description": "Consulting Services",
                "quantity": 10,
                "unit_price": 45.45,
                "total_price": 454.54
            }
        ],
        "financial": {
            "subtotal": 454.54,
            "tax": 45.45,
            "total": 499.99
        },
        "additional_info": {
            "payment_method": "Bank Transfer",
            "currency": "USD"
        },
        "confidence_score": 0.9
    }
    
    # Create a function that returns the custom response
    async def mock_custom_extract(*args, **kwargs):
        return json.dumps(custom_response)
    
    # Patch the LLM factory method
    monkeypatch.setattr(data_extractor_agent.llm_factory, "extract_invoice_data", mock_custom_extract)
    
    # Create input
    with open(VALID_INVOICE_PATH, 'rb') as f:
        file_content = f.read()
    
    agent_input = AgentInput(
        content=file_content,
        metadata={
            'file_path': str(VALID_INVOICE_PATH),
            'input_type': 'image'
        }
    )
    
    # Process the input
    result = await data_extractor_agent.process(agent_input)
    
    assert isinstance(result, AgentOutput)
    assert result.content is not None
    assert result.content["vendor"]["name"] == "Acme Corp"
    assert result.content["transaction"]["receipt_no"] == "INV-2023-1234"
    assert result.content["financial"]["tax"] == 45.45
    assert result.content["additional_info"]["payment_method"] == "Bank Transfer"
    assert result.status == "success"
    assert result.confidence == 0.9
    
    logger.info(f"Specific fields extraction result: {result.content}") 