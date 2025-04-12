# WhatsApp Invoice Assistant Testing Guide

This document provides an overview of the testing approaches for the WhatsApp Invoice Assistant, including both automated tests and interactive testing modes.

## Automated Tests

The WhatsApp Invoice Assistant includes several types of automated tests:

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test interactions between components
- **End-to-End Tests**: Test complete user flows

### Running Automated Tests

To run all tests:

```bash
python -m pytest tests/
```

To run specific test categories:

```bash
python -m pytest tests/agents/      # Test agent components
python -m pytest tests/workflow/    # Test workflow components
python -m pytest tests/memory/      # Test memory components
```

To run tests with verbose output:

```bash
python -m pytest tests/ -v
```

## Interactive Testing

For manual testing and exploration of the system's behavior, we provide an interactive test script.

### Running the Interactive Test

To start the interactive test:

```bash
python -m tests.interactive_test
```

This will launch an interactive console where you can input messages and commands to test the WhatsApp Invoice Assistant.

### Available Commands

- `/exit` - Exit the interactive test
- `/file <path>` - Process a file at the given path
- `/graph` - Save the current workflow graph visualization
- `/help` - Display help information

### Example Session

```
===== WhatsApp Invoice Assistant Interactive Test =====
Type /help for available commands
Type your message or command below:

You: Hello

Processing your message... 