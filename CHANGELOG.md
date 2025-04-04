# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### LLM Factory Implementation
- Created prompt templates for all AI-driven tasks:
  - Text intent classification for determining user intent
  - Text to SQL conversion for database queries
  - Invoice entity extraction from text inputs
  - File validation for uploaded documents
  - Invoice data extraction from document content
  - Response formatting for consistent user experience
- Implemented LLMFactory class for creating and managing LLM instances
  - Template loading and caching system
  - Task-specific configuration
  - Provider-agnostic interface (OpenAI, Anthropic, Cohere)
  - Token usage tracking
- Integrated OpenAI service with GPT-4o-mini
  - Automatic retry logic for API calls
  - Structured entity extraction
  - Classification capabilities
  - Error handling and logging
- Comprehensive test suite for LLM components
  - Mock implementations for testing without API calls
  - Tests for template loading and rendering
  - Tests for different model configurations
  - Tests for error handling and edge cases

## [0.1.0] - 2023-04-04

### Added

- Initial project setup and Phase 1 completion
  
#### Project Setup
- Initial directory structure and project organization
- Poetry configuration for dependency management
- Pre-commit hooks for code quality
- Makefile with commands for common operations
- Docker configuration for development environment
- Environment variable template and example file

#### Configuration System
- Centralized configuration loading from multiple sources
- YAML-based configuration in `config/` directory
- Utility functions for accessing configuration
- Type-safe configuration with Pydantic validators

#### Logging System
- Centralized logging setup with configurable levels
- Structured logging format for better parsing
- Log formatting and handling configuration

#### Database Implementation
- SQLAlchemy ORM models for all entities:
  - User model for managing user accounts
  - Invoice model for invoice metadata
  - Item model for invoice line items
  - Conversation model for chat history
  - Message model for individual messages
  - WhatsAppMessage model for message delivery tracking
  - Media model for file attachments
  - Usage model for token usage tracking
- Pydantic models for validation and serialization
- Database connection management and session utilities
- Error handling for database operations
- Alembic integration for database migrations
- CRUD operations for all entities with a generic base class
- Transaction support and error handling

#### Testing Framework
- Pytest setup with fixtures and configuration
- In-memory SQLite database for testing
- Test cases for database models verifying relationships
- Test cases for CRUD operations
- Migration testing framework
- Test data generation utilities and seed script

### Changed
- Not applicable for initial release

### Fixed
- Not applicable for initial release 