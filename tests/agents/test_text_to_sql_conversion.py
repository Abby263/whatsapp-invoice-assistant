"""
Tests for the TextToSQLConversionAgent.
"""

import pytest
import json
import logging
from typing import Dict, Any

from agents.text_to_sql_conversion_agent import TextToSQLConversionAgent
from services.llm_factory import LLMFactory
from utils.base_agent import AgentInput, AgentContext
from tests.fixtures.test_data import (
    INVOICE_QUERY_INPUTS,
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
def db_schema_info():
    """Create sample database schema information for testing."""
    return """
    Table: invoices
    Columns:
      - id: INTEGER (primary key)
      - user_id: INTEGER (foreign key to users.id)
      - vendor: TEXT 
      - invoice_number: TEXT
      - date: DATE
      - total_amount: NUMERIC(10,2)
      - category: TEXT
      - description: TEXT
      - status: TEXT
      - created_at: TIMESTAMP
      - updated_at: TIMESTAMP
    
    Table: items
      - id: INTEGER (primary key)
      - invoice_id: INTEGER (foreign key to invoices.id)
      - description: TEXT
      - quantity: INTEGER
      - unit_price: NUMERIC(10,2)
      - total_price: NUMERIC(10,2)
    """

@pytest.fixture
def text_to_sql_agent(llm_factory, db_schema_info):
    """Create a TextToSQLConversionAgent instance."""
    agent = TextToSQLConversionAgent(
        llm_factory=llm_factory,
        db_schema_info=db_schema_info
    )
    return agent

def test_init_text_to_sql_agent(llm_factory, db_schema_info):
    """Test initializing the TextToSQLConversionAgent."""
    agent = TextToSQLConversionAgent(
        llm_factory=llm_factory,
        db_schema_info=db_schema_info
    )
    assert agent is not None
    assert isinstance(agent.llm_factory, LLMFactory)
    assert agent.db_schema_info == db_schema_info

@pytest.mark.asyncio
async def test_convert_query_to_sql(text_to_sql_agent):
    """Test converting natural language queries to SQL."""
    # Test with a simple invoice query
    query = "What did I spend at Amazon last month?"
    
    agent_input = AgentInput(
        content=query
    )
    
    context = AgentContext()
    
    # Process the query
    result = await text_to_sql_agent.process(agent_input, context)
    
    # Verify the result
    assert result is not None
    assert result.content is not None
    assert "SELECT" in result.content.upper()
    assert "FROM" in result.content.upper()
    assert result.confidence > 0
    assert "explanation" in result.metadata
    assert result.status == "success"
    
    # Log the result for verification
    logger.info(f"SQL conversion result: {result}")

@pytest.mark.asyncio
async def test_query_with_conversation_history(text_to_sql_agent):
    """Test converting a query with conversation history for context."""
    # Test with a query
    query = "What did I spend at Amazon last month?"
    
    agent_input = AgentInput(
        content=query
    )
    
    # Create context with conversation history
    context = AgentContext(
        conversation_history=SAMPLE_CONVERSATION_HISTORY
    )
    
    # Process the query
    result = await text_to_sql_agent.process(agent_input, context)
    
    # Verify the result
    assert result is not None
    assert result.content is not None
    assert "SELECT" in result.content.upper()
    assert result.status == "success"
    
    # Log the result for verification
    logger.info(f"SQL conversion result with history: {result}")

@pytest.mark.asyncio
async def test_complex_query(text_to_sql_agent):
    """Test a more complex query with filtering and aggregation."""
    # Test with a complex query
    complex_query = "Show me total spending by vendor for Q1, sorted by highest amount"
    
    agent_input = AgentInput(
        content=complex_query
    )
    
    context = AgentContext()
    
    # Process the query
    result = await text_to_sql_agent.process(agent_input, context)
    
    # Verify the result
    assert result is not None
    assert result.content is not None
    assert "SELECT" in result.content.upper()
    assert "FROM" in result.content.upper()
    assert "GROUP BY" in result.content.upper()
    assert "ORDER BY" in result.content.upper()
    assert result.status == "success"
    
    # Log the result for verification
    logger.info(f"Complex query conversion result: {result}")

@pytest.mark.asyncio
async def test_sql_injection_prevention(text_to_sql_agent):
    """Test that the agent handles potential SQL injection attempts safely."""
    # Test with a potentially unsafe query
    injection_query = "Show all invoices; DROP TABLE invoices;"
    
    agent_input = AgentInput(
        content=injection_query
    )
    
    context = AgentContext()
    
    # Process the query
    result = await text_to_sql_agent.process(agent_input, context)
    
    # Verify the result
    assert result is not None
    assert result.content is not None
    # Should not contain dangerous SQL operations
    assert "DROP TABLE" not in result.content.upper()
    assert result.status != "error"
    
    # Log the result for verification
    logger.info(f"SQL injection prevention result: {result}")

@pytest.mark.asyncio
async def test_error_handling(text_to_sql_agent, monkeypatch):
    """Test error handling in the SQL conversion agent."""
    # Patch the convert_text_to_sql method to simulate an error
    async def mock_error(*args, **kwargs):
        raise Exception("Test validation error")
    
    monkeypatch.setattr(text_to_sql_agent.llm_factory, "convert_text_to_sql", mock_error)
    
    query = "What did I spend at Amazon last month?"
    
    agent_input = AgentInput(
        content=query
    )
    
    context = AgentContext()
    
    # Should handle exceptions gracefully
    result = await text_to_sql_agent.process(agent_input, context)
    
    # Verify the result
    assert result is not None
    assert result.content == ""
    assert result.status == "error"
    assert "error" in result.__dict__
    
    # Log the result for verification
    logger.info(f"Error handling result: {result}")

@pytest.mark.asyncio
async def test_invalid_llm_response(text_to_sql_agent, monkeypatch):
    """Test handling invalid LLM responses."""
    # Patch the convert_text_to_sql method to return an invalid response
    async def mock_invalid_response(*args, **kwargs):
        return "Not a valid JSON"
    
    monkeypatch.setattr(text_to_sql_agent.llm_factory, "convert_text_to_sql", mock_invalid_response)
    
    query = "What did I spend at Amazon last month?"
    
    agent_input = AgentInput(
        content=query
    )
    
    context = AgentContext()
    
    # Should handle invalid responses gracefully
    result = await text_to_sql_agent.process(agent_input, context)
    
    # Verify the result
    assert result is not None
    assert result.status == "invalid_sql"
    assert "Failed to parse" in result.metadata.get("explanation", "")
    assert "original_query" in result.metadata
    
    # Log the result for verification
    logger.info(f"Invalid response result: {result}") 