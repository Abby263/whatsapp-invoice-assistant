
## Tech Stack

The tech stack is carefully selected to meet the requirements of scalability, efficiency, and robustness for a production environment handling thousands of simultaneous users.

| **Component**            | **Technology/Tool**          | **Purpose**                                                                 |
|--------------------------|------------------------------|-----------------------------------------------------------------------------|
| **Backend Framework**    | FastAPI                      | Asynchronous web framework for high-concurrency request handling.           |
| **Database**             | PostgreSQL                   | Relational database for structured storage with ACID compliance.            |
| **ORM**                  | SQLAlchemy                   | Simplifies database interactions with async support.                        |
| **Migrations**           | Alembic                      | Manages database schema migrations.                                         |
| **AI Model**             | GPT-4o-mini (OpenAI API)     | Processes invoice images to extract structured data.                        |
| **Orchestration**        | LangGraph                    | Manages workflows between agents for modularity and coordination.           |
| **Agent Definition**     | Pydantic                     | Strongly typed models for agent inputs/outputs and data validation.         |
| **Asynchronous Tasks**   | Celery                       | Offloads image processing and heavy tasks to maintain responsiveness.       |
| **Message Broker**       | Redis                        | Message broker for Celery and caching for performance.                      |
| **File Storage**         | Amazon S3                    | Scalable storage for invoice images and media files.                        |
| **Containerization**     | Docker                       | Ensures consistency across development, testing, and production.            |
| **Orchestration**        | Kubernetes                   | Manages container scaling, load balancing, and fault tolerance.             |
| **Logging**              | Python `logging` + ELK/CloudWatch | Structured logging for debugging and production monitoring.                 |
| **Code Quality**         | `black`, `flake8`, `mypy`, `pytest` | Enforces formatting, linting, type checking, and testing.                   |
| **CI/CD**                | GitHub Actions / GitLab CI   | Automates testing and deployment pipelines.                                 |

### Why This Stack?
- **FastAPI**: Its async capabilities handle thousands of concurrent WhatsApp requests efficiently.
- **PostgreSQL + SQLAlchemy**: Ensures structured data storage and retrieval with robust transaction support.
- **GPT-4o-mini**: Provides advanced image processing for accurate data extraction without relying on Tesseract.
- **Celery + Redis**: Offloads resource-intensive tasks like image processing, keeping the main app responsive.
- **Docker + Kubernetes**: Enables horizontal scaling and fault-tolerant deployment for high traffic.
- **Pydantic + LangGraph**: Promotes modular, reusable agents with validated data flows.

---

## Key Features and Implementation Details

### 1. **Scalability**
- **FastAPI**: Handles high concurrency with async endpoints (e.g., WhatsApp webhook in `api/routes/whatsapp.py`).
- **Celery + Redis**: Offloads image processing to asynchronous tasks, ensuring the main app scales under load.
- **Kubernetes**: Automatically scales containers based on traffic and ensures high availability.

### 2. **Image Processing with GPT-4o-mini**
- **No Tesseract**: Relies solely on GPT-4o-mini via the OpenAI API (`services/openai_service.py`) for image-to-data extraction.
- **Asynchronous Processing**: Images are processed in `tasks/image_processing.py` using Celery, keeping the API responsive.
- **Structured Data**: Extracted data (e.g., invoice number, date, total) is validated with Pydantic models (`database/models.py`) before storage in PostgreSQL.

### 3. **Data Extraction and Storage**
- **Extraction**: The `data_extractor.py` agent processes images and returns structured JSON, validated against Pydantic schemas.
- **Database**: Stored in PostgreSQL using SQLAlchemy (`database/schemas.py` and `database/crud.py`) with predefined tables for invoices, users, and conversations.
- **Corner Cases**: 
  - Invalid images trigger fallback messages (`constants/fallback_messages.py`).
  - Missing or malformed data is caught by Pydantic validation, with errors logged and handled gracefully (`utils/error_handling.py`).

### 4. **Agent Architecture**
- **Pydantic**: Agents like `invoice_query_agent.py` and `data_extractor.py` use Pydantic for input/output validation.
- **LangGraph**: The `langgraph/workflow.py` orchestrates agent interactions, routing requests based on intent or file type.

### 5. **Production-Ready Features**
- **Logging**: Structured logging configured in `utils/logging.py`, integrated with ELK or CloudWatch for centralized monitoring.
- **Code Standards**: Pre-commit hooks (`black`, `flake8`, `mypy`) in `.pre-commit-config.yaml` enforce consistency and catch errors early.
- **Testing**: `pytest` suite in `tests/` covers agents, API, services, and workflows.
- **Docker**: `docker/Dockerfile` and `docker-compose.yml` for local development and production builds.
- **Kubernetes**: Manifests in `kubernetes/` for scalable deployment.

### 6. **Error Handling**
- **Validation**: Pydantic ensures extracted data matches expected schemas, rejecting invalid inputs.
- **Fallbacks**: Predefined messages in `constants/fallback_messages.py` handle failures (e.g., “Please upload a valid invoice”).
- **Logging**: Errors are logged with context for debugging (`utils/logging.py`).

---

## Example Workflow
1. **User Uploads Invoice Image via WhatsApp**:
   - Received by `api/routes/whatsapp.py` via Twilio webhook.
2. **Intent Detection**:
   - `text_intent_classifier.py` determines the user’s intent (e.g., “extract invoice data”).
3. **Image Validation**:
   - `file_validator.py` checks file type and size.
4. **Data Extraction**:
   - `tasks/image_processing.py` processes the image with GPT-4o-mini asynchronously, extracting structured data.
5. **Storage**:
   - Validated data is stored in PostgreSQL via `database/crud.py`.
6. **Response**:
   - `response_formatter.py` crafts a reply (e.g., “Invoice #123 saved: Total $500”), sent via `services/twilio_service.py`.

---

### How the System Handles Key Aspects

#### 1. **Agent States**
The system manages agent states through a modular and dynamic workflow, as depicted in the "LangGraph Workflow" and "Agent Workflow" flowcharts:
- **Implementation**: Distinct agents handle specific tasks, such as intent classification (`text_intent_classifier.py`), invoice extraction (`invoice_extractor.py`), and file validation (`file_validator.py`). Each agent represents a state in the workflow, triggered based on user input (text or file) and intent.
- **Flow**: The workflow begins with input from WhatsApp or FastAPI, routed through a decision node (`Determine Input Type` or `Router: Validate File & Check if Invoice?`) to the appropriate agent. For example:
  - Text inputs go to the `Text Intent Classifier` to detect intents like "InvoiceQuery," "InvoiceCreator," "Greeting," or "General."
  - File inputs are validated and processed by `file_validator.py` and `data_extractor.py`.
- **Dynamic Transitions**: Intents drive state transitions (e.g., "InvoiceQuery" leads to SQL conversion, while "InvoiceCreator" triggers extraction and PDF generation), ensuring flexibility and adaptability.
- **Modularity**: Agents are independent, enabling easy updates and testing without affecting the entire system.

#### 2. **Memory**
Memory is a critical component for maintaining context across interactions:
- **Implementation**: A dedicated `memory/` directory with `langgraph_memory.py` manages stateful behavior. This module stores conversational context (e.g., previous intents, extracted data) and integrates with agents like `text_intent_classifier.py` and `data_extractor.py`.
- **Integration**: The memory system supports the LLM (e.g., GPT-4o-mini) in retaining user history, ensuring responses are contextually relevant. For instance, it remembers prior queries during an "InvoiceQuery" workflow.
- **Persistence**: Context is preserved across sessions, enabling seamless multi-turn interactions via WhatsApp or FastAPI.

#### 3. **Coding Standards**
The system enforces high-quality, maintainable code through structured design and tooling:
- **Enforcement**: Configuration files like `.flake8`, `.pylintrc`, and `.pre-commit-config.yaml` ensure consistent formatting, linting, and type checking. Templates (`general_response_template.jinja`, `default_invoice_template.jinja`) standardize outputs.
- **Modularity**: Code is organized into directories like `agents/`, `workflows/`, and `utils/`, with each component having a single responsibility (e.g., `text_intent_classifier.py` for intent detection, `s3_handler.py` for file storage).
- **Documentation**: A `README.md` and inline comments maintain clarity and accessibility for developers.

#### 4. **Flakes (Unreliable Tests or Inputs)**
The system mitigates flakes through validation, error handling, and testing:
- **Validation**: `file_validator.py` checks file types and content, rejecting unsupported inputs (e.g., non-invoice files) with fallback responses from `fallback_messages.py`.
- **Error Handling**: Robust fallback mechanisms ensure graceful degradation (e.g., "Reject Unsupported File" path in the workflow). `error_handling.py` manages exceptions systematically.
- **Testing**: A `tests/` directory includes unit and integration tests for agents, workflows, memory, and file handling, reducing the likelihood of unreliable behavior. Pre-commit hooks catch issues early.

---

### Repository Structure

The updated repository structure below is designed to fully support the "LangGraph Workflow" and "Agent Workflow" architectures. It includes all necessary agents, memory management, file handling, database integration, and response formatting, ensuring the system can process inputs, manage intents, handle files, and generate responses as described.

```plaintext
project_root/
│
├── agents/                    # Directory for agent-related code
│   ├── __init__.py
│   ├── text_intent_classifier.py  # Classifies intents (e.g., InvoiceQuery, Greeting) with LLM + memory
│   ├── invoice_extractor.py    # Extracts invoice data from text using LLM
│   ├── response_formatter.py   # Formats responses using templates and agent structure
│   ├── file_validator.py       # Validates files and checks if they’re invoices
│   ├── data_extractor.py       # Extracts structured data from files with GPT-4o-mini
│
├── workflows/                 # Directory for workflow logic
│   ├── __init__.py
│   ├── invoice_query_workflow.py  # Converts text to SQL, updates PostgreSQL
│   ├── invoice_creator_workflow.py  # Extracts data, maps to schema, generates PDF
│   ├── general_response_workflow.py  # Handles Greeting and General intents
│   ├── file_processing_workflow.py  # Validates files, uploads to S3 if needed
│
├── memory/                    # Memory management and context storage
│   ├── __init__.py
│   ├── langgraph_memory.py      # Implements LangGraph Memory for stateful interactions
│   ├── context_manager.py       # Manages context across sessions
│
├── database/                  # Database-related configurations
│   ├── __init__.py
│   ├── models.py              # Pydantic models for data validation
│   ├── schemas.py             # SQLAlchemy models for PostgreSQL tables
│   ├── crud.py                # CRUD operations for database access
│   ├── migrations/            # Alembic migration files for schema changes
│
├── storage/                   # File storage and S3 integration
│   ├── __init__.py
│   ├── s3_handler.py          # Uploads raw files to S3
│
├── services/                  # External service integrations
│   ├── __init__.py
│   ├── twilio_service.py      # WhatsApp integration via Twilio
│   ├── openai_service.py      # GPT-4o-mini API integration
│   ├── celery_service.py      # Celery for asynchronous tasks
│
├── tasks/                     # Celery asynchronous tasks
│   ├── __init__.py
│   ├── image_processing.py    # Processes file data extraction with GPT-4o-mini
│
├── utils/                     # Utility functions and helpers
│   ├── __init__.py
│   ├── base_node.py           # Base structure for workflow nodes
│   ├── base_router.py         # Routing logic for intent and file type decisions
│   ├── logging.py             # Centralized logging configuration
│   ├── error_handling.py      # Error handling and fallbacks
│   ├── image_utils.py         # Utilities for image/file handling
│
├── constants/                 # Centralized configuration files
│   ├── __init__.py
│   ├── prompts.py             # Prompts for LLMs (e.g., intent classification, extraction)
│   ├── fallback_messages.py   # Fallback responses for unsupported inputs
│   ├── llm_configs.py         # GPT-4o-mini configuration
│   ├── agent_configs.py       # Agent-specific settings
│
├── prompts/                   # Prompt templates for LLMs
│   ├── __init__.py
│   ├── text_intent_prompt.txt # Prompt for intent classification
│   ├── invoice_query_prompt.txt # Prompt for text-to-SQL conversion
│   ├── data_extraction_prompt.txt # Prompt for file data extraction
│   ├── response_format_prompt.txt # Prompt for response formatting
│
├── templates/                 # Response and invoice templates
│   ├── __init__.py
│   ├── general_response_template.jinja  # Template for Greeting/General responses
│   ├── default_invoice_template.jinja  # Template for PDF invoice generation
│
├── api/                       # API-related code
│   ├── __init__.py
│   ├── main.py                # FastAPI application entry point
│   ├── dependencies.py        # Dependency injection (e.g., DB sessions)
│   └── routes/                # API endpoints
│       ├── __init__.py
│       ├── whatsapp.py        # WhatsApp webhook endpoint
│       ├── health.py          # Health check endpoint
│
├── tests/                     # Unit and integration tests
│   ├── __init__.py
│   ├── test_agents.py         # Tests for agent functionality
│   ├── test_workflows.py      # Tests for workflow logic
│   ├── test_memory.py         # Tests for memory integration
│   ├── test_file_handling.py  # Tests for file validation and S3 uploads
│   ├── test_api.py            # API endpoint tests
│   ├── test_services.py       # Service integration tests
│   ├── test_tasks.py          # Celery task tests
│   ├── test_utils.py          # Utility function tests
│
├── docker/                    # Docker configuration
│   ├── Dockerfile             # Application Dockerfile
│   ├── docker-compose.yml     # Local development setup (e.g., app, DB, Celery)
│
├── kubernetes/                # Kubernetes manifests
│   ├── deployment.yaml        # Deployment configuration
│   ├── service.yaml           # Service configuration
│   ├── ingress.yaml           # Ingress configuration
│
├── .pre-commit-config.yaml    # Pre-commit hooks for linting and formatting
├── pyproject.toml             # Project settings (black, flake8, etc.)
├── requirements.txt           # Python dependencies
└── README.md                  # Project documentation and setup instructions
```

---

### Explanation of Updated Repository Structure

This structure aligns with the workflow diagrams and addresses your requirements:

- **Agents**: Includes all required agents:
  - `text_intent_classifier.py`: Detects intents (e.g., InvoiceQuery, Greeting).
  - `invoice_extractor.py`: Extracts invoice data from text.
  - `response_formatter.py`: Formats responses consistently.
  - `file_validator.py`: Validates files and routes them appropriately.
  - `data_extractor.py`: Extracts data from files using GPT-4o-mini.
- **Workflows**: Encapsulates logic for each intent-based flow, matching the flowchart branches (e.g., `invoice_query_workflow.py` for SQL conversion, `invoice_creator_workflow.py` for PDF generation).
- **Memory**: `langgraph_memory.py` and `context_manager.py` ensure stateful interactions, supporting the LLM’s memory integration.
- **Database**: Supports PostgreSQL interactions with models, schemas, and CRUD operations, critical for "InvoiceQuery" workflows.
- **Storage**: `s3_handler.py` manages file uploads, aligning with the "Upload raw file to S3" path.
- **Services and Tasks**: Integrates Twilio, OpenAI, and Celery for WhatsApp, LLM, and asynchronous processing (e.g., `image_processing.py`).
- **Utils and Constants**: Provides reusable tools and configurations (e.g., prompts, fallbacks) to enforce coding standards and handle flakes.
- **Templates**: Standardizes responses and invoices, ensuring consistency.
- **API**: Supports WhatsApp and FastAPI inputs with dedicated endpoints.
- **Tests**: Comprehensive testing minimizes flakes and ensures reliability.
- **Deployment**: Docker and Kubernetes configurations enable scalable deployment.

---

### Conclusion

The system effectively handles agent states through modular agents and dynamic workflows, manages memory with a dedicated module for context retention, enforces coding standards via tooling and structure, and mitigates flakes with validation and testing. The updated repository structure is production-ready, modular, and capable of supporting the entire workflow architecture and flow as described in the attached diagrams. All necessary agents and supporting files are included to ensure full functionality. Let me know if you need further details or adjustments!