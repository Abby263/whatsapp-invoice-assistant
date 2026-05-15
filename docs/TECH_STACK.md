# Technology Stack

This repository contains a WhatsApp receipt and invoice assistant with three runtime surfaces:

- `api/main.py`: FastAPI webhook/API service for WhatsApp and programmatic calls.
- `ui/app.py`: Full local Flask operator UI for development and end-to-end testing.
- `app.py`: Hosted Vercel-compatible Flask demo UI.

## Core Components

| Area | Technology | Purpose |
| --- | --- | --- |
| Backend API | FastAPI | WhatsApp webhook handling, text requests, file requests, and health checks. |
| Local/demo UI | Flask, vanilla JavaScript, CSS | Operator workspace for uploads, chat, generated invoices, settings, and workflow inspection. |
| Agent orchestration | LangGraph-style modules in `langchain_app/` | Routes text, file, query, and invoice-generation workflows. |
| LLM provider | OpenAI | Receipt extraction, intent classification, text-to-SQL support, response formatting, and embeddings. |
| Database | Supabase Postgres / PostgreSQL | Users, WhatsApp identities, invoices, invoice items, generated invoices, media, conversations, usage, and pgvector embeddings. |
| Migrations | Alembic | Schema evolution under `database/migrations/`. |
| Object storage | Supabase Storage | Original receipt files and generated invoice documents. |
| Authentication | Clerk | Web authentication and WhatsApp number linking for user-scoped data. |
| Memory | Optional MongoDB | Conversation history and checkpoint persistence when enabled. |
| Deployment | Vercel, Docker, Helm | Hosted demo deployment plus container/Kubernetes deployment assets for the full backend. |
| Testing | pytest | Agent, service, workflow, database, and UI-adjacent coverage. |

## Repository Map

```text
.
├── agents/                 # Agent implementations for extraction, validation, SQL, RAG, and formatting
├── api/                    # FastAPI application entry point
├── constants/              # Prompt, intent, UI, LLM, vector, and invoice template constants
├── database/               # SQLAlchemy models, CRUD helpers, connection setup, and Alembic migrations
├── docs/                   # Architecture and operational documentation
├── helm/                   # Kubernetes Helm chart
├── langchain_app/          # Active workflow routing and LangGraph-style orchestration
├── memory/                 # In-memory and MongoDB-backed conversation memory
├── prompts/                # Prompt templates used by agents and LLM services
├── scripts/                # Operational scripts for embeddings, categories, memory, and DB cleanup
├── services/               # LLM, OpenAI, generated invoice, user profile, and invoice template services
├── storage/                # Supabase Storage integration
├── template/               # Source invoice document templates
├── tests/                  # pytest suite and tracked fixtures
├── ui/                     # Full local operator UI
├── utils/                  # Shared auth, config, logging, vector, status, and agent utilities
├── app.py                  # Vercel-hosted demo UI entry point
├── docker-compose.yml      # Local service stack
├── pyproject.toml          # Python dependencies and test/tooling config
└── vercel.json             # Vercel routing/build configuration
```

## Primary Workflows

1. WhatsApp or UI input arrives at `api/main.py` or `ui/app.py`.
2. `langchain_app/api.py` routes the request to text or file processing.
3. File workflows validate the upload, store the original file in Supabase Storage, extract structured invoice data, persist database rows, and create embeddings.
4. Text workflows classify intent, answer analytics questions from stored invoice data, or create generated invoice records and documents.
5. Clerk identity plus linked WhatsApp number keep website and WhatsApp activity scoped to the same user.

## Production Notes

- Keep runtime secrets in `.env`, Vercel environment variables, or deployment secrets. `config/env.yaml` is intentionally ignored; use `config/env.yaml.example` only as a local template.
- Supabase is the default storage and database provider. AWS S3 code is no longer part of the active repository.
- The Vercel deployment serves the lightweight demo UI. The full webhook/backend flow still needs the production environment variables and services described in `SETUP.md`.
- Generated receipts and invoices are stored through Supabase Storage when configured, with database metadata in Postgres.
