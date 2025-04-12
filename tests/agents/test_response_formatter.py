"""
Tests for the ResponseFormatterAgent.
"""

import pytest
import json
import logging
from typing import Dict, Any, Optional

from agents.response_formatter import ResponseFormatterAgent
from services.llm_factory import LLMFactory
from utils.base_agent import AgentInput, AgentOutput, AgentContext
from tests.fixtures.test_data import (
    SAMPLE_CONVERSATION_HISTORY,
    SAMPLE_INVOICE_DATA,
    SAMPLE_QUERY_RESULTS,
    EXPECTED_RESPONSE_FORMATS
)

logger = logging.getLogger(__name__)

@pytest.fixture
def llm_factory():
    """Create a real LLM factory instance."""
    return LLMFactory()

@pytest.fixture
def response_formatter_agent(llm_factory):
    """Create a response formatter agent."""
    return ResponseFormatterAgent(llm_factory=llm_factory)

@pytest.mark.asyncio
async def test_init_response_formatter(llm_factory):
    """Test initializing the ResponseFormatterAgent."""
    agent = ResponseFormatterAgent(llm_factory=llm_factory)
    assert agent is not None
    assert isinstance(agent.llm_factory, LLMFactory)

@pytest.mark.asyncio
async def test_format_greeting_response(response_formatter_agent):
    """Test formatting a greeting response."""
    
    # Create input with greeting content
    agent_input = AgentInput(
        content="Hello! Welcome to the WhatsApp Invoice Assistant!",
        metadata={
            'format_type': 'greeting'
        }
    )
    
    # Process the input
    result = await response_formatter_agent.process(agent_input)
    
    assert isinstance(result, AgentOutput)
    assert result.content is not None
    assert isinstance(result.content, str)
    assert "Welcome" in result.content
    assert result.status == "success"
    assert result.confidence >= 0.8
    
    logger.info(f"Greeting format result: {result.content}")

@pytest.mark.asyncio
async def test_format_invoice_query_response(response_formatter_agent):
    """Test formatting an invoice query response."""
    
    # Create input with query results - convert dict to JSON string first
    agent_input = AgentInput(
        content=json.dumps(SAMPLE_QUERY_RESULTS),
        metadata={
            'format_type': 'invoice_query'
        }
    )
    
    # Process the input
    result = await response_formatter_agent.process(agent_input)
    
    assert isinstance(result, AgentOutput)
    assert result.content is not None
    assert isinstance(result.content, str)
    assert "Amazon" in result.content
    assert result.status == "success"
    assert result.confidence >= 0.8
    
    logger.info(f"Invoice query format result: {result.content}")

@pytest.mark.asyncio
async def test_format_invoice_creation_response(response_formatter_agent):
    """Test formatting an invoice creation response."""
    
    # Create input with invoice data - convert dict to JSON string first
    agent_input = AgentInput(
        content=json.dumps(SAMPLE_INVOICE_DATA),
        metadata={
            'format_type': 'invoice_creation'
        }
    )
    
    # Process the input
    result = await response_formatter_agent.process(agent_input)
    
    assert isinstance(result, AgentOutput)
    assert result.content is not None
    assert isinstance(result.content, str)
    assert "Amazon" in result.content
    assert "$125.99" in result.content or "125.99" in result.content
    assert result.status == "success"
    assert result.confidence >= 0.8
    
    logger.info(f"Invoice creation format result: {result.content}")

@pytest.mark.asyncio
async def test_format_with_conversation_context(response_formatter_agent):
    """Test formatting a response with conversation context."""
    
    # Create input with context
    agent_input = AgentInput(
        content="Here's your invoice information",
        metadata={
            'format_type': 'general'
        }
    )
    
    # Create context with conversation history
    context = AgentContext(
        conversation_history=SAMPLE_CONVERSATION_HISTORY
    )
    
    # Process the input with context
    result = await response_formatter_agent.process(agent_input, context)
    
    assert isinstance(result, AgentOutput)
    assert result.content is not None
    assert isinstance(result.content, str)
    assert result.status == "success"
    assert result.confidence >= 0.8
    
    logger.info(f"Context-aware format result: {result.content}")

@pytest.mark.asyncio
async def test_error_handling(response_formatter_agent, monkeypatch):
    """Test error handling in the response formatter."""
    
    # Create a function that raises an exception
    async def mock_error(*args, **kwargs):
        raise Exception("Test formatting error")
    
    # Patch the LLM factory method
    monkeypatch.setattr(response_formatter_agent.llm_factory, "format_response", mock_error)
    
    # Create input
    agent_input = AgentInput(
        content="This will cause an error",
        metadata={
            'format_type': 'error_test'
        }
    )
    
    # Process the input
    result = await response_formatter_agent.process(agent_input)
    
    assert isinstance(result, AgentOutput)
    assert result.content is not None
    assert isinstance(result.content, str)
    assert "error" in result.content.lower() or "sorry" in result.content.lower()
    assert result.status == "error"
    assert "Test formatting error" in result.error
    assert result.confidence < 1.0
    
    logger.info(f"Error handling result: {result.content}")

@pytest.mark.asyncio
async def test_invalid_llm_response(response_formatter_agent, monkeypatch):
    """Test handling of invalid LLM responses."""
    
    # Create a function that returns an invalid response
    async def mock_invalid_response(*args, **kwargs):
        return "Not a valid JSON response"
    
    # Patch the LLM factory method
    monkeypatch.setattr(response_formatter_agent.llm_factory, "format_response", mock_invalid_response)
    
    # Create input
    agent_input = AgentInput(
        content="This will get an invalid response",
        metadata={
            'format_type': 'invalid_test'
        }
    )
    
    # Process the input
    result = await response_formatter_agent.process(agent_input)
    
    assert isinstance(result, AgentOutput)
    assert result.content is not None
    assert isinstance(result.content, str)
    # The fallback should return the original invalid response, which is better than nothing
    assert result.content == "Not a valid JSON response"
    assert result.confidence >= 0.5  # Still somewhat confident since we're returning the raw response
    
    logger.info(f"Invalid response handling result: {result.content}")
    
@pytest.mark.asyncio
async def test_format_complex_data(response_formatter_agent):
    """Test formatting a complex data structure."""
    
    # Create a complex nested data structure
    complex_data = {
        "invoices": [
            {
                "id": 1,
                "vendor": "Amazon",
                "amount": 125.99,
                "items": [{"name": "Office Chair", "price": 89.99}, {"name": "Desk Lamp", "price": 36.00}]
            },
            {
                "id": 2,
                "vendor": "Staples",
                "amount": 45.20,
                "items": [{"name": "Paper", "price": 12.99}, {"name": "Pens", "price": 32.21}]
            }
        ],
        "total_spent": 171.19,
        "period": "March 2023",
        "stats": {
            "average_invoice": 85.60,
            "largest_vendor": "Amazon",
            "categories": {
                "Office Supplies": 45.20,
                "Furniture": 125.99
            }
        }
    }
    
    # Convert complex data to a JSON string
    agent_input = AgentInput(
        content=json.dumps(complex_data),
        metadata={
            'format_type': 'summary'
        }
    )
    
    # Process the input
    result = await response_formatter_agent.process(agent_input)
    
    assert isinstance(result, AgentOutput)
    assert result.content is not None
    assert isinstance(result.content, str)
    assert "Amazon" in result.content
    assert "Staples" in result.content
    assert result.status == "success"
    assert result.confidence >= 0.8
    
    logger.info(f"Complex data format result: {result.content}") 