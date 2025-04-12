As you complete tasks and reference relevant files update this file as our memory to help with future tasks

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
- [x] Ensure all code follows project style guide
- [x] Add type hints to all functions
- [x] Verify docstrings on all public modules, classes, and functions
- [x] Verify all security best practices are implemented
- [x] Ensure logging is properly implemented for database operations

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
- [x] Create prompts/ directory with separate files for each prompt type
  - [x] text_intent_classification_prompt.txt
  - [x] text_to_sql_conversion_prompt.txt
  - [x] invoice_entity_extraction_prompt.txt
  - [x] file_validation_prompt.txt
  - [x] invoice_data_extraction_prompt.txt
  - [x] response_formatting_prompt.txt
- [x] Implement LLMFactory class in services/llm_factory.py
  - [x] Configure model name, temperature, and other parameters
  - [x] Add methods for loading prompts from files
  - [x] Implement caching for prompt templates
- [x] Configure GPT-4o-mini integration in services/openai_service.py
- [x] **Test:** Create mock LLM responses for testing without API calls
- [x] **Test:** Write unit tests for prompt loading and template rendering
- [x] **Test:** Test LLMFactory with different configurations
- [x] **Test:** Verify OpenAI service integration with mock responses

### 5. Router and Agent Implementation
- [x] Create BaseAgent class in utils/base_agent.py to ensure standardized agent interfaces
- [x] Implement InputTypeRouter in utils/input_type_router.py for determining input type (text vs file)
- [x] Implement text_intent_classifier.py agent
  - [x] Integration with LLM for intent classification
  - [x] Memory integration for context retention
  - [x] Support for Greeting, General, InvoiceQuery, and InvoiceCreator intents
- [x] **Test:** Write unit tests for the text_intent_classifier with sample inputs
- [x] **Test:** Test classification accuracy with various input types
- [x] Implement file_validator.py agent
  - [x] File type validation (image, PDF, Excel, CSV)
  - [x] Integration with LLM to check if the file is a valid invoice
  - [x] Router capability to direct to appropriate processing path
- [x] **Test:** Create test fixtures with sample invoice files and non-invoice files
- [x] **Test:** Verify file validator correctly identifies valid invoices
- [x] Implement text_to_sql_conversion_agent.py for InvoiceQuery intents
- [x] **Test:** Test SQL conversion with various query types
- [x] **Test:** Verify SQL injection protection
- [x] Implement invoice_entity_extraction_agent.py for InvoiceCreator intents
- [x] **Test:** Test entity extraction with various input formats
- [x] Implement data_extractor.py agent for file processing
  - [x] Integration with GPT-4o-mini for data extraction
  - [x] Extraction of invoice details (vendor, date, amount, items)
  - [x] Mapping extracted data to database schema
- [x] **Test:** Test data extraction with sample invoice images
- [x] **Test:** Verify extraction accuracy against known values
- [x] Implement response_formatter.py agent
  - [x] Format responses using templates
  - [x] Add disclaimers and structure to all responses
  - [x] Handle different response types (text, files, templates)
- [x] **Test:** Verify response formatting with different template types
- [x] **Test:** Test edge cases like empty responses or error conditions

### 6. RAG Implementation
- [x] Implement invoice_rag_agent.py for semantic search
  - [x] Add pgvector integration for vector storage and search
  - [x] Create utility functions for generating and storing embeddings
  - [x] Implement vector similarity search for invoice data
  - [x] Add automatic embedding generation during invoice upload
  - [x] Ensure proper formatting of vector data for PostgreSQL
- [x] **Test:** Create test fixtures for vector search testing
- [x] **Test:** Verify RAG search returns relevant results
- [x] **Test:** Test edge cases like missing embeddings or malformed queries
- [x] **Test:** Validate embedding generation during invoice upload

### 7. LangGraph Workflow Implementation
- [x] Create langchain_app/ directory for LangGraph components
- [x] Define workflow state schema in langchain_app/state.py
  - [x] Include input data, classification results, and processing outputs
  - [x] Use Pydantic models for type safety
- [x] Implement workflow nodes in langchain_app/nodes.py
  - [x] Create nodes for each processing step (classification, validation, extraction)
  - [x] Ensure proper error handling and logging in each node
- [x] Define workflow graph in langchain_app/workflow.py
  - [x] Connect nodes with edges
  - [x] Implement conditional routing based on input type and intent
  - [x] Add visualization for debugging
- [x] Create API interface in langchain_app/api.py
  - [x] Handle text and file inputs
  - [x] Process WhatsApp message format
  - [x] Format responses for Twilio
- [x] **Test:** Create end-to-end tests for the workflow
- [x] **Test:** Verify handling of different input types
- [x] **Test:** Test error handling and recovery

### 8. Memory and Context Management
- [x] Implement langgraph_memory.py for stateful conversations
  - [x] Storage for conversation history
  - [x] Context retention between user interactions
  - [x] Memory clearing/expiration mechanisms
- [x] Create context_manager.py to maintain conversation history
  - [x] Integration with database for persistence
  - [x] Support for retrieving past conversations
- [x] **Test:** Create test fixtures with sample conversation histories
- [x] **Test:** Test memory retrieval and context maintenance
- [x] **Test:** Verify memory expiration works as expected
- [x] **Test:** Test context manager with database integration

### 9. Workflow Implementation
- [x] Create base_workflow.py with shared workflow logic
- [x] Implement main_workflow.py for orchestrating the entire flow
  - [x] Input type determination (text vs file)
  - [x] Routing based on input type and intent
- [x] **Test:** Test main workflow routing with different input types
- [x] Implement text_processing_workflow.py for handling text inputs
  - [x] Intent classification routing
  - [x] Processing for different intents
- [x] **Test:** Test text processing workflow with different intents
- [x] Implement invoice_query_workflow.py
  - [x] Text-to-SQL conversion
  - [x] Database query execution
  - [x] Result formatting
- [x] **Test:** Test invoice query workflow with sample queries
- [x] **Test:** Verify database query execution and result formatting
- [x] Implement invoice_creator_workflow.py
  - [x] Entity extraction
  - [x] Template population
  - [x] PDF generation
- [x] **Test:** Test invoice creation workflow with sample data
- [x] **Test:** Verify PDF generation works correctly
- [x] Implement general_response_workflow.py for Greeting and General intents
- [x] **Test:** Test general response workflow with greeting and general queries
- [x] Implement file_processing_workflow.py
  - [x] File validation
  - [x] Handling valid invoices
  - [x] Handling invalid files
  - [x] Handling unsupported formats
- [x] **Test:** Test file processing workflow with various file types
- [x] **Test:** Verify proper handling of valid and invalid files
- [x] **Test:** End-to-end test of entire workflow with sample inputs

### Phase 2 Code Standards Check
- [x] Run code formatting with Black on all implemented modules
- [x] Run Flake8 to ensure PEP 8 compliance
- [x] Run MyPy to verify type annotations with focus on agent interfaces
- [x] Verify consistent error handling patterns across all agents
- [x] Check for proper dependency injection in agent implementations
- [x] Review prompt templates for consistency and standards
- [x] Verify test coverage of Phase 2 components is at least 80%
- [x] Check for proper exception handling and logging
- [x] Review agent interfaces for consistency

### Phase 2 Documentation Updates
- [x] Update README.md with Phase 2 implementation details
  - [x] LLM integration instructions
  - [x] Agent system architecture overview
  - [x] Workflow implementation details
- [x] Update Makefile with Phase 2 specific commands
  - [x] Commands for running specific workflows
  - [x] Commands for testing agents independently
- [x] Update CHANGELOG.md with Phase 2 changes
  - [x] LLM Factory implementation details
  - [x] Agent and router implementation
  - [x] Workflow architecture details

## Phase 3: External Services Integration

### 10. WhatsApp Integration
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

### 11. Storage Implementation
- [x] Set up AWS S3 bucket for file storage
- [x] Implement s3_handler.py for file uploads and retrievals
  - [x] File upload functionality
  - [x] URL generation for stored files
  - [x] File retrieval for processing
- [x] **Test:** Create mock S3 service for testing uploads and retrievals
- [x] **Test:** Test file upload and URL generation
- [x] **Test:** Verify file retrieval works as expected

### 12. Task Queue Setup
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

### 13. Template Implementation
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

### 14. Constant Definitions
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

### 15. FastAPI Implementation
- [x] Create main.py with FastAPI application setup
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

### 16. Webhook Processing
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

### 17. Comprehensive Test Implementation
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

### 18. Containerization and Deployment
- [x] Finalize Dockerfile for production
- [x] Create Kubernetes manifests for deployment
  - [x] Deployment configuration
  - [x] Service configuration
  - [x] Ingress configuration
  - [x] ConfigMap and Secret management
- [ ] Set up CI/CD pipeline with GitHub Actions/GitLab CI
- [ ] Configure logging and monitoring for production
- [x] **Test:** Verify Docker builds successfully
- [x] **Test:** Test Kubernetes deployment in staging environment
- [ ] **Test:** Perform load testing in production-like environment

### Phase 6 Code Standards Check
- [x] Run code formatting with Black on all implemented modules
- [x] Run Flake8 to ensure PEP 8 compliance
- [x] Run MyPy to verify type annotations
- [x] Review Dockerfile for best practices
- [x] Check Kubernetes manifests for security best practices
- [ ] Verify CI/CD pipeline configuration
- [ ] Ensure test coverage of Phase 6 components is at least 80%
- [x] Review environment variable handling in Docker and Kubernetes
- [x] Check for hardcoded configuration that should be externalized

### Phase 6 Documentation Updates
- [x] Update README.md with Phase 6 testing and deployment details
  - [x] Testing strategy and coverage
  - [x] Deployment instructions for various environments
  - [ ] CI/CD pipeline setup guide
- [x] Update Makefile with Phase 6 specific commands
  - [x] Commands for building and deploying containers
  - [ ] Commands for running comprehensive tests
- [x] Update CHANGELOG.md with Phase 6 changes
  - [ ] Testing infrastructure improvements
  - [x] Containerization and deployment setup
  - [ ] CI/CD pipeline implementation

## Phase 7: Documentation and Finalization

### 19. Documentation
- [x] Update README.md with setup and usage instructions
- [x] Create workflow visualizations in docs/ directory
  - [x] Text processing workflow diagram
  - [x] File processing workflow diagram
  - [x] Database schema diagram
- [x] Setup LangGraph Studio for interactive workflow visualization
- [x] Create vector search implementation documentation
- [x] Validate and update database schema documentation
  - [x] Confirm PostgreSQL and pgvector extension setup
  - [x] Document actual table structures and relationships
  - [x] Update DATABASE.md with validation results
- [x] Add system validation summary to README.md
- [ ] Generate API documentation using FastAPI's built-in tools
- [ ] Document configuration options and environment variables
- [ ] Create user guide with example queries and responses
- [ ] **Test:** Verify documentation is accurate by following setup instructions
- [ ] **Test:** Test API documentation with example requests

### 20. Security Review
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

## Phase 8: Test UI Implementation

### 21. Core UI Development
- [x] Create Flask-based UI for testing WhatsApp Invoice Assistant
- [x] Implement the UI/app.py with appropriate API endpoints
  - [x] Message sending endpoint (/api/message)
  - [x] File upload endpoint (/api/upload)
  - [x] Agent flow visualization endpoint (/api/agent-flow)
  - [x] Database status endpoint (/api/db-status)
  - [x] Workflow step log retrieval endpoint (/api/step-logs)
- [x] Create HTML templates in ui/templates directory
  - [x] Main index.html with responsive design
  - [x] Chat interface for message simulation
  - [x] File upload component
  - [x] Workflow visualization panel
- [x] **Test:** Test all API endpoints with sample requests
- [x] **Test:** Verify UI correctly displays agent responses

### 22. Frontend Implementation
- [x] Develop UI static assets in ui/static directory
  - [x] CSS styles for responsive design
  - [x] JavaScript for dynamic content loading
  - [x] Images and icons for UI elements
- [x] Implement asynchronous API calls with proper error handling
- [x] Create chat interface with message history
- [x] Design responsive mobile-first layout
- [x] Add file upload progress indicators
- [x] Implement workflow visualization with clickable steps
- [x] Add real-time database status updates
- [x] **Test:** Test UI on various screen sizes
- [x] **Test:** Verify all UI components function correctly

### 23. UI Integration Testing
- [x] Implement comprehensive UI error handling
- [x] Fix "Event loop is closed" errors in Flask async operations
- [x] Ensure proper handling of file uploads
- [x] Resolve invoice creator validation errors
- [x] Implement test mode for all agent workflows
- [x] Add WhatsApp number simulation in message processing
- [x] **Test:** Perform end-to-end testing of UI with backend
- [x] **Test:** Verify all error cases are properly handled
- [x] **Test:** Test UI performance with multiple requests

### Phase 8 Code Standards Check
- [x] Ensure UI code follows project style guide
- [x] Implement proper logging in UI application
- [x] Verify security of UI endpoints
- [x] Review frontend code for best practices
- [x] Ensure UI is accessible and user-friendly

### Phase 8 Documentation Updates
- [x] Update UI README.md with setup instructions
- [x] Document UI API endpoints
- [x] Create usage guide for the test interface
- [x] Update main README.md with UI testing information

## Development and Error Handling Rules

Throughout all phases of development, the following rules must be followed:

### Error Resolution Process
- [x] Fix errors by implementing necessary corrections
- [x] Validate all fixes by re-running the same query/operation that produced the error
- [x] Document the fix and the validation method used

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