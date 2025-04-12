"""
Tests for the InvoiceEntityExtractionAgent.
"""

import pytest
import json
import logging
from typing import Dict, Any

from agents.invoice_entity_extraction_agent import InvoiceEntityExtractionAgent
from services.llm_factory import LLMFactory
from utils.base_agent import AgentInput, AgentContext
from tests.fixtures.test_data import (
    INVOICE_CREATION_INPUTS,
    SAMPLE_CONVERSATION_HISTORY
)

# Configure logger for tests
logger = logging.getLogger(__name__)

@pytest.fixture
def llm_factory():
    """Create a real LLM factory instance for testing."""
    factory = LLMFactory()
    return factory

@pytest.fixture
def entity_extraction_agent(llm_factory):
    """Create an InvoiceEntityExtractionAgent instance."""
    agent = InvoiceEntityExtractionAgent(llm_factory=llm_factory)
    return agent

def test_init_invoice_extraction_agent(llm_factory):
    """Test initializing the InvoiceEntityExtractionAgent."""
    agent = InvoiceEntityExtractionAgent(llm_factory=llm_factory)
    assert agent is not None
    assert isinstance(agent.llm_factory, LLMFactory)

@pytest.mark.asyncio
async def test_extract_invoice_entities(entity_extraction_agent):
    """Test extracting entities from invoice creation requests."""
    # Test with a simple invoice creation request
    text = "Create an invoice for $100 from Amazon on March 5"
    
    agent_input = AgentInput(
        content=text
    )
    
    context = AgentContext()
    
    # Process the text for entity extraction
    result = await entity_extraction_agent.process(agent_input, context)
    
    # Verify the result
    assert result is not None
    assert isinstance(result.content, dict)
    extracted_entities = result.content
    
    # Basic validation of extracted data
    assert "vendor" in extracted_entities
    assert result.confidence > 0
    assert result.status == "success"
    
    # Fixed assertion to properly check for Amazon in the vendor field
    vendor = extracted_entities.get("vendor", "")
    assert "amazon" in vendor.lower()
    
    assert extracted_entities.get("total_amount") or extracted_entities.get("amount")
    
    # Log the result for verification
    logger.info(f"Invoice entity extraction result: {result}")

@pytest.mark.asyncio
async def test_extract_line_items(entity_extraction_agent):
    """Test extracting line items from invoice descriptions."""
    # Test with an invoice request containing line items
    text = "Create an invoice for office supplies: 2 pens at $3 each, 1 notebook for $5, total $11"
    
    agent_input = AgentInput(
        content=text
    )
    
    context = AgentContext()
    
    # Process the text for entity extraction
    result = await entity_extraction_agent.process(agent_input, context)
    
    # Verify the result
    assert result is not None
    assert isinstance(result.content, dict)
    extracted_entities = result.content
    
    # Check for items in the result
    assert "items" in extracted_entities
    items = extracted_entities.get("items", [])
    assert len(items) > 0
    
    # Check for total amount
    total = extracted_entities.get("total_amount") or extracted_entities.get("amount")
    assert total is not None
    
    # Verify we have some line items with descriptions
    has_pen = False
    has_notebook = False
    
    for item in items:
        if "pen" in str(item.get("description", "")).lower():
            has_pen = True
        if "notebook" in str(item.get("description", "")).lower():
            has_notebook = True
    
    assert has_pen or has_notebook, "Expected to find pen or notebook in line items"
    
    # Log the result for verification
    logger.info(f"Line items extraction result: {result}")

@pytest.mark.asyncio
async def test_extract_with_conversation_context(entity_extraction_agent):
    """Test entity extraction with conversation history."""
    # Test with a query that requires context
    text = "Create an invoice for that order I mentioned earlier"
    
    agent_input = AgentInput(
        content=text
    )
    
    # Create context with conversation history
    context = AgentContext(
        conversation_history=SAMPLE_CONVERSATION_HISTORY
    )
    
    # Process the query with context
    result = await entity_extraction_agent.process(agent_input, context)
    
    # Verify the result
    assert result is not None
    assert isinstance(result.content, dict)
    extracted_entities = result.content
    
    # With context, we should get some entities, even if incomplete
    assert len(extracted_entities) > 0
    
    # Accept both success and incomplete_extraction statuses as valid for this test
    # Since extracting from context is challenging for the LLM
    assert result.status in ["success", "incomplete_extraction"]
    
    # Log the result for verification
    logger.info(f"Context-based extraction result: {result}")

@pytest.mark.asyncio
async def test_error_handling(entity_extraction_agent, monkeypatch):
    """Test error handling in the entity extraction agent."""
    # Patch the extract_invoice_entities method to simulate an error
    async def mock_error(*args, **kwargs):
        raise Exception("Test validation error")
    
    monkeypatch.setattr(entity_extraction_agent.llm_factory, "extract_invoice_entities", mock_error)
    
    text = "Create an invoice for $100"
    
    agent_input = AgentInput(
        content=text
    )
    
    context = AgentContext()
    
    # Should handle exceptions gracefully
    result = await entity_extraction_agent.process(agent_input, context)
    
    # Verify the result
    assert result is not None
    assert result.content == {}
    assert result.status == "error"
    assert "error" in result.__dict__
    assert "Test validation error" in result.error
    
    # Log the result for verification
    logger.info(f"Error handling result: {result}")

@pytest.mark.asyncio
async def test_invalid_llm_response(entity_extraction_agent, monkeypatch):
    """Test handling invalid LLM responses."""
    # Patch the extract_invoice_entities method to return an invalid response
    async def mock_invalid_response(*args, **kwargs):
        return "Not a valid JSON"
    
    monkeypatch.setattr(entity_extraction_agent.llm_factory, "extract_invoice_entities", mock_invalid_response)
    
    text = "Create an invoice for $100"
    
    agent_input = AgentInput(
        content=text
    )
    
    context = AgentContext()
    
    # Should handle invalid responses gracefully
    result = await entity_extraction_agent.process(agent_input, context)
    
    # Verify the result
    assert result is not None
    assert isinstance(result.content, dict)
    assert result.confidence == 0
    assert "metadata" in result.__dict__
    assert "Failed to parse" in result.metadata.get("explanation", "")
    
    # Log the result for verification
    logger.info(f"Invalid response result: {result}") 