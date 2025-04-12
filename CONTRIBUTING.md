# Contributing to WhatsApp Invoice Assistant

Thank you for your interest in contributing to the WhatsApp Invoice Assistant! This document provides guidelines and instructions for contributing to this project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Submitting Changes](#submitting-changes)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Documentation](#documentation)
- [Issue Reporting](#issue-reporting)
- [Feature Requests](#feature-requests)
- [Pull Requests](#pull-requests)
- [Review Process](#review-process)

## Code of Conduct

By participating in this project, you are expected to uphold our Code of Conduct, which is to:

- Use welcoming and inclusive language
- Be respectful of differing viewpoints and experiences
- Gracefully accept constructive criticism
- Focus on what is best for the community
- Show empathy towards other community members

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork**:
   ```bash
   git clone https://github.com/your-username/whatsapp-invoice-assistant.git
   cd whatsapp-invoice-assistant
   ```
3. **Set up the development environment**:
   ```bash
   make install
   ```
4. **Set up the databases**:
   ```bash
   make db-migrate
   ```
5. **Create a branch** for your work:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Workflow

1. Make your changes in small, incremental commits
2. Follow the [Coding Standards](#coding-standards)
3. Add tests for your changes
4. Ensure all tests pass with `make test`
5. Update documentation if necessary
6. Run linting with `make lint`

## Submitting Changes

1. Push your changes to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```
2. Create a Pull Request against the `main` branch

## Coding Standards

- Follow PEP 8 style guide for Python code
- Use type hints for all function parameters and return values
- Add docstrings to all functions and classes
- Follow the project's existing coding style
- Use descriptive variable names
- Limit line length to 88 characters

We use automated tools to enforce these standards:
- `black` for code formatting
- `flake8` for linting
- `mypy` for type checking

Run `make format` to automatically format your code.

## Testing

- Write tests for all new features and bug fixes
- Ensure all tests pass before submitting a Pull Request
- Run the test suite with `make test`
- For testing specific components:
  - `make test-db` for database tests
  - `make test-sql` for SQL generation tests
  - `make ui-test` for UI tests

## Documentation

- Update the README.md if your changes affect the user-facing functionality
- Add or update documentation in the `docs/` directory
- Document all new public functions, classes, and modules
- Keep the documentation up to date with code changes

## Issue Reporting

When reporting an issue:

1. Use the issue templates provided
2. Clearly describe the problem
3. Include steps to reproduce
4. Include expected vs. actual behavior
5. Include relevant system information
6. Include log files or screenshots if applicable

## Feature Requests

When requesting a feature:

1. Use the feature request template
2. Clearly describe the feature and its benefits
3. Provide use cases for the feature
4. Indicate if you're willing to contribute the implementation

## Pull Requests

When submitting a Pull Request:

1. Use the PR template
2. Link to any related issues
3. Describe the changes you've made
4. Include screenshots for UI changes
5. Update relevant documentation
6. Ensure all tests pass
7. Address any review feedback promptly

## Review Process

The review process for Pull Requests:

1. At least one maintainer must review and approve all changes
2. Automated checks must pass (tests, linting, etc.)
3. Changes may require revisions before being accepted
4. Large changes may require multiple reviews

## License

By contributing to this project, you agree that your contributions will be licensed under the project's license. 