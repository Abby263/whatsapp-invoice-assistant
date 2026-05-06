# Setup Guide

This guide covers the services, secrets, and commands required to run the WhatsApp Invoice Assistant locally or in a production-like environment.

## 1. Prerequisites

Install these tools locally:

| Tool | Version | Purpose |
| --- | --- | --- |
| Python | 3.9 or newer | Application runtime. |
| Poetry | Latest stable | Dependency management. |
| Git | Latest stable | Source control. |
| Supabase account | Any paid/free project | Postgres, pgvector, and receipt storage. |
| Clerk account | Any project | Web authentication and user identity. |
| OpenAI account | API access enabled | Chat model and embeddings. |
| Twilio account | WhatsApp sandbox or sender | WhatsApp webhook testing and production traffic. |
| MongoDB | Optional | Persistent conversation memory. |
| Redis | Optional | Background task infrastructure. |
| Docker | Optional | Containerized local stack. |

## 2. Clone and Install

```bash
git clone https://github.com/Abby263/whatsapp-invoice-assistant.git
cd whatsapp-invoice-assistant
cp .env.example .env
poetry install
```

If `poetry` is not installed:

```bash
pip install poetry
```

## 3. Supabase Setup

Supabase is the production storage platform for this project.

### 3.1 Create a Project

1. Go to [Supabase](https://supabase.com/).
2. Create a new project.
3. Save the project reference ID and database password.

### 3.2 Get the Database URL

In Supabase:

1. Open your project.
2. Go to `Project Settings` -> `Database`.
3. Copy a Postgres connection string.
4. Use either direct connection or pooler connection.

Direct connection format:

```env
DATABASE_URL=postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres
```

Pooler format:

```env
SUPABASE_DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-0-us-east-1.pooler.supabase.com:6543/postgres
```

The app resolves database configuration in this order:

1. `DATABASE_URL`
2. `SUPABASE_DATABASE_URL`
3. `SUPABASE_PROJECT_ID` plus `SUPABASE_DB_PASSWORD`

### 3.3 Enable pgvector

Open the Supabase SQL editor and run:

```sql
create extension if not exists vector;
```

The Alembic migrations also try to create the extension, but enabling it explicitly makes setup failures easier to diagnose.

### 3.4 Create the Receipt Storage Bucket

1. Go to `Storage`.
2. Create a bucket named `receipts`.
3. Keep the bucket private.
4. Store the bucket name in `.env`:

```env
SUPABASE_STORAGE_BUCKET=receipts
```

### 3.5 Get Supabase API Keys

Go to `Project Settings` -> `API`.

Use:

```env
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_KEY=<anon-public-key>
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
SUPABASE_PROJECT_ID=<project-ref>
SUPABASE_DB_PASSWORD=<database-password>
```

Important: `SUPABASE_SERVICE_ROLE_KEY` must only be used server-side. Do not expose it in client-side code.

## 4. OpenAI Setup

1. Go to [OpenAI API keys](https://platform.openai.com/api-keys).
2. Create a project API key.
3. Add it to `.env`:

```env
OPENAI_API_KEY=<your-openai-api-key>
OPENAI_API_MODEL=gpt-4o-mini
```

Embeddings use `text-embedding-3-small` in `utils/vector_utils.py` and `config/env.yaml`.

## 5. WhatsApp and Twilio Setup

The FastAPI webhook expects Twilio-style WhatsApp payload fields such as `From`, `Body`, `NumMedia`, and `MediaUrl0`.

### 5.1 Twilio Sandbox

1. Go to [Twilio Console](https://console.twilio.com/).
2. Open `Messaging` -> `Try it out` -> `Send a WhatsApp message`.
3. Join the sandbox from your WhatsApp device.
4. Copy:
   - Account SID
   - Auth Token
   - WhatsApp sandbox sender

Add:

```env
TWILIO_ACCOUNT_SID=<account-sid>
TWILIO_AUTH_TOKEN=<auth-token>
TWILIO_PHONE_NUMBER=whatsapp:+14155238886
```

### 5.2 Webhook URL

For local webhook testing, expose FastAPI with a secure tunnel such as ngrok:

```bash
poetry run uvicorn api.main:app --host 0.0.0.0 --port 8000
ngrok http 8000
```

Set the Twilio inbound webhook to:

```text
https://<your-ngrok-domain>/webhook
```

Use `POST` as the method.

### 5.3 Meta WhatsApp Cloud API Variables

`.env.example` also includes:

```env
WHATSAPP_PHONE_NUMBER_ID=<phone-number-id>
WHATSAPP_API_VERSION=v18.0
WHATSAPP_ACCESS_TOKEN=<meta-cloud-api-token>
```

These are useful if you extend the app to use Meta Cloud API directly. The current webhook path is Twilio-compatible.

## 6. Clerk Authentication Setup

Clerk is used for website sign-in. The app still stores receipts and invoices under the internal `users.id`, while Clerk provides the web identity. A signed-in user links their WhatsApp number once; after that, website activity and WhatsApp receipt uploads resolve to the same `users` row.

### 6.1 Create a Clerk Application

1. Go to [Clerk](https://clerk.com/).
2. Create an application.
3. Enable the sign-in methods you want, ideally phone number plus email so users can link the same WhatsApp number.
4. In Clerk Dashboard, open `Configure` -> `API keys`.
5. Copy the publishable key and secret key.

Add:

```env
CLERK_PUBLISHABLE_KEY=<clerk-publishable-key>
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=<clerk-publishable-key>
CLERK_SECRET_KEY=<clerk-secret-key>
CLERK_REQUIRE_AUTH=true
```

`NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` is included because Vercel/Clerk integrations commonly provision that name. The Flask UI also accepts `CLERK_PUBLISHABLE_KEY`.

### 6.2 Production Hardening

The backend verifies Clerk session JWTs using the Clerk JWKS endpoint. The issuer is derived from the publishable key by default. For stricter production configuration, set:

```env
CLERK_JWT_ISSUER=https://<your-clerk-frontend-api-domain>
CLERK_JWKS_URL=https://<your-clerk-frontend-api-domain>/.well-known/jwks.json
CLERK_AUTHORIZED_PARTIES=https://your-production-domain.com
```

For the current Vercel deployment, set:

```env
CLERK_AUTHORIZED_PARTIES=https://whatsapp-invoice-assistant.vercel.app
```

### 6.3 WhatsApp Link Flow

1. User signs in on the website with Clerk.
2. User clicks `Link WhatsApp`.
3. The app links `users.clerk_user_id` to the row with the same `users.whatsapp_number`.
4. WhatsApp uploads continue to use the phone number path.
5. Website dashboard queries use the Clerk-linked internal `users.id`.

This is the bridge that makes a receipt uploaded over WhatsApp visible to the same user in the web UI.

## 7. MongoDB Memory Setup

MongoDB is optional. It stores conversation memory and can back LangGraph checkpointing.

Local MongoDB:

```env
MONGODB_URI=mongodb://localhost:27017/whatsapp_invoice_assistant
USE_MONGODB=true
```

Run without MongoDB memory:

```env
USE_MONGODB=false
```

The local UI command already uses `USE_MONGODB=false` by default in the Makefile.

## 8. Redis Setup

Redis is optional for current local UI testing, but the project includes Celery/Redis dependencies for background work patterns.

```env
REDIS_URL=redis://localhost:6379/0
```

## 9. Complete `.env` Example

```env
DATABASE_URL=postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_KEY=<anon-key>
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
SUPABASE_PROJECT_ID=<project-ref>
SUPABASE_DB_PASSWORD=<database-password>
SUPABASE_STORAGE_BUCKET=receipts
SUPABASE_STORAGE_TIMEOUT=30

CLERK_PUBLISHABLE_KEY=<clerk-publishable-key>
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=<clerk-publishable-key>
CLERK_SECRET_KEY=<clerk-secret-key>
CLERK_REQUIRE_AUTH=true
CLERK_AUTHORIZED_PARTIES=https://whatsapp-invoice-assistant.vercel.app

OPENAI_API_KEY=<openai-api-key>
OPENAI_API_MODEL=gpt-4o-mini

TWILIO_ACCOUNT_SID=<twilio-account-sid>
TWILIO_AUTH_TOKEN=<twilio-auth-token>
TWILIO_PHONE_NUMBER=whatsapp:+14155238886

MONGODB_URI=mongodb://localhost:27017/whatsapp_invoice_assistant
USE_MONGODB=false

REDIS_URL=redis://localhost:6379/0
DEBUG=false
LOG_LEVEL=INFO
PORT=8000
HOST=0.0.0.0
```

## 10. Database Migration

Run migrations after configuring Supabase:

```bash
PYTHONPATH=. poetry run alembic upgrade head
```

Check database connectivity:

```bash
make db-status
```

Update embeddings after importing or backfilling invoice data:

```bash
make update-embeddings
```

## 11. Run Locally

### FastAPI Webhook API

```bash
make start
```

API health:

```bash
curl http://localhost:8000/health
```

### Operator UI

```bash
make ui-run
```

Open:

```text
http://localhost:5001
```

The UI can render in degraded mode when Supabase is unavailable, but upload, extraction, storage, and search require working Supabase and OpenAI credentials.

## 12. Vercel UI Deployment

The repository includes a Vercel-compatible Flask entrypoint in `app.py`. This deployment is intentionally lightweight and serves the operator UI in demo mode. It is useful for README demos and product review, while the full WhatsApp processing backend should run with the production services listed above.

Current public UI:

```text
https://whatsapp-invoice-assistant.vercel.app
```

Deploy from the repository root:

```bash
npx vercel deploy --prod --scope <vercel-team-or-user-scope>
```

Vercel uses:

- `app.py` for the hosted UI/demo routes.
- `requirements.txt` for minimal hosted UI dependencies.
- `vercel.json` for the Flask project preset.
- `.vercelignore` to exclude local databases, secrets, tests, generated files, and heavyweight backend modules from the UI bundle.

For a fully functional hosted production system, configure the same Supabase, OpenAI, Twilio, MongoDB, and Redis variables in Vercel or deploy the FastAPI/LangGraph backend on a Python service that supports longer-running workers.

## 13. Docker Setup

Build and run:

```bash
make docker-build
make docker-run
```

Or use compose directly:

```bash
docker-compose up --build
```

The compose file includes local Postgres and MongoDB containers for development. Production deployments should use managed Supabase Postgres, Supabase Storage, and a managed MongoDB service if persistent memory is needed.

## 14. Production Deployment Checklist

- Use managed Supabase Postgres with automated backups.
- Enable `vector` in Supabase.
- Keep the receipt bucket private.
- Store `SUPABASE_SERVICE_ROLE_KEY`, `OPENAI_API_KEY`, and Twilio secrets in your platform secret manager.
- Restrict CORS in `api/main.py` to trusted origins.
- Put the API behind HTTPS.
- Configure Twilio webhook retries and monitor non-2xx responses.
- Add API request logging with secret redaction.
- Configure alerting for storage upload failures, extraction failures, and embedding failures.
- Run Alembic migrations in CI/CD before app rollout.
- Use separate Supabase projects for development, staging, and production.

## 15. Troubleshooting

### `No Supabase connection details found`

Set one of:

- `DATABASE_URL`
- `SUPABASE_DATABASE_URL`
- `SUPABASE_PROJECT_ID` and `SUPABASE_DB_PASSWORD`

### `could not translate host name db.<project>.supabase.co`

Your runtime cannot resolve the Supabase hostname. Check network access, DNS, VPN, and whether the project reference is correct.

### `Supabase Storage upload failed`

Check:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_STORAGE_BUCKET`
- Whether the bucket exists
- Whether the key belongs to the same Supabase project

### Embeddings are missing

Check:

- `OPENAI_API_KEY`
- OpenAI account billing and project access
- The `vector` extension
- The embedding update logs from `make update-embeddings`

### WhatsApp webhook does not receive messages

Check:

- Twilio sandbox join status
- Public HTTPS webhook URL
- Twilio webhook method is `POST`
- FastAPI is reachable at `/webhook`
- Server logs in `logs/api.log`
