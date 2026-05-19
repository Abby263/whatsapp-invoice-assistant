# WhatsApp Invoice Assistant

AI receipt and invoice workspace for WhatsApp-first operators. Users can send receipt images or PDFs to a Twilio WhatsApp number, link the same WhatsApp number to their Clerk web account, review extracted records in the web app, generate outgoing invoices, and ask finance questions over the stored data.

The production path runs on Vercel with Flask, Clerk, Twilio, Supabase Postgres, Supabase Storage, pgvector, and OpenAI.

## Live App

- Web app: [https://whatsapp-invoice-assistant.vercel.app](https://whatsapp-invoice-assistant.vercel.app)
- Twilio incoming-message webhook: [https://whatsapp-invoice-assistant.vercel.app/webhook](https://whatsapp-invoice-assistant.vercel.app/webhook)
- Repository: [https://github.com/Abby263/whatsapp-invoice-assistant](https://github.com/Abby263/whatsapp-invoice-assistant)

If production environment variables are missing, the hosted app falls back to demo mode so reviewers can still inspect the interface. Real WhatsApp processing requires the setup in [SETUP.md](SETUP.md).

## Demo

![Receipt Intelligence Workspace demo](docs/assets/invoice-command-center-demo.gif)

### Light Mode

![Receipt Intelligence Workspace light mode](docs/assets/ui-command-center-light.png)

### Dark Mode

![Receipt Intelligence Workspace dark mode](docs/assets/ui-command-center-dark.png)

## Product Capabilities

- Accepts WhatsApp text, image, and PDF messages through Twilio.
- Links Clerk web users to WhatsApp numbers so web and WhatsApp activity share one internal `users.id`.
- Extracts merchant, date, totals, taxes, payment details, and line items from receipts and handwritten expense ledgers.
- Stores original receipt files in a private Supabase Storage bucket.
- Stores normalized invoice, item, media, message, user, and generated-invoice records in Supabase Postgres.
- Generates OpenAI embeddings and stores them in pgvector columns for guarded agentic RAG.
- Answers user-scoped finance questions from approved extracted data using SQL, full-document retrieval, line-item retrieval, and keyword fallback.
- Generates outgoing invoices from WhatsApp or the website using saved seller/client defaults.
- Shows parsing quality signals, row counts, and review warnings for handwritten or low-confidence uploads.
- Requires pending WhatsApp uploads to be approved or rejected in WhatsApp with `APPROVE <upload_id>` / `REJECT <upload_id>` commands before analytics rows are created.
- Lets signed-in users delete one saved upload, one generated invoice, or all historical data from the web app.
- Shows receipt, invoice, workflow, storage, database, and vector status in the UI.

Example WhatsApp prompts:

- `Hi`
- `What did I spend on coffee this month?`
- `Show my latest receipts.`
- `Create an invoice for Acme for $500 consulting due next Friday.`

WhatsApp media behavior:

- Each uploaded image/PDF gets a final `Document extraction result` or `Document not processed` status.
- Pending uploads must show an `APPROVE <upload_id>` / `REJECT <upload_id>` command in WhatsApp. Saved history can show the pending upload and commands for reference, but it is not an approval surface.
- If a pending upload cannot get an upload id, the assistant asks the user to resend the file instead of pointing them to an approval flow that cannot work.
- If WhatsApp/Twilio splits a multi-image forward into separate webhooks, the summaries arrive one per image. Six forwarded images should produce six final file-status messages.
- If Twilio sends several media attachments in one webhook, the bot returns a `Batch processing result` with saved, duplicate, and failed counts.
- Random images, blank pages, tickets, bank-transfer confirmations, and non-financial notes are rejected instead of being stored as expenses.

## Architecture

```mermaid
flowchart TB
    subgraph Clients["Clients"]
        WU["WhatsApp user"]
        WEB["Signed-in web user"]
    end

    subgraph Edge["Vercel Flask application"]
        TW["Twilio WhatsApp"]
        WH["POST /webhook"]
        DASH["Receipt Intelligence UI"]
        AUTH["Clerk auth and WhatsApp linking"]
        API["Authenticated app APIs"]
    end

    subgraph Workflows["Agent workflows"]
        POLICY["Conversation policy"]
        ROUTER["Text and media router"]
        VALIDATOR["Document validator"]
        EXTRACTOR["Structured document extraction"]
        HITL["HITL approval"]
        STORE["Confirmed database storage"]
        SQL["User-scoped Text-to-SQL"]
        RAG["Agentic RAG retrieval"]
        GENERATOR["Invoice generation"]
        HIST["History deletion"]
        FORMATTER["Compact WhatsApp formatter"]
    end

    subgraph AI["OpenAI"]
        CHAT["gpt-5.4-mini chat and vision"]
        EMBED["Embedding model"]
    end

    subgraph Data["Supabase"]
        DB["Postgres tables: users, media, invoices, items, generated invoices, messages"]
        STORAGE["Private Storage bucket with user-scoped paths"]
        VECTOR["pgvector indexes"]
    end

    WU -->|"text, image, PDF"| TW
    TW --> WH
    WEB --> DASH
    DASH --> AUTH
    AUTH --> API
    API --> ROUTER
    WH --> POLICY
    POLICY --> ROUTER

    ROUTER -->|"receipt or ledger media"| VALIDATOR
    VALIDATOR --> CHAT
    VALIDATOR --> EXTRACTOR
    EXTRACTOR --> CHAT
    EXTRACTOR --> STORAGE
    EXTRACTOR --> HITL
    HITL -->|"WhatsApp APPROVE upload_id"| STORE
    HITL -->|"WhatsApp REJECT upload_id"| STORAGE
    STORE --> DB
    STORE --> EMBED
    EMBED --> VECTOR

    ROUTER -->|"spend question"| SQL
    SQL --> CHAT
    SQL --> DB
    SQL --> RAG
    RAG --> VECTOR

    ROUTER -->|"create invoice"| GENERATOR
    GENERATOR --> CHAT
    GENERATOR --> DB
    GENERATOR --> STORAGE

    API -->|"confirmed delete"| HIST
    HITL -->|"CONFIRM DELETE"| HIST
    HIST --> DB
    HIST --> STORAGE

    ROUTER -->|"greeting or help"| CHAT
    CHAT --> FORMATTER
    SQL --> FORMATTER
    EXTRACTOR --> FORMATTER
    HITL --> FORMATTER
    GENERATOR --> FORMATTER
    FORMATTER --> TW
    FORMATTER --> DASH
```

### Processing Contract

Every uploaded file follows the same contract before it reaches analytics:

1. Twilio delivers media to `/webhook` with the sender WhatsApp number.
2. The app resolves that number to the linked `users.id`.
3. The validator rejects unsupported, duplicate, blank, or non-financial images before expense storage.
4. Valid files are uploaded to Supabase Storage under a user-scoped path and registered in `media`.
5. The extractor returns the canonical schema from [schemas/llm_outputs/document_extraction.py](schemas/llm_outputs/document_extraction.py).
6. The normalizer fixes row-level ledger dates, computes ledger totals from extracted rows, and records `extraction_quality` warnings when review is needed.
7. The user gets a fixed-schema WhatsApp summary plus `APPROVE <upload_id>` and `REJECT <upload_id>` commands, and the same pending upload appears under Saved history on the website for tracking.
8. The linked user approves or rejects by replying on WhatsApp with `APPROVE <upload_id>` / `REJECT <upload_id>`.
9. Only after approval does the app re-open the private file, re-run extraction, and write invoice rows, item rows, embeddings, and processing metadata with the same `user_id`.
10. WhatsApp receives one final file-status response per delivered media item, or a batch summary when Twilio sends multiple attachments in one webhook.
11. Text turns load recent Supabase-backed conversation memory so short follow-ups stay attached to the same user context across WhatsApp and the website.
12. Spend questions use user-scoped SQL first, then the agentic RAG retriever over approved `invoice_embeddings`, approved `items.description_embedding`, and finalized receipt keywords.
13. Deletes require human confirmation: browser deletes include a confirmation dialog, and WhatsApp deletes require exact `CONFIRM DELETE ...` commands before rows or files are removed.

## Runtime Components

| Component | Purpose |
| --- | --- |
| [app.py](app.py) | Vercel Flask entrypoint for the hosted UI, `/webhook`, auth APIs, upload/chat routes, generated invoices, and health checks. |
| [ui/app.py](ui/app.py) | Local operator UI for development and workflow inspection. |
| [services/live_backend.py](services/live_backend.py) | Production bridge from Flask routes to Supabase, Clerk identity, Twilio media, receipt processing, and invoice generation. |
| [langchain_app/](langchain_app) | Text, file, query, and invoice-generation workflow routing. |
| [agents/](agents) | LLM-backed intent classification, validation, extraction, SQL generation, RAG, and response formatting. |
| [prompts/](prompts) | Prompt templates grouped by conversation, document processing, SQL, and storage tasks. |
| [schemas/llm_outputs/](schemas/llm_outputs) | Canonical structured-output contracts for LLM parsing. |
| [database/](database) | SQLAlchemy models, connection handling, CRUD helpers, and Alembic migrations. |
| [storage/supabase_storage_handler.py](storage/supabase_storage_handler.py) | Private Supabase Storage uploads and signed URL generation. |
| [storage/user_uploads.py](storage/user_uploads.py) | User-scoped upload paths, media registry writes, and duplicate lookup metadata. |
| [services/generated_invoice_service.py](services/generated_invoice_service.py) | Generated invoice defaults, line items, document creation, storage, and analytics. |
| [services/history_service.py](services/history_service.py) | User-scoped listing and deletion of receipt history, generated invoices, messages, usage rows, and stored files. |
| [services/conversation_memory.py](services/conversation_memory.py) | Supabase Postgres-backed active conversation memory for WhatsApp and web multi-turn context. |
| [utils/clerk_auth.py](utils/clerk_auth.py) | Clerk JWT verification and auth enforcement. |
| [memory/](memory) | Legacy in-memory and optional MongoDB checkpoint helpers for local experiments. |

## Data Model

The application stores user-scoped operational data in Supabase Postgres:

- `users`: Clerk identity, WhatsApp number, profile data, and invoice-generation defaults.
- `invoices`: extracted receipt or invoice header data.
- `items`: line items extracted from uploaded receipts.
- `media`: uploaded receipt metadata, content hashes, storage paths, and duplicate detection fields.
- `generated_invoices` and `generated_invoice_items`: outgoing invoices created from WhatsApp or the web app.
- `conversations`, `messages`, and `whatsapp_messages`: chat history and delivery metadata.
- pgvector embedding columns: semantic search over invoice and item content.

Uploaded receipt files and generated invoice documents are stored in the private Supabase Storage bucket configured by `SUPABASE_STORAGE_BUCKET`, defaulting to `receipts`. The database stores metadata and storage paths; the app generates signed URLs when users need to view a file.

Conversation memory is user scoped. For production WhatsApp and web requests, the agent loads memory from `conversations` and `messages` by the resolved internal `users.id`; caller-supplied history is ignored unless it comes from an internal trusted workflow path.

Receipt extraction uses a human-in-the-loop gate by default. Valid uploads are saved privately in Supabase Storage and shown as pending in the web Saved history view, but invoice rows, line items, embeddings, and analytics are created only after WhatsApp approval. The same linked user must reply on WhatsApp with `APPROVE <upload_id>` / `REJECT <upload_id>`. Deletes are also guarded by exact confirmation commands such as `CONFIRM DELETE RECEIPT <id>` or `CONFIRM DELETE ALL`.

## Why Supabase Storage Instead Of S3

The app already uses Supabase Postgres, pgvector, and server-side Supabase credentials. Keeping receipt files in Supabase Storage means private file storage, signed links, metadata, row ownership, and vector-backed analytics live in one platform. This repo no longer contains an active S3 storage path.

## Setup

Full setup lives in [SETUP.md](SETUP.md). The minimum production services are:

| Service | Required For |
| --- | --- |
| Supabase Postgres | Users, receipts, generated invoices, pgvector embeddings, and migrations. |
| Supabase Storage | Private receipt and generated-invoice document storage. |
| Clerk | Web sign-in and WhatsApp account linking. |
| Twilio WhatsApp | Incoming WhatsApp text and media messages. |
| OpenAI | LLM responses, extraction, image/PDF interpretation, and embeddings. |
| Vercel | Hosted Flask app and public HTTPS webhook. |

Core environment variables:

```bash
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-1-<region>.pooler.supabase.com:6543/postgres
DIRECT_URL=postgresql://postgres.<project-ref>:<password>@aws-1-<region>.pooler.supabase.com:5432/postgres
NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
SUPABASE_SECRET_KEY=sb_secret_...
SUPABASE_STORAGE_BUCKET=receipts
HITL_CONFIRMATION_REQUIRED=true

NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
CLERK_REQUIRE_AUTH=true
CLERK_AUTHORIZED_PARTIES=https://whatsapp-invoice-assistant.vercel.app

OPENAI_API_KEY=sk-proj-...
OPENAI_API_MODEL=gpt-5.4-mini

TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=whatsapp:+1...
```

The two `NEXT_PUBLIC_SUPABASE_*` values are not enough for this app by themselves. The server-side webhook also needs `DATABASE_URL`, `DIRECT_URL`, and `SUPABASE_SECRET_KEY` because it writes SQL records, stores private files, runs migrations, and creates signed URLs.

Validate local env values before testing:

```bash
python3 scripts/validate_env.py --env-file .env
```

## Local Development

```bash
git clone https://github.com/Abby263/whatsapp-invoice-assistant.git
cd whatsapp-invoice-assistant
cp .env.example .env
poetry install
PYTHONPATH=. poetry run alembic upgrade head
make ui-run
```

Open [http://localhost:5001](http://localhost:5001).

For production-style webhook testing, configure Twilio to call the deployed Vercel URL:

```text
https://whatsapp-invoice-assistant.vercel.app/webhook
```

## Common Commands

```bash
make install              # Install Python dependencies and pre-commit hooks
make ui-run              # Start the local Flask operator UI on port 5001
make db-migrate          # Run Alembic migrations
make db-status           # Check database connectivity
make update-embeddings   # Backfill or refresh pgvector embeddings
make test                # Run the pytest suite
```

## Testing Checklist

1. Run `python3 scripts/validate_env.py --env-file .env`.
2. Run `PYTHONPATH=. poetry run alembic upgrade head`.
3. Confirm [https://whatsapp-invoice-assistant.vercel.app/health](https://whatsapp-invoice-assistant.vercel.app/health) reports `backend_enabled=true`.
4. Sign in with Clerk on the website.
5. Use **Link WhatsApp** and enter the WhatsApp number that will message the Twilio sender.
6. Send `Hi` on WhatsApp and confirm the assistant responds.
7. Send a receipt image or PDF and confirm WhatsApp returns `APPROVE <upload_id>` / `REJECT <upload_id>` commands and Saved history shows the upload as pending.
8. Reply `APPROVE <upload_id>` in WhatsApp and confirm the receipt moves into saved analytics.
9. Ask a question over the stored data, such as `What did I spend this month?`.
10. Generate an outgoing invoice and confirm it appears in generated invoices and analytics.

## Documentation

- [SETUP.md](SETUP.md): Production and local setup, env sourcing, Twilio webhook setup, and test plan.
- [docs/DATABASE.md](docs/DATABASE.md): Database schema and relationships.
- [docs/VECTOR_SEARCH.md](docs/VECTOR_SEARCH.md): pgvector and embedding behavior.
- [docs/TECH_STACK.md](docs/TECH_STACK.md): Current runtime stack and repository map.
- [CONTRIBUTING.md](CONTRIBUTING.md): Contribution workflow.

## License

This repository is licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE). It is available for noncommercial review, learning, evaluation, research, and contribution under the license terms.

Commercial use in any form is not permitted without a separate written commercial license from the copyright holder. This includes paid products, hosted services, client work, revenue-generating demos, resale, sublicensing, and use to support commercial operations.

AGPL was not used because AGPL permits commercial use; it only adds copyleft and network source-sharing obligations.
