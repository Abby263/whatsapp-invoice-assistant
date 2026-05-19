# WhatsApp Invoice Assistant Testing Guide

This document provides an overview of the automated testing approach for the WhatsApp Invoice Assistant.

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
python -m pytest tests/workflows/   # Test workflow components
```

To run tests with verbose output:

```bash
python -m pytest tests/ -v
```
