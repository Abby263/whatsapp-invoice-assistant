# WhatsApp Invoice Assistant Testing Guide

This guide provides comprehensive information on how to test the WhatsApp Invoice Assistant application, including running existing tests, creating new tests, and using the interactive testing mode.

## Table of Contents

1. [Testing Overview](#testing-overview)
2. [Test Directory Structure](#test-directory-structure)
3. [Running Tests](#running-tests)
4. [Interactive Testing](#interactive-testing)
5. [Creating New Tests](#creating-new-tests)
6. [Troubleshooting](#troubleshooting)

## Testing Overview

The WhatsApp Invoice Assistant uses pytest as its primary testing framework. Tests are organized by component type (agents, services, database, etc.) and follow standard pytest conventions.

The test suite includes:
- Unit tests for individual components
- Integration tests for component interactions
- End-to-end tests for complete workflows

## Test Directory Structure

```
tests/
├── __init__.py
├── agents/                     # Tests for all agent components
│   ├── test_entity_extraction.py
│   ├── test_file_validator.py
│   ├── test_text_intent_classifier.py
│   ├── test_text_to_sql_conversion.py
│   ├── test_response_formatter.py
│   └── test_data_extractor.py
├── services/                   # Tests for service components
│   ├── test_llm_factory.py
│   └── ...
├── database/                   # Tests for database operations
│   ├── test_models.py
│   ├── test_migrations.py
│   └── ...
├── langchain_app/              # Tests for LangGraph workflows
│   ├── test_workflow.py
│   └── ...
├── fixtures/                   # Shared test fixtures
│   ├── test_data.py            # Sample test data
│   └── prompts/                # Test prompts
└── test_runner.py              # CLI tool for running tests
```

## Running Tests

### Using Makefile Commands

The simplest way to run tests is using the provided Make commands:

```bash
# Run all tests
make test

# Run database-specific tests
make test-db
```

### Using the Test Runner

For more flexibility, use the `test_runner.py` script:

```bash
# Run all tests
python tests/test_runner.py --all

# Run tests for a specific agent (e.g., entity extraction)
python tests/test_runner.py --agent entity

# Run tests for a specific service
python tests/test_runner.py --service llm_factory

# Run a specific test file or function
python tests/test_runner.py --specific tests/agents/test_entity_extraction.py
python tests/test_runner.py --specific tests/agents/test_entity_extraction.py::test_extract_invoice_entities

# Check test status
python tests/test_runner.py --status
```

### Using pytest Directly

You can also use pytest commands directly for more control:

```bash
# Run all tests
python -m pytest tests/

# Run a specific test file
python -m pytest tests/agents/test_entity_extraction.py

# Run a specific test function
python -m pytest tests/agents/test_entity_extraction.py::test_extract_invoice_entities

# Run tests with extra verbosity
python -m pytest -v tests/

# Run tests and stop on first failure
python -m pytest -x tests/
```

### Expected Test Results

When tests run successfully, you'll see output like this:

```
==================== TEST SESSION STARTS ====================
...
collected 42 items

tests/agents/test_entity_extraction.py::test_init_invoice_extraction_agent PASSED
tests/agents/test_entity_extraction.py::test_extract_invoice_entities PASSED
...

==================== 42 passed in 10.34s ====================
```

If there are failures, you'll see details about what failed and why:

```
==================== FAILURES ====================
__________________ test_extract_invoice_entities __________________

...
>       assert "vendor" in extracted_entities
E       AssertionError: assert 'vendor' in {}

tests/agents/test_entity_extraction.py:52: AssertionError
```

## Interactive Testing

The WhatsApp Invoice Assistant includes an interactive testing mode that allows you to test individual agents with custom queries without writing formal tests.

### Starting Interactive Mode

```bash
python tests/test_runner.py --interactive
```

This will start a command-line interface where you can interact with the agents:

```
==================================================
WhatsApp Invoice Assistant - Interactive Testing Console
==================================================
Type 'help' for available commands, 'exit' to quit.
==================================================

>
```

### Available Commands

- `help` - Show available commands
- `agents` - List available agent instances
- `test <agent> <query>` - Test a specific agent with a text query
- `file <agent> <path>` - Test a file-based agent with a file input
- `history` - Show conversation history
- `clear` - Clear conversation history
- `exit` - Exit the console

### Example Usage

```
> agents

Available agents:
  intent - TextIntentClassifierAgent
  entity - InvoiceEntityExtractionAgent
  sql - TextToSQLConversionAgent
  format - ResponseFormatterAgent
  validator - FileValidatorAgent
  extractor - DataExtractorAgent

> test intent What did I spend at Amazon last month?

==================================================
AGENT: intent
STATUS: success
CONFIDENCE: 0.95
--------------------------------------------------
CONTENT:
invoice_query
--------------------------------------------------
METADATA:
{
  "explanation": "This query is asking about spending at Amazon, which is an invoice-related query that likely requires database lookup.",
  "confidence_scores": {
    "greeting": 0.01,
    "general": 0.02,
    "invoice_query": 0.95,
    "invoice_creation": 0.02
  }
}
==================================================

> test entity Create an invoice for $100 from Amazon on March 5

==================================================
AGENT: entity
STATUS: success
CONFIDENCE: 0.85
--------------------------------------------------
CONTENT:
{
  "vendor": "Amazon",
  "invoice_date": "2023-03-05",
  "total_amount": 100.0,
  "currency": "USD",
  "items": []
}
--------------------------------------------------
METADATA:
{
  "original_text": "Create an invoice for $100 from Amazon on March 5",
  "raw_extraction_result": "..."
}
==================================================
```

## Creating New Tests

### Test Structure

Each test file should follow this basic structure:

```python
"""
Tests for the ComponentName.
"""

import pytest
from your_component import YourComponent

@pytest.fixture
def component_instance():
    """Create a component instance for testing."""
    return YourComponent()

def test_component_initialization(component_instance):
    """Test component initialization."""
    assert component_instance is not None
    # More assertions...

@pytest.mark.asyncio  # For async functions
async def test_component_functionality(component_instance):
    """Test component functionality."""
    result = await component_instance.some_method()
    assert result is not None
    # More assertions...
```

### Using Test Fixtures

Common test data is available in `tests/fixtures/test_data.py`:

```python
from tests.fixtures.test_data import (
    SAMPLE_INVOICE_DATA,
    INVOICE_QUERY_INPUTS,
    SAMPLE_CONVERSATION_HISTORY
)
```

### Testing Asynchronous Code

For asynchronous functions, use the `@pytest.mark.asyncio` decorator:

```python
@pytest.mark.asyncio
async def test_async_function():
    result = await your_async_function()
    assert result is not None
```

## Troubleshooting

### Common Test Failures

1. **JSON parsing errors**:
   - Check if the agent can handle different response formats
   - Verify that the LLM response parser can handle triple backticks

2. **LLM response failures**:
   - Verify that environment variables are set correctly
   - Check prompt templates for errors

3. **Missing data errors**:
   - Ensure all required test fixtures are properly imported
   - Check if test data has all required fields

### Debugging Tips

1. Use the `-v` or `-vv` flags for more verbose output:
   ```bash
   python -m pytest -vv tests/agents/test_entity_extraction.py
   ```

2. Add print statements or logging within tests:
   ```python
   import logging
   logger = logging.getLogger(__name__)
   logger.info(f"Test result: {result}")
   ```

3. Use the interactive testing mode to debug agent behavior directly:
   ```bash
   python tests/test_runner.py --interactive
   ```

4. Check that prompts are loading correctly:
   ```bash
   # From interactive mode
   > test intent -debug What did I spend at Amazon?
   ```

5. Inspect agent output:
   ```python
   print(f"Agent output: {json.dumps(result.content, indent=2)}")
   ```

### Best Practices

1. **Test Isolation**: Each test should run independently
2. **Mock External Services**: Use pytest's monkeypatch for external dependencies
3. **Use Fixtures**: Share setup code using pytest fixtures
4. **Clear Assertions**: Make assertions specific and descriptive
5. **Test Edge Cases**: Include tests for error conditions and edge cases 