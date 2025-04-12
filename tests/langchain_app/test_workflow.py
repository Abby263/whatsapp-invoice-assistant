"""
Tests for the LangGraph workflow.
"""

import pytest
import os
import json
from unittest.mock import MagicMock, patch
from pathlib import Path

from langchain_app.workflow import process_input, create_workflow_graph, create_workflow
from langchain_app.state import WorkflowState, InputType, IntentType, UserInput
from langchain_app.nodes import (
    input_classifier,
    text_intent_classifier,
    file_validator,
    invoice_entity_extractor,
    data_extractor,
    sql_query_generator,
    response_formatter
)
from tests.fixtures.test_data import (
    GREETING_INPUTS,
    GENERAL_INPUTS,
    INVOICE_QUERY_INPUTS,
    INVOICE_CREATION_INPUTS,
    SAMPLE_CONVERSATION_HISTORY,
    VALID_INVOICE_PATH,
    INVALID_INVOICE_PATH
)

@pytest.fixture
def mock_state_functions():
    """Create mock state functions for the workflow."""
    mock_input_classifier = MagicMock(side_effect=input_classifier)
    mock_text_intent_classifier = MagicMock(side_effect=text_intent_classifier)
    mock_file_validator = MagicMock(side_effect=file_validator)
    mock_invoice_entity_extractor = MagicMock(side_effect=invoice_entity_extractor)
    mock_data_extractor = MagicMock(side_effect=data_extractor)
    mock_sql_query_generator = MagicMock(side_effect=sql_query_generator)
    mock_response_formatter = MagicMock(side_effect=response_formatter)
    
    return {
        "input_classifier": mock_input_classifier,
        "text_intent_classifier": mock_text_intent_classifier,
        "file_validator": mock_file_validator,
        "invoice_entity_extractor": mock_invoice_entity_extractor,
        "data_extractor": mock_data_extractor,
        "sql_query_generator": mock_sql_query_generator,
        "response_formatter": mock_response_formatter
    }

def test_create_workflow_graph():
    """Test creating the workflow graph."""
    graph = create_workflow_graph()
    assert graph is not None
    
    # Check that the graph has the expected nodes
    nodes = graph._graph.nodes
    expected_nodes = [
        "input_classifier",
        "text_intent_classifier",
        "file_validator",
        "invoice_entity_extractor",
        "data_extractor",
        "sql_query_generator",
        "response_formatter"
    ]
    
    for node in expected_nodes:
        assert node in nodes

@patch("langchain_app.workflow.create_workflow")
def test_process_text_input(mock_create_workflow):
    """Test processing text input."""
    # Create a mock workflow that returns a predefined response
    mock_workflow = MagicMock()
    mock_workflow.invoke.return_value = WorkflowState(
        current_response={
            "content": "This is a test response",
            "metadata": {"test": "value"},
            "confidence": 0.95
        },
        processing_complete=True
    )
    mock_create_workflow.return_value = mock_workflow
    
    # Process a text input
    result = process_input(
        input_content="Hello",
        conversation_history=SAMPLE_CONVERSATION_HISTORY
    )
    
    # Check the result
    assert result is not None
    assert "content" in result
    assert result["content"] == "This is a test response"
    assert "metadata" in result
    assert result["metadata"] == {"test": "value"}
    assert "confidence" in result
    assert result["confidence"] == 0.95
    
    # Check that the workflow was called with the expected initial state
    mock_workflow.invoke.assert_called_once()
    initial_state = mock_workflow.invoke.call_args[0][0]
    assert initial_state.user_input.content == "Hello"
    assert initial_state.user_input.content_type == InputType.TEXT

@patch("langchain_app.workflow.create_workflow")
def test_process_file_input(mock_create_workflow):
    """Test processing file input."""
    # Create a mock workflow that returns a predefined response
    mock_workflow = MagicMock()
    mock_workflow.invoke.return_value = WorkflowState(
        current_response={
            "content": "Invoice processed successfully",
            "metadata": {"invoice_id": "123"},
            "confidence": 0.92
        },
        processing_complete=True
    )
    mock_create_workflow.return_value = mock_workflow
    
    # Process a file input
    result = process_input(
        input_content="",
        file_path=str(VALID_INVOICE_PATH),
        file_name="invoice.png",
        mime_type="image/png",
        conversation_history=SAMPLE_CONVERSATION_HISTORY
    )
    
    # Check the result
    assert result is not None
    assert "content" in result
    assert result["content"] == "Invoice processed successfully"
    assert "metadata" in result
    assert result["metadata"] == {"invoice_id": "123"}
    assert "confidence" in result
    assert result["confidence"] == 0.92
    
    # Check that the workflow was called with the expected initial state
    mock_workflow.invoke.assert_called_once()
    initial_state = mock_workflow.invoke.call_args[0][0]
    assert initial_state.user_input.content == ""
    assert initial_state.user_input.content_type == InputType.UNKNOWN
    assert initial_state.user_input.file_path == str(VALID_INVOICE_PATH)
    assert initial_state.user_input.file_name == "invoice.png"
    assert initial_state.user_input.mime_type == "image/png"

@patch("langchain_app.workflow.create_workflow")
def test_error_handling(mock_create_workflow):
    """Test error handling in the workflow."""
    # Create a mock workflow that raises an exception
    mock_workflow = MagicMock()
    mock_workflow.invoke.side_effect = Exception("Test workflow error")
    mock_create_workflow.return_value = mock_workflow
    
    # Process input that will cause an error
    result = process_input(
        input_content="Hello",
        conversation_history=SAMPLE_CONVERSATION_HISTORY
    )
    
    # Check the result
    assert result is not None
    assert "content" in result
    assert "error" in result["metadata"]
    assert "Test workflow error" in result["metadata"]["error"]
    assert result["confidence"] == 0.0

@patch("langchain_app.workflow.create_workflow")
def test_missing_response(mock_create_workflow):
    """Test handling a workflow that doesn't produce a response."""
    # Create a mock workflow that returns a state without a response
    mock_workflow = MagicMock()
    mock_workflow.invoke.return_value = WorkflowState(
        processing_complete=True
    )
    mock_create_workflow.return_value = mock_workflow
    
    # Process input
    result = process_input(
        input_content="Hello",
        conversation_history=SAMPLE_CONVERSATION_HISTORY
    )
    
    # Check the result
    assert result is not None
    assert "content" in result
    assert "I apologize" in result["content"]
    assert result["confidence"] == 0.0

@patch("langchain_app.nodes.text_intent_classifier")
@patch("langchain_app.nodes.response_formatter")
@patch("langchain_app.nodes.input_classifier")
def test_text_greeting_workflow(mock_input_classifier, mock_response_formatter, mock_text_intent_classifier, mock_state_functions):
    """Test the greeting workflow path."""
    # Mock the node functions
    mock_input_classifier.side_effect = lambda state: WorkflowState(
        user_input=UserInput(content="Hello"),
        input_type=InputType.TEXT
    )
    
    mock_text_intent_classifier.side_effect = lambda state: WorkflowState(
        user_input=UserInput(content="Hello"),
        input_type=InputType.TEXT,
        intent=IntentType.GREETING
    )
    
    mock_response_formatter.side_effect = lambda state: WorkflowState(
        user_input=UserInput(content="Hello"),
        input_type=InputType.TEXT,
        intent=IntentType.GREETING,
        current_response={
            "content": "👋 Welcome to InvoiceAgent!",
            "metadata": {},
            "confidence": 0.95
        },
        processing_complete=True
    )
    
    # Create the workflow with patched nodes
    with patch("langchain_app.workflow.input_classifier", mock_input_classifier):
        with patch("langchain_app.workflow.text_intent_classifier", mock_text_intent_classifier):
            with patch("langchain_app.workflow.response_formatter", mock_response_formatter):
                workflow = create_workflow()
                
                # Run the workflow
                result = workflow.invoke(WorkflowState(
                    user_input=UserInput(content="Hello"),
                    conversation_history={"messages": []}
                ))
                
                # Check the result
                assert result is not None
                assert result.current_response is not None
                assert "Welcome" in result.current_response.content
                assert result.processing_complete is True
                
                # Check the node calls
                mock_input_classifier.assert_called_once()
                mock_text_intent_classifier.assert_called_once()
                mock_response_formatter.assert_called_once()

@patch("langchain_app.nodes.file_validator")
@patch("langchain_app.nodes.data_extractor")
@patch("langchain_app.nodes.response_formatter")
@patch("langchain_app.nodes.input_classifier")
def test_valid_invoice_workflow(mock_input_classifier, mock_response_formatter, mock_data_extractor, mock_file_validator, mock_state_functions):
    """Test the valid invoice workflow path."""
    # Mock the node functions
    mock_input_classifier.side_effect = lambda state: WorkflowState(
        user_input=UserInput(content="", file_path=str(VALID_INVOICE_PATH)),
        input_type=InputType.IMAGE
    )
    
    mock_file_validator.side_effect = lambda state: WorkflowState(
        user_input=UserInput(content="", file_path=str(VALID_INVOICE_PATH)),
        input_type=InputType.IMAGE,
        file_validation={"is_valid": True, "confidence": 0.95}
    )
    
    mock_data_extractor.side_effect = lambda state: WorkflowState(
        user_input=UserInput(content="", file_path=str(VALID_INVOICE_PATH)),
        input_type=InputType.IMAGE,
        file_validation={"is_valid": True, "confidence": 0.95},
        extracted_invoice_data={"vendor": "Amazon", "total_amount": 100.00}
    )
    
    mock_response_formatter.side_effect = lambda state: WorkflowState(
        user_input=UserInput(content="", file_path=str(VALID_INVOICE_PATH)),
        input_type=InputType.IMAGE,
        file_validation={"is_valid": True, "confidence": 0.95},
        extracted_invoice_data={"vendor": "Amazon", "total_amount": 100.00},
        current_response={
            "content": "✅ Invoice uploaded and processed successfully!",
            "metadata": {},
            "confidence": 0.95
        },
        processing_complete=True
    )
    
    # Create the workflow with patched nodes
    with patch("langchain_app.workflow.input_classifier", mock_input_classifier):
        with patch("langchain_app.workflow.file_validator", mock_file_validator):
            with patch("langchain_app.workflow.data_extractor", mock_data_extractor):
                with patch("langchain_app.workflow.response_formatter", mock_response_formatter):
                    workflow = create_workflow()
                    
                    # Run the workflow
                    result = workflow.invoke(WorkflowState(
                        user_input=UserInput(content="", file_path=str(VALID_INVOICE_PATH)),
                        conversation_history={"messages": []}
                    ))
                    
                    # Check the result
                    assert result is not None
                    assert result.current_response is not None
                    assert "Invoice uploaded" in result.current_response.content
                    assert result.processing_complete is True
                    
                    # Check the node calls
                    mock_input_classifier.assert_called_once()
                    mock_file_validator.assert_called_once()
                    mock_data_extractor.assert_called_once()
                    mock_response_formatter.assert_called_once() 