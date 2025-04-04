# WhatsApp Invoice Assistant: Implementation Tasks

## Overview
This document outlines the sequential tasks required to build the WhatsApp Invoice Assistant, an AI-powered bot for processing and managing invoice data through WhatsApp. The implementation follows the architecture defined in the provided documentation, using FastAPI, PostgreSQL, LangGraph, and GPT-4o-mini.

## Phase 1: Project Setup and Configuration

### 1. Environment and Project Structure Setup
- [x] Create project directory structure as defined in TECH_STACK.md
- [x] Set up Poetry for dependency management 
- [x] Create initial pyproject.toml file with required dependencies
- [x] Set up pre-commit hooks for code quality (black, flake8, mypy)
- [x] Create Makefile with basic commands (start, stop, restart, db-clean)
- [x] Configure Docker and docker-compose.yml for local development
- [x] Create a .env.example file with required environment variables
- [x] **Test:** Verify project structure by running `make lint` to ensure code quality tools are working

### 2. Configuration Management
- [x] Create config/env.yaml for environment variable management
- [x] Implement configuration loading utilities in utils/
- [x] Set up centralized logging in utils/logging.py
- [x] **Test:** Write unit tests for config loader to verify environment variable loading
- [x] **Test:** Verify logging configuration by testing different log levels

### 3. Database Setup
- [x] Create PostgreSQL database models using SQLAlchemy in database/schemas.py
  - [x] Users table (id, whatsapp_number, name, email, etc.)
  - [x] Invoices table (id, user_id, invoice_number, invoice_date, vendor, etc.)
  - [x] Items table (id, invoice_id, description, quantity, unit_price, etc.)
  - [x] Conversations table (id, user_id, created_at, updated_at)
  - [x] Messages table (id, user_id, conversation_id, content, role, etc.)
  - [x] WhatsAppMessages table (id, message_id, whatsapp_message_id, status, etc.)
  - [x] Media table (id, user_id, invoice_id, filename, file_path, etc.)
  - [x] Usage table (id, user_id, tokens_in, tokens_out, cost, etc.)
- [x] Implement Pydantic models for validation in database/models.py
- [x] Set up database connection utilities in database/connection.py
- [x] Create Alembic migrations for initial schema
- [x] Implement CRUD operations in database/crud.py
  - [x] User CRUD operations
  - [x] Invoice CRUD operations
  - [x] Conversation and Message CRUD operations
  - [x] Media file CRUD operations
- [x] **Test:** Write unit tests for database models to verify relationships and constraints
- [x] **Test:** Create database test fixtures for integration testing
- [x] **Test:** Verify CRUD operations by writing unit tests for each operation
- [x] **Test:** Run database migrations in a test environment to ensure they apply correctly

### Phase 1 Code Standards Check
- [x] Run code formatting with Black on all implemented modules
- [x] Run Flake8 to ensure PEP 8 compliance
- [x] Run MyPy to verify type annotations
- [x] Verify docstrings are present and follow project standards
- [x] Ensure test coverage of Phase 1 components is at least 80%
- [x] Review imported dependencies for security vulnerabilities
- [x] Verify no hardcoded credentials or secrets in code

### Phase 1 Documentation Updates
- [x] Update README.md with Phase 1 setup instructions
  - [x] Database setup and migration instructions
  - [x] Configuration management details
  - [x] Local development setup steps
- [x] Update Makefile with Phase 1 specific commands
  - [x] Database migration commands
  - [x] Test commands for database components
- [x] Update CHANGELOG.md with Phase 1 changes
  - [x] Database schema implementation details
  - [x] Configuration system implementation
  - [x] Testing framework setup

## Phase 2: Core Components Implementation

### 4. LLM Factory Implementation
- [ ] Create prompts/ directory with separate files for each prompt type
  - [ ] text_intent_classification_prompt.txt
  - [ ] text_to_sql_conversion_prompt.txt
  - [ ] invoice_entity_extraction_prompt.txt
  - [ ] file_validation_prompt.txt
  - [ ] invoice_data_extraction_prompt.txt
  - [ ] response_formatting_prompt.txt
- [ ] Implement LLMFactory class in services/llm_factory.py
  - [ ] Configure model name, temperature, and other parameters
  - [ ] Add methods for loading prompts from files
  - [ ] Implement caching for prompt templates
- [ ] Configure GPT-4o-mini integration in services/openai_service.py
- [ ] **Test:** Create mock LLM responses for testing without API calls
- [ ] **Test:** Write unit tests for prompt loading and template rendering
- [ ] **Test:** Test LLMFactory with different configurations
- [ ] **Test:** Verify OpenAI service integration with mock responses

### 5. Router and Agent Implementation
- [ ] Create BaseAgent class in utils/base_agent.py to ensure standardized agent interfaces
- [ ] Implement InputTypeRouter in utils/input_type_router.py for determining input type (text vs file)
- [ ] Implement text_intent_classifier.py agent
  - [ ] Integration with LLM for intent classification
  - [ ] Memory integration for context retention
  - [ ] Support for Greeting, General, InvoiceQuery, and InvoiceCreator intents
- [ ] **Test:** Write unit tests for the text_intent_classifier with sample inputs
- [ ] **Test:** Test classification accuracy with various input types
- [ ] Implement file_validator.py agent
  - [ ] File type validation (image, PDF, Excel, CSV)
  - [ ] Integration with LLM to check if the file is a valid invoice
  - [ ] Router capability to direct to appropriate processing path
- [ ] **Test:** Create test fixtures with sample invoice files and non-invoice files
- [ ] **Test:** Verify file validator correctly identifies valid invoices
- [ ] Implement text_to_sql_conversion_agent.py for InvoiceQuery intents
- [ ] **Test:** Test SQL conversion with various query types
- [ ] **Test:** Verify SQL injection protection
- [ ] Implement invoice_entity_extraction_agent.py for InvoiceCreator intents
- [ ] **Test:** Test entity extraction with various input formats
- [ ] Implement data_extractor.py agent for file processing
  - [ ] Integration with GPT-4o-mini for data extraction
  - [ ] Extraction of invoice details (vendor, date, amount, items)
  - [ ] Mapping extracted data to database schema
- [ ] **Test:** Test data extraction with sample invoice images
- [ ] **Test:** Verify extraction accuracy against known values
- [ ] Implement response_formatter.py agent
  - [ ] Format responses using templates
  - [ ] Add disclaimers and structure to all responses
  - [ ] Handle different response types (text, files, templates)
- [ ] **Test:** Verify response formatting with different template types
- [ ] **Test:** Test edge cases like empty responses or error conditions

### 6. Memory and Context Management
- [ ] Implement langgraph_memory.py for stateful conversations
  - [ ] Storage for conversation history
  - [ ] Context retention between user interactions
  - [ ] Memory clearing/expiration mechanisms
- [ ] Create context_manager.py to maintain conversation history
  - [ ] Integration with database for persistence
  - [ ] Support for retrieving past conversations
- [ ] **Test:** Create test fixtures with sample conversation histories
- [ ] **Test:** Test memory retrieval and context maintenance
- [ ] **Test:** Verify memory expiration works as expected
- [ ] **Test:** Test context manager with database integration

### 7. Workflow Implementation
- [ ] Create base_workflow.py with shared workflow logic
- [ ] Implement main_workflow.py for orchestrating the entire flow
  - [ ] Input type determination (text vs file)
  - [ ] Routing based on input type and intent
- [ ] **Test:** Test main workflow routing with different input types
- [ ] Implement text_processing_workflow.py for handling text inputs
  - [ ] Intent classification routing
  - [ ] Processing for different intents
- [ ] **Test:** Test text processing workflow with different intents
- [ ] Implement invoice_query_workflow.py
  - [ ] Text-to-SQL conversion
  - [ ] Database query execution
  - [ ] Result formatting
- [ ] **Test:** Test invoice query workflow with sample queries
- [ ] **Test:** Verify database query execution and result formatting
- [ ] Implement invoice_creator_workflow.py
  - [ ] Entity extraction
  - [ ] Template population
  - [ ] PDF generation
- [ ] **Test:** Test invoice creation workflow with sample data
- [ ] **Test:** Verify PDF generation works correctly
- [ ] Implement general_response_workflow.py for Greeting and General intents
- [ ] **Test:** Test general response workflow with greeting and general queries
- [ ] Implement file_processing_workflow.py
  - [ ] File validation
  - [ ] Handling valid invoices
  - [ ] Handling invalid files
  - [ ] Handling unsupported formats
- [ ] **Test:** Test file processing workflow with various file types
- [ ] **Test:** Verify proper handling of valid and invalid files
- [ ] **Test:** End-to-end test of entire workflow with sample inputs

### Phase 2 Code Standards Check
- [ ] Run code formatting with Black on all implemented modules
- [ ] Run Flake8 to ensure PEP 8 compliance
- [ ] Run MyPy to verify type annotations with focus on agent interfaces
- [ ] Verify consistent error handling patterns across all agents
- [ ] Check for proper dependency injection in agent implementations
- [ ] Review prompt templates for consistency and standards
- [ ] Verify test coverage of Phase 2 components is at least 80%
- [ ] Check for proper exception handling and logging
- [ ] Review agent interfaces for consistency

### Phase 2 Documentation Updates
- [ ] Update README.md with Phase 2 implementation details
  - [ ] LLM integration instructions
  - [ ] Agent system architecture overview
  - [ ] Workflow implementation details
- [ ] Update Makefile with Phase 2 specific commands
  - [ ] Commands for running specific workflows
  - [ ] Commands for testing agents independently
- [ ] Update CHANGELOG.md with Phase 2 changes
  - [ ] LLM Factory implementation details
  - [ ] Agent and router implementation
  - [ ] Workflow architecture details

## Phase 3: External Services Integration

### 8. WhatsApp Integration
- [ ] Set up Twilio account and WhatsApp sandbox
- [ ] Implement twilio_service.py for WhatsApp messaging
  - [ ] Message sending functionality
  - [ ] File handling (receive and send)
  - [ ] Status tracking
- [ ] Create webhook endpoint in api/routes/whatsapp.py
  - [ ] Message parsing
  - [ ] File extraction and processing
  - [ ] Integration with main workflow
- [ ] **Test:** Create mock Twilio service for testing webhook
- [ ] **Test:** Test webhook endpoint with sample requests
- [ ] **Test:** Verify file handling in webhook
- [ ] **Test:** Integration test of webhook with main workflow

### 9. Storage Implementation
- [ ] Set up AWS S3 bucket for file storage
- [ ] Implement s3_handler.py for file uploads and retrievals
  - [ ] File upload functionality
  - [ ] URL generation for stored files
  - [ ] File retrieval for processing
- [ ] **Test:** Create mock S3 service for testing uploads and retrievals
- [ ] **Test:** Test file upload and URL generation
- [ ] **Test:** Verify file retrieval works as expected

### 10. Task Queue Setup
- [ ] Configure Redis as message broker
- [ ] Set up Celery for asynchronous task processing
- [ ] Implement tasks/celery_app.py for Celery configuration
- [ ] Implement tasks/image_processing.py for asynchronous file processing
  - [ ] Image preprocessing
  - [ ] OCR and data extraction
  - [ ] Database storage
- [ ] **Test:** Create test fixtures for Celery tasks
- [ ] **Test:** Test async processing with sample images
- [ ] **Test:** Verify task queue handles errors correctly
- [ ] **Test:** Test integration between Celery tasks and database

### Phase 3 Code Standards Check
- [ ] Run code formatting with Black on all implemented modules
- [ ] Run Flake8 to ensure PEP 8 compliance
- [ ] Run MyPy to verify type annotations
- [ ] Check for proper error handling in external service integrations
- [ ] Review security of API keys and external service credentials
- [ ] Verify exception handling for network failures and service outages
- [ ] Ensure test coverage of Phase 3 components is at least 80%
- [ ] Review retry mechanisms for external service calls
- [ ] Check for proper timeouts on external service calls

### Phase 3 Documentation Updates
- [ ] Update README.md with Phase 3 integration details
  - [ ] WhatsApp/Twilio setup instructions
  - [ ] S3 bucket configuration guide
  - [ ] Async task processing system overview
- [ ] Update Makefile with Phase 3 specific commands
  - [ ] Commands for starting worker processes
  - [ ] Commands for monitoring task queues
- [ ] Update CHANGELOG.md with Phase 3 changes
  - [ ] External service integration details
  - [ ] Asynchronous processing implementation
  - [ ] File storage system details

## Phase 4: Response Templates and Formatting

### 11. Template Implementation
- [ ] Create response templates in templates/ directory
- [ ] Implement general_response_template.jinja
  - [ ] Welcome message
  - [ ] Bot capabilities
  - [ ] Example queries
  - [ ] Disclaimers
- [ ] Implement greeting_response_template.jinja
- [ ] Implement default_invoice_template.jinja for PDF generation
- [ ] Implement invoice_query_result_template.jinja
- [ ] Implement invalid_file_template.jinja
- [ ] Implement unsupported_format_template.jinja
- [ ] Set up PDF generation utilities in utils/pdf_generator.py
- [ ] **Test:** Test template rendering with sample data
- [ ] **Test:** Verify PDF generation with the invoice template
- [ ] **Test:** Test response formatting with all templates
- [ ] **Test:** Verify templates handle edge cases (missing data, long text)

### 12. Constant Definitions
- [ ] Define fallback messages in constants/fallback_messages.py
  - [ ] Invalid invoice messages
  - [ ] Unsupported format messages
  - [ ] General error messages
- [ ] Configure LLM settings in constants/llm_configs.py
- [ ] Define agent configurations in constants/agent_configs.py
- [ ] Define workflow configurations in constants/workflow_configs.py
- [ ] Define intent types in constants/intent_types.py
- [ ] Define file types in constants/file_types.py
- [ ] **Test:** Verify constants are loaded correctly
- [ ] **Test:** Test integration of constants with agents and workflows

### Phase 4 Code Standards Check
- [ ] Run code formatting with Black on all implemented modules
- [ ] Run Flake8 to ensure PEP 8 compliance
- [ ] Run MyPy to verify type annotations
- [ ] Check template files for consistent formatting and naming
- [ ] Verify constants follow naming conventions
- [ ] Review message formatting for localization readiness
- [ ] Ensure test coverage of Phase 4 components is at least 80%
- [ ] Check for hardcoded strings that should be constants

### Phase 4 Documentation Updates
- [ ] Update README.md with Phase 4 templates and formatting details
  - [ ] Template system overview
  - [ ] Response formatting guidelines
  - [ ] PDF generation instructions
- [ ] Update Makefile with Phase 4 specific commands
  - [ ] Commands for testing template rendering
  - [ ] Commands for generating sample responses
- [ ] Update CHANGELOG.md with Phase 4 changes
  - [ ] Template system implementation
  - [ ] Response formatting standardization
  - [ ] PDF generation capabilities

## Phase 5: API and Main Application

### 13. FastAPI Implementation
- [ ] Create main.py with FastAPI application setup
- [ ] Implement dependency injection in api/dependencies.py
  - [ ] Database session dependency
  - [ ] Workflow dependency
  - [ ] Services dependencies
- [ ] Create health check endpoint in api/routes/health.py
- [ ] Create api/routes/whatsapp.py for webhook handling
- [ ] Set up error handling middleware in api/middleware.py
- [ ] Configure CORS and security headers
- [ ] **Test:** Write unit tests for API endpoints
- [ ] **Test:** Test API with sample requests
- [ ] **Test:** Verify dependency injection works correctly
- [ ] **Test:** Test error handling middleware

### 14. Webhook Processing
- [ ] Implement file type detection logic in utils/file_utils.py
- [ ] Set up input_router.py for initial routing
- [ ] Create response handling and formatting pipeline
- [ ] Implement webhook verification for Twilio
- [ ] **Test:** Test file type detection with various file types
- [ ] **Test:** Verify webhook verification logic
- [ ] **Test:** Test end-to-end webhook processing flow

### Phase 5 Code Standards Check
- [ ] Run code formatting with Black on all implemented modules
- [ ] Run Flake8 to ensure PEP 8 compliance
- [ ] Run MyPy to verify type annotations
- [ ] Review API endpoint documentation
- [ ] Check for proper error response formatting
- [ ] Verify security headers and CORS configuration
- [ ] Ensure test coverage of Phase 5 components is at least 80%
- [ ] Review request validation and sanitization
- [ ] Check for proper logging of API requests and responses

### Phase 5 Documentation Updates
- [ ] Update README.md with Phase 5 API and application details
  - [ ] API endpoints documentation
  - [ ] Webhook handling instructions
  - [ ] Application deployment guide
- [ ] Update Makefile with Phase 5 specific commands
  - [ ] Commands for starting the API server
  - [ ] Commands for testing API endpoints
- [ ] Update CHANGELOG.md with Phase 5 changes
  - [ ] API implementation details
  - [ ] Webhook processing system
  - [ ] Application architecture overview

## Phase 6: Testing and Deployment

### 15. Comprehensive Test Implementation
- [ ] Create end-to-end test suite covering all flows
  - [ ] Test greeting flow
  - [ ] Test general query flow
  - [ ] Test invoice query flow
  - [ ] Test invoice creation flow
  - [ ] Test valid invoice upload flow
  - [ ] Test invalid file upload flow
  - [ ] Test unsupported format flow
- [ ] Implement load testing for high concurrency
- [ ] Create automation for regression testing
- [ ] Set up continuous integration testing pipelines

### 16. Containerization and Deployment
- [ ] Finalize Dockerfile for production
- [ ] Create Kubernetes manifests for deployment
  - [ ] Deployment configuration
  - [ ] Service configuration
  - [ ] Ingress configuration
  - [ ] ConfigMap and Secret management
- [ ] Set up CI/CD pipeline with GitHub Actions/GitLab CI
- [ ] Configure logging and monitoring for production
- [ ] **Test:** Verify Docker builds successfully
- [ ] **Test:** Test Kubernetes deployment in staging environment
- [ ] **Test:** Perform load testing in production-like environment

### Phase 6 Code Standards Check
- [ ] Run code formatting with Black on all implemented modules
- [ ] Run Flake8 to ensure PEP 8 compliance
- [ ] Run MyPy to verify type annotations
- [ ] Review Dockerfile for best practices
- [ ] Check Kubernetes manifests for security best practices
- [ ] Verify CI/CD pipeline configuration
- [ ] Ensure test coverage of Phase 6 components is at least 80%
- [ ] Review environment variable handling in Docker and Kubernetes
- [ ] Check for hardcoded configuration that should be externalized

### Phase 6 Documentation Updates
- [ ] Update README.md with Phase 6 testing and deployment details
  - [ ] Testing strategy and coverage
  - [ ] Deployment instructions for various environments
  - [ ] CI/CD pipeline setup guide
- [ ] Update Makefile with Phase 6 specific commands
  - [ ] Commands for building and deploying containers
  - [ ] Commands for running comprehensive tests
- [ ] Update CHANGELOG.md with Phase 6 changes
  - [ ] Testing infrastructure improvements
  - [ ] Containerization and deployment setup
  - [ ] CI/CD pipeline implementation

## Phase 7: Documentation and Finalization

### 17. Documentation
- [x] Update README.md with setup and usage instructions
- [ ] Generate API documentation using FastAPI's built-in tools
- [ ] Create workflow visualizations in docs/ directory
  - [ ] Text processing workflow diagram
  - [ ] File processing workflow diagram
  - [ ] Database schema diagram
- [ ] Document configuration options and environment variables
- [ ] Create user guide with example queries and responses
- [ ] **Test:** Verify documentation is accurate by following setup instructions
- [ ] **Test:** Test API documentation with example requests

### 18. Security Review
- [ ] Conduct security audit
- [ ] Ensure proper environment variable handling
- [ ] Review permissions and access controls
- [ ] Check for data validation and sanitization
- [ ] Implement rate limiting for API endpoints
- [ ] Set up proper error handling to prevent information leakage
- [ ] **Test:** Perform security penetration testing
- [ ] **Test:** Verify rate limiting works as expected
- [ ] **Test:** Test error handling for security vulnerabilities

### Phase 7 Code Standards Check
- [ ] Perform final code formatting with Black on all modules
- [ ] Run Flake8 to ensure PEP 8 compliance throughout the codebase
- [ ] Run MyPy to verify all type annotations
- [ ] Check documentation for completeness and accuracy
- [ ] Verify all public interfaces have proper docstrings
- [ ] Ensure test coverage across the entire codebase is at least 80%
- [ ] Run security scanning tools on the codebase
- [ ] Review all TODOs and FIXMEs for resolution
- [ ] Verify all pre-commit hooks pass on the entire codebase

### Phase 7 Documentation Updates
- [ ] Finalize README.md with comprehensive project information
  - [ ] Project overview and architecture
  - [ ] Complete setup and deployment guide
  - [ ] Troubleshooting and FAQ section
- [ ] Finalize Makefile with all necessary commands
  - [ ] Commands summary and usage examples
  - [ ] Environment-specific commands
- [ ] Finalize CHANGELOG.md with complete version history
  - [ ] Version numbering and release dates
  - [ ] Feature implementations by phase
  - [ ] Bug fixes and improvements

## Development and Error Handling Rules

Throughout all phases of development, the following rules must be followed:

### Error Resolution Process
- [ ] Fix errors by implementing necessary corrections
- [ ] Validate all fixes by re-running the same query/operation that produced the error
- [ ] Document the fix and the validation method used

### LLM Agent Usage
- [ ] Delegate all text matching tasks to LLM agents instead of using regex or keyword matching
- [ ] Avoid creating specialized functions for individual error types
- [ ] When encountering errors, update the prompt with clear examples rather than creating new error-handling code
- [ ] For SQL issues, include example SQL commands in prompts to demonstrate proper implementation

### File Management
- [ ] Before creating a new file, check if an existing file offers similar functionality
- [ ] If similar functionality exists, update the existing file rather than creating a new one
- [ ] Never override already working code - extend or enhance it instead
- [ ] Document any file changes with clear comments explaining the purpose

### Code Reuse and Maintenance
- [ ] Prioritize reusability over creating new implementations
- [ ] When similar patterns emerge, abstract them into shared utilities
- [ ] Maintain clear separation of concerns between components
- [ ] Follow the established pattern when extending existing functionality

### Testing for Fixed Issues
- [ ] Create specific test cases for any fixed issues to prevent regression
- [ ] Ensure all fixes are covered by automated tests
- [ ] Include edge cases in test suites to validate the robustness of fixes

## Implementation Strategy

For each task:
1. Begin by setting up the necessary directory structure
2. Implement core functionality
3. Write tests to verify behavior
4. Document the implementation
5. Review against requirements before proceeding

Each phase should be completed sequentially, with each task marked as complete before moving to the next. This ensures a methodical approach to building the application while maintaining code quality and adherence to requirements.

## Testing Strategy

- **Unit Testing**: Test individual components in isolation
- **Integration Testing**: Test interactions between components
- **End-to-End Testing**: Test complete user flows
- **Mock External Services**: Use mocks for external APIs during testing
- **Test Fixtures**: Create reusable test data and setup
- **Continuous Testing**: Run tests after each implementation step
- **Regression Testing**: Ensure new changes don't break existing functionality

## Code Standards Strategy

- **Formatting**: Use Black for consistent code formatting
- **Linting**: Apply Flake8 for PEP 8 compliance
- **Type Checking**: Use MyPy to verify type annotations
- **Documentation**: Require docstrings for all public interfaces
- **Test Coverage**: Maintain minimum 80% test coverage
- **Security**: Regularly scan for vulnerabilities
- **Consistency**: Follow project-specific naming conventions
- **Reviews**: Conduct code reviews after each phase completion 