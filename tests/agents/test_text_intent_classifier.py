"""
Tests for the TextIntentClassifierAgent.
"""

import pytest
import os
import json
from pathlib import Path

from agents.text_intent_classifier import TextIntentClassifierAgent
from services.llm_factory import LLMFactory
from langchain_app.state import IntentType
from utils.base_agent import AgentInput, AgentContext
from tests.fixtures.test_data import (
    GREETING_INPUTS,
    GENERAL_INPUTS,
    INVOICE_QUERY_INPUTS,
    INVOICE_CREATION_INPUTS,
    SAMPLE_CONVERSATION_HISTORY
)

@pytest.fixture
def llm_factory():
    """Create a real LLM factory instance for testing."""
    factory = LLMFactory()
    return factory

@pytest.fixture
def text_intent_classifier(llm_factory):
    """Create a TextIntentClassifierAgent instance."""
    agent = TextIntentClassifierAgent(llm_factory=llm_factory)
    return agent

def test_init_text_intent_classifier(llm_factory):
    """Test initializing the TextIntentClassifierAgent."""
    agent = TextIntentClassifierAgent(llm_factory=llm_factory)
    assert agent is not None
    assert isinstance(agent.llm_factory, LLMFactory)

@pytest.mark.asyncio
async def test_process_input_greeting(text_intent_classifier):
    """Test processing greeting input text."""
    # Test with greeting input
    input_text = GREETING_INPUTS[0]  # "Hi"
    agent_input = AgentInput(content=input_text)
    context = AgentContext(conversation_history=[])
    
    result = await text_intent_classifier.process(agent_input, context)
    
    assert result is not None
    assert result.content == IntentType.GREETING
    assert result.confidence > 0.7
    assert "explanation" in result.metadata
    
    # Log the result for verification
    print(f"Greeting classification result: {result}")

@pytest.mark.asyncio
async def test_process_input_general(text_intent_classifier):
    """Test processing general input text."""
    # Test with general input
    input_text = GENERAL_INPUTS[0]  # "What's the weather like today?"
    agent_input = AgentInput(content=input_text)
    context = AgentContext(conversation_history=[])
    
    result = await text_intent_classifier.process(agent_input, context)
    
    assert result is not None
    assert result.content == IntentType.GENERAL
    assert result.confidence > 0.7
    assert "explanation" in result.metadata
    
    # Log the result for verification
    print(f"General query classification result: {result}")

@pytest.mark.asyncio
async def test_process_input_invoice_query(text_intent_classifier):
    """Test processing invoice query input text."""
    # Test with invoice query input
    input_text = INVOICE_QUERY_INPUTS[0]  # "What did I spend at Amazon last month?"
    agent_input = AgentInput(content=input_text)
    context = AgentContext(conversation_history=[])
    
    result = await text_intent_classifier.process(agent_input, context)
    
    assert result is not None
    assert result.content == IntentType.INVOICE_QUERY
    assert result.confidence > 0.7
    assert "explanation" in result.metadata
    
    # Log the result for verification
    print(f"Invoice query classification result: {result}")

@pytest.mark.asyncio
async def test_process_input_invoice_creator(text_intent_classifier):
    """Test processing invoice creator input text."""
    # Test with invoice creator input
    input_text = INVOICE_CREATION_INPUTS[0]  # "Create an invoice for $100 from Amazon on March 5"
    agent_input = AgentInput(content=input_text)
    context = AgentContext(conversation_history=[])
    
    result = await text_intent_classifier.process(agent_input, context)
    
    assert result is not None
    assert result.content == IntentType.INVOICE_CREATOR
    assert result.confidence > 0.7
    assert "explanation" in result.metadata
    
    # Log the result for verification
    print(f"Invoice creator classification result: {result}")

@pytest.mark.asyncio
async def test_process_with_conversation_history(text_intent_classifier):
    """Test processing input with conversation history."""
    # Test with a query and conversation history
    input_text = "What did I spend at Amazon last month?"
    agent_input = AgentInput(content=input_text)
    context = AgentContext(conversation_history=SAMPLE_CONVERSATION_HISTORY)
    
    result = await text_intent_classifier.process(agent_input, context)
    
    assert result is not None
    assert result.content == IntentType.INVOICE_QUERY
    assert result.confidence > 0.7
    
    # Log the result for verification
    print(f"Conversation history test result: {result}")

@pytest.mark.asyncio
async def test_error_handling(llm_factory, monkeypatch):
    """Test error handling in the classifier."""
    agent = TextIntentClassifierAgent(llm_factory=llm_factory)
    
    # Patch the classify_text_intent method to simulate an error
    async def mock_error(*args, **kwargs):
        raise Exception("Test error")
    
    monkeypatch.setattr(llm_factory, "classify_text_intent", mock_error)
    
    # Should handle exceptions gracefully
    agent_input = AgentInput(content="Hello")
    context = AgentContext(conversation_history=[])
    result = await agent.process(agent_input, context)
    
    assert result is not None
    assert result.content == IntentType.UNKNOWN
    assert result.confidence == 0.0
    assert result.status == "error"
    assert "Test error" in result.error

@pytest.mark.asyncio
async def test_invalid_llm_response(llm_factory, monkeypatch):
    """Test handling invalid LLM responses."""
    agent = TextIntentClassifierAgent(llm_factory=llm_factory)
    
    # Patch the classify_text_intent method to return an invalid response
    async def mock_invalid_response(*args, **kwargs):
        return "Not a valid JSON"
    
    monkeypatch.setattr(llm_factory, "classify_text_intent", mock_invalid_response)
    
    # Should handle invalid responses gracefully
    agent_input = AgentInput(content="Hello")
    context = AgentContext(conversation_history=[])
    result = await agent.process(agent_input, context)
    
    assert result is not None
    assert result.content == IntentType.UNKNOWN
    assert result.confidence <= 0.1
    assert "Could not parse" in result.metadata.get("explanation", "") 