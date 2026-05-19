# Technology Stack

This repository is centered on a Vercel-hosted Flask app that serves the web UI and Twilio WhatsApp webhook. The current production path is:

```text
Twilio WhatsApp -> Vercel Flask app.py -> workflows/ -> Supabase Postgres/Storage + OpenAI
Clerk web user -> Vercel Flask UI -> Supabase-backed APIs -> same user-scoped data
```

## Runtime Components

| Area | Technology | Purpose |
| --- | --- | --- |
| Hosted app and webhook | Flask on Vercel (`app.py`) | Public UI, Twilio `/webhook`, Clerk-authenticated APIs, health checks, uploads, chat, and generated invoices. |
| Local development UI | Flask (`ui/app.py`) | Operator workspace for uploads, chat simulation, generated invoices, settings, and workflow inspection. |
| Workflows | `workflows/` modules | Routes text, file, query, approval, RAG, and invoice-generation workflows. |
| LLM provider | OpenAI | Intent routing, extraction, natural language responses, and embeddings. |
| Database | Supabase Postgres | Users, linked WhatsApp identities, receipts, line items, generated invoices, media, conversations, usage, and embeddings. |
| Migrations | Alembic | Schema evolution under `database/migrations/`. |
| Vector search | pgvector | Semantic search over invoice and line-item content. |
| Object storage | Supabase Storage | Private original receipt files and generated invoice documents. |
| Authentication | Clerk | Web sign-in and WhatsApp number linking for user-scoped data. |
| Messaging | Twilio WhatsApp | Incoming text/media webhook delivery and assistant replies. |
| Memory | Supabase Postgres conversations/messages | Durable user-scoped short-term context for WhatsApp and web multi-turn conversations. |
| Testing | pytest | Agent, workflow, service, database, and UI-adjacent coverage. |

## Repository Map

```text
.
├── agents/                 # Intent, validation, extraction, RAG, SQL, and response agents
├── compat/                 # Narrow compatibility shims for third-party package differences
├── constants/              # Prompt, intent, UI, LLM, vector, and invoice-template constants
├── database/               # SQLAlchemy models, CRUD helpers, connection setup, and Alembic migrations
├── docs/                   # Architecture and operational documentation
├── workflows/              # Active workflow routing and orchestration
├── memory/                 # Legacy in-memory and optional MongoDB checkpoint helpers
├── prompts/                # Prompt templates used by agents and LLM services
├── scripts/                # Env validation, embeddings, categories, memory, and DB cleanup scripts
├── services/               # Live backend, LLM, generated invoice, user profile, and template services
├── storage/                # Supabase Storage integration
├── template/               # Source invoice document templates used by generated invoices
├── tests/                  # pytest suite and tracked fixtures
├── ui/                     # Full local operator UI
├── utils/                  # Shared auth, config, logging, vector, status, and agent utilities
├── app.py                  # Vercel-hosted Flask entrypoint
├── requirements.txt        # Vercel/runtime dependency set
├── pyproject.toml          # Poetry dependency and tooling config for local development
└── vercel.json             # Vercel Flask configuration
```

## Primary Workflows

1. WhatsApp text/media reaches `app.py` through Twilio `/webhook`, or a signed-in user acts through the web UI.
2. Clerk identity and linked WhatsApp number resolve to the same internal `users.id`.
3. `services/live_backend.py` calls the text, file, query, or generated-invoice workflow.
4. File workflows validate the upload, store the original file in Supabase Storage, extract structured invoice data, persist database rows, and create embeddings.
5. Text workflows load recent user-scoped conversation memory, classify intent, answer analytics questions from stored invoice data, or create generated invoice records and documents.
6. The user and assistant turn is saved to `conversations` and `messages`, then responses are returned to WhatsApp as TwiML or to the browser as JSON.

## Production Notes

- Runtime secrets belong in Vercel environment variables or local `.env`; never commit real credentials.
- Supabase is the default database, vector, and file-storage provider.
- Original receipts and generated invoices are stored in private Supabase Storage with signed URLs.
- `DATABASE_URL` should use the Supabase pooler for Vercel runtime.
- `DIRECT_URL` should be available for Alembic migrations.
- `SUPABASE_SECRET_KEY` or `SUPABASE_SERVICE_ROLE_KEY` must remain server-side.
- `CLERK_REQUIRE_AUTH=true` and `CLERK_REQUIRE_VERIFIED_PHONE=true` should be used for production testing.
- Twilio should call `https://whatsapp-invoice-assistant.vercel.app/webhook`, not a temporary ngrok URL, for production traffic.
