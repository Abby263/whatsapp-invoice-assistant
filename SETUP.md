# Setup Guide

This guide covers the services, secrets, and commands required to run the WhatsApp Invoice Assistant locally or in a production-like environment.

## Current Deployment Mode

The public Vercel URL is:

```text
https://whatsapp-invoice-assistant.vercel.app
```

That deployment currently serves the hosted UI through `app.py`. It is useful for UI review and demo-mode flows, but it is not a full production backend by itself. Real receipt upload, extraction, Supabase persistence, embeddings, Clerk user scoping, WhatsApp webhook processing, and generated invoice persistence need the real service configuration described below.

Before real-time testing, verify which mode you are in:

```bash
curl https://whatsapp-invoice-assistant.vercel.app/health
curl https://whatsapp-invoice-assistant.vercel.app/api/generated-invoices
npx vercel env ls
```

If `/health` returns `{"runtime":"vercel-ui-demo","status":"ok"}` and `npx vercel env ls` shows no variables, the deployment is still demo-only.

## Real-Time Testing Readiness

You are ready to test real data only after all of these are true:

| Area | Required before real-time testing |
| --- | --- |
| Supabase Postgres | `DATABASE_URL` or `SUPABASE_DATABASE_URL` points to the target Supabase database, or `SUPABASE_DB_PASSWORD` is set with the Supabase URL/project ref. |
| Migrations | `PYTHONPATH=. poetry run alembic upgrade head` has completed successfully. |
| pgvector | `create extension if not exists vector;` has run in Supabase SQL editor. |
| Supabase Storage | Private `receipts` bucket exists and `SUPABASE_SECRET_KEY` or `SUPABASE_SERVICE_ROLE_KEY` can write to it. |
| OpenAI | `OPENAI_API_KEY` is set and the account has access/billing for chat and embeddings. |
| Clerk | Publishable/secret keys are set, `CLERK_REQUIRE_AUTH=true`, and authorized parties include the live URL. |
| WhatsApp/Twilio | Twilio inbound webhook points to a publicly reachable `/webhook` endpoint. |
| Real backend | The Flask UI from `ui/app.py` or the FastAPI backend from `api/main.py` is deployed with the production env vars. |

Testing scope by deployment:

| Target | What you can test |
| --- | --- |
| Current Vercel `app.py` deployment | UI, theme, navigation, demo chat, demo generated invoices. Data is in memory and not durable. |
| Local `ui/app.py` with `.env` | Receipt upload, extraction, Supabase storage, generated invoices, dashboard analytics, Clerk link flow if configured. |
| FastAPI `api/main.py` with public HTTPS URL | Twilio WhatsApp webhook, text messages, media downloads, file processing workflow. |
| Full production | Website + WhatsApp using the same Supabase database and the same `users.id` mapping. |

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
4. `SUPABASE_URL` or `NEXT_PUBLIC_SUPABASE_URL` plus `SUPABASE_DB_PASSWORD`

The Supabase project URL and publishable key are API settings, not database credentials. For real testing you still need one database credential path above.

### 3.3 Enable pgvector

Open the Supabase SQL editor and run:

```sql
create extension if not exists vector;
```

The Alembic migrations also try to create the extension, but enabling it explicitly makes setup failures easier to diagnose.

### 3.4 Create the Receipt and Generated-Invoice Storage Bucket

1. Go to `Storage`.
2. Create a bucket named `receipts`.
3. Keep the bucket private.
4. Store the bucket name in `.env`:

```env
SUPABASE_STORAGE_BUCKET=receipts
```

The same private bucket stores original receipt uploads and generated outgoing invoice documents. Object paths are user-scoped:

- `<user-id>/invoices/...` for uploaded receipt files.
- `<user-id>/generated-invoices/...` for generated invoice DOCX/PDF files.

Local development can fall back to `ui/uploads` if Supabase Storage is missing. Production runtimes such as Vercel fail invoice generation clearly when storage is not configured because local files are not durable.

### 3.5 Get Supabase API Keys

Go to `Project Settings` -> `API`.

Use:

```env
SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_KEY=<anon-or-publishable-key>
SUPABASE_PUBLISHABLE_KEY=<sb_publishable_...>
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<sb_publishable_...>
SUPABASE_SERVICE_ROLE_KEY=<legacy-service-role-key-if-shown>
SUPABASE_SECRET_KEY=<sb_secret_...>
SUPABASE_PROJECT_ID=<project-ref>
SUPABASE_DB_PASSWORD=<database-password>
```

Important: `SUPABASE_SERVICE_ROLE_KEY` and `SUPABASE_SECRET_KEY` must only be used server-side. Do not expose either key in client-side code or a `NEXT_PUBLIC_*` variable. The app accepts `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` for compatibility, but private bucket uploads and signed URLs should use `SUPABASE_SECRET_KEY` or `SUPABASE_SERVICE_ROLE_KEY` in production.

## 4. OpenAI Setup

1. Go to [OpenAI API keys](https://platform.openai.com/api-keys).
2. Create a project API key.
3. Add it to `.env`:

```env
OPENAI_API_KEY=<your-openai-api-key>
OPENAI_API_MODEL=gpt-5.4-mini
```

The code now reads `OPENAI_API_MODEL` for chat and image extraction. Make sure your OpenAI project has access to the model ID you configure. Embeddings use `text-embedding-3-small` in `utils/vector_utils.py`; copy `config/env.yaml.example` to ignored `config/env.yaml` only if you prefer YAML-based local overrides.

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

`whatsapp:+14155238886` is Twilio's sandbox sender. Use it only while testing inside the sandbox.

### 5.2 Use a Purchased Twilio Number for WhatsApp

A purchased Twilio phone number can be used only after it is approved/onboarded as a WhatsApp sender. Buying an SMS/voice number is not enough by itself.

1. In Twilio Console, open `Messaging` -> `Senders` -> `WhatsApp senders`.
2. Start the WhatsApp sender onboarding flow.
3. Choose or register the purchased Twilio number you want to use.
4. Complete Meta Business/WhatsApp Business approval if Twilio asks for it.
5. After the sender is approved, set:

```env
TWILIO_PHONE_NUMBER=whatsapp:+1<your-approved-twilio-number>
```

Keep the `whatsapp:` prefix. Inbound webhook payloads will still use `From=whatsapp:+<customer-number>` and `To=whatsapp:+<your-approved-twilio-number>`.

### 5.3 Webhook URL

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

For production, the webhook URL should point to the real backend host, not the current Vercel demo UI:

```text
https://<your-backend-domain>/webhook
```

The current `https://whatsapp-invoice-assistant.vercel.app` deployment is a hosted UI demo unless you deploy the FastAPI backend/runtime behind it.

### 5.4 Meta WhatsApp Cloud API Variables

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

## 7. Generated Invoice Setup

Outgoing invoice generation uses the same services already required by receipt processing:

| Requirement | Why it is needed |
| --- | --- |
| Supabase Postgres migrations | Creates `generated_invoices` and `generated_invoice_items`. |
| Supabase Storage | Stores generated invoice DOCX/PDF files in a private bucket. |
| Clerk or WhatsApp user mapping | Ensures generated invoices belong to the same internal `users.id` as uploaded receipts. |
| Company profile defaults | Reuses seller, client, currency, tax, and payment terms across WhatsApp and website generation. |

Run migrations after pulling this feature:

```bash
PYTHONPATH=. poetry run alembic upgrade head
```

In the website, open `Settings` -> `Company profile` to save reusable seller/client defaults. Users can also save defaults from the **Generate invoice** form. WhatsApp invoice requests reuse those defaults automatically once the sender's WhatsApp number resolves to the same user row.

Production note: generated invoice files must use Supabase Storage. The local `ui/uploads` fallback is only for development and should not be used as a durable production store.

## 8. MongoDB Memory Setup

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

## 9. Redis Setup

Redis is optional for current local UI testing, but the project includes Celery/Redis dependencies for background work patterns.

```env
REDIS_URL=redis://localhost:6379/0
```

## 10. Complete `.env` Example

```env
DATABASE_URL=postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres
SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_KEY=<anon-or-publishable-key>
SUPABASE_PUBLISHABLE_KEY=<sb_publishable_...>
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<sb_publishable_...>
SUPABASE_SECRET_KEY=<sb_secret_...>
SUPABASE_SERVICE_ROLE_KEY=<legacy-service-role-key-if-shown>
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
OPENAI_API_MODEL=gpt-5.4-mini

TWILIO_ACCOUNT_SID=<twilio-account-sid>
TWILIO_AUTH_TOKEN=<twilio-auth-token>
TWILIO_PHONE_NUMBER=whatsapp:+1<approved-twilio-whatsapp-sender>

MONGODB_URI=mongodb://localhost:27017/whatsapp_invoice_assistant
USE_MONGODB=false

REDIS_URL=redis://localhost:6379/0
DEBUG=false
LOG_LEVEL=INFO
PORT=8000
HOST=0.0.0.0
```

### 10.1 Required Production Variables

For real-time testing, these variables are mandatory in whichever runtime hosts the real backend:

| Variable | Required for | Notes |
| --- | --- | --- |
| `DATABASE_URL` or `SUPABASE_DATABASE_URL` | Database | Use the Supabase Postgres direct or pooler connection string. Required unless `SUPABASE_DB_PASSWORD` is provided with a Supabase URL/project ref. |
| `SUPABASE_URL` or `NEXT_PUBLIC_SUPABASE_URL` | Storage | Supabase project URL, for example `https://<project-ref>.supabase.co`. |
| `SUPABASE_SECRET_KEY` or `SUPABASE_SERVICE_ROLE_KEY` | Storage and private server access | Server-side only. Required for private bucket uploads and signed URLs. |
| `SUPABASE_PUBLISHABLE_KEY` or `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Public Supabase API access | Accepted as a fallback, but not recommended for private server storage operations. |
| `SUPABASE_STORAGE_BUCKET` | Storage | Use `receipts` unless you created a different bucket. |
| `OPENAI_API_KEY` | Extraction, chat, embeddings | Required for real agent execution. |
| `OPENAI_API_MODEL` | Chat and image extraction | Set to `gpt-5.4-mini` if your OpenAI project has access. |
| `CLERK_PUBLISHABLE_KEY` | Web auth | Browser key for the Clerk sign-in UI. |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Web auth | Same value as `CLERK_PUBLISHABLE_KEY`; useful for Vercel/Clerk conventions. |
| `CLERK_SECRET_KEY` | Web auth | Server-side key. |
| `CLERK_REQUIRE_AUTH` | Web auth | Set `true` for user-level receipt and invoice isolation. |
| `CLERK_AUTHORIZED_PARTIES` | Web auth | Include `https://whatsapp-invoice-assistant.vercel.app` and local URLs used for testing. |
| `TWILIO_ACCOUNT_SID` | WhatsApp | Required when Twilio downloads media or sends responses. |
| `TWILIO_AUTH_TOKEN` | WhatsApp | Required for authenticated Twilio media URLs. |
| `TWILIO_PHONE_NUMBER` | WhatsApp | Twilio WhatsApp sender, for example sandbox `whatsapp:+14155238886` or approved sender `whatsapp:+1...`. |
| `USE_MONGODB` | Memory | Set `false` unless MongoDB is configured and reachable. |
| `MONGODB_URI` | Memory | Required only when `USE_MONGODB=true`. |
| `REDIS_URL` | Background jobs | Optional for current local testing. |

For local development, keep these in `.env`. For Vercel or another host, add them in that platform's environment variable manager and redeploy.

### 10.2 Using Supabase/Vercel-Style Variable Names

The runtime accepts these aliases:

| Existing app name | Also accepted |
| --- | --- |
| `SUPABASE_URL` | `NEXT_PUBLIC_SUPABASE_URL` |
| `SUPABASE_KEY` | `SUPABASE_PUBLISHABLE_KEY`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_ANON_KEY`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` |
| `SUPABASE_SERVICE_ROLE_KEY` | `SUPABASE_SECRET_KEY` |
| `CLERK_PUBLISHABLE_KEY` | `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` |

If your Vercel project currently has only `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, add at least one database credential and one server-side storage/admin key before real receipt testing:

```env
# Database, choose one:
DATABASE_URL=<supabase-postgres-url>
SUPABASE_DATABASE_URL=<supabase-pooler-url>
# or
SUPABASE_DB_PASSWORD=<supabase-database-password>

# Private storage/admin access:
SUPABASE_SECRET_KEY=<sb_secret_...>
# or legacy:
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
```

Also set `CLERK_REQUIRE_AUTH=true` in production when receipts and generated invoices must be user-scoped.

## 11. Database Migration

Run migrations after configuring Supabase:

```bash
PYTHONPATH=. poetry run alembic upgrade head
```

Confirm the generated-invoice tables exist in Supabase SQL editor:

```sql
select table_name
from information_schema.tables
where table_schema = 'public'
  and table_name in (
    'users',
    'invoices',
    'items',
    'generated_invoices',
    'generated_invoice_items',
    'invoice_embeddings'
  )
order by table_name;
```

Check database connectivity:

```bash
make db-status
```

Update embeddings after importing or backfilling invoice data:

```bash
make update-embeddings
```

## 12. Run Locally

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

### 12.1 Local Full-Flow Smoke Tests

Run these before testing with real users:

```bash
# Database and migrations
PYTHONPATH=. poetry run alembic current
PYTHONPATH=. poetry run alembic upgrade head

# API health
curl http://localhost:8000/health

# UI health
curl http://localhost:5001/api/db-status?user_id=1
curl http://localhost:5001/api/generated-invoices?user_id=1
```

Then test in the UI:

1. Open `http://localhost:5001`.
2. Create or select a user.
3. Open `Settings` -> `Company profile` and save seller defaults.
4. Open `Receipts` -> `Generate invoice`, create an invoice, and confirm it appears in `Generated invoices`.
5. Upload a sample PDF or image receipt.
6. Confirm the file appears in Supabase Storage under `<user-id>/invoices/...`.
7. Ask a chat question such as `What did I spend this month?`.

Generated invoice files should appear in Supabase Storage under:

```text
<user-id>/generated-invoices/...
```

Receipt upload files should appear under:

```text
<user-id>/invoices/...
```

### 12.2 WhatsApp Real-Time Smoke Test

After the FastAPI backend is public over HTTPS and Twilio points to `/webhook`:

1. Send a plain WhatsApp message to the Twilio sandbox.
2. Confirm the backend logs show `Received webhook`.
3. Send a receipt PDF or image through WhatsApp.
4. Confirm Supabase Storage has a new `<user-id>/invoices/...` object.
5. Confirm Supabase Postgres has new `invoices`, `items`, and embedding rows.
6. Sign in to the website with Clerk.
7. Link the same WhatsApp number.
8. Confirm the web dashboard shows the same user's receipts and generated invoices.
9. Ask WhatsApp to generate an outgoing invoice.
10. Confirm Supabase Storage has `<user-id>/generated-invoices/...` and Postgres has a `generated_invoices` row.

## 13. Vercel UI Deployment

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

### 13.1 Vercel Environment Variables

Check whether Vercel has production variables configured:

```bash
npx vercel env ls
```

Add required variables to production:

```bash
npx vercel env add DATABASE_URL production
npx vercel env add SUPABASE_URL production
npx vercel env add NEXT_PUBLIC_SUPABASE_URL production
npx vercel env add SUPABASE_SECRET_KEY production
npx vercel env add SUPABASE_SERVICE_ROLE_KEY production
npx vercel env add SUPABASE_PUBLISHABLE_KEY production
npx vercel env add NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY production
npx vercel env add SUPABASE_STORAGE_BUCKET production
npx vercel env add OPENAI_API_KEY production
npx vercel env add OPENAI_API_MODEL production
npx vercel env add CLERK_PUBLISHABLE_KEY production
npx vercel env add NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY production
npx vercel env add CLERK_SECRET_KEY production
npx vercel env add CLERK_REQUIRE_AUTH production
npx vercel env add CLERK_AUTHORIZED_PARTIES production
```

If you only have the Supabase values from `Project Settings` -> `API`, add one of these database options too:

```bash
npx vercel env add DATABASE_URL production
# or
npx vercel env add SUPABASE_DATABASE_URL production
# or, if the code should derive the project ref from NEXT_PUBLIC_SUPABASE_URL:
npx vercel env add SUPABASE_DB_PASSWORD production
```

For private receipt storage, add `SUPABASE_SECRET_KEY` or `SUPABASE_SERVICE_ROLE_KEY`. `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` is safe for browsers, but should not be the only key configured for server-side private storage.

Only add Twilio and MongoDB variables to Vercel if the Vercel app is changed to run the real backend paths:

```bash
npx vercel env add TWILIO_ACCOUNT_SID production
npx vercel env add TWILIO_AUTH_TOKEN production
npx vercel env add TWILIO_PHONE_NUMBER production
npx vercel env add USE_MONGODB production
npx vercel env add MONGODB_URI production
npx vercel env add REDIS_URL production
```

Redeploy after changing env vars:

```bash
npx vercel redeploy --prod
```

### 13.2 Important Vercel Limitation

The current Vercel deployment is wired to `app.py`, which returns demo responses for receipt upload, generated invoices, database counts, and embeddings. Setting env vars alone does not make this Vercel deployment process real WhatsApp receipts.

For full production testing, choose one of these approaches:

1. Deploy `ui/app.py` as the real web UI with the env vars above, then use that URL for Clerk web testing.
2. Deploy `api/main.py` as the public FastAPI backend for Twilio webhooks.
3. Keep Vercel as the public demo UI and run the real backend elsewhere until the Vercel entrypoint is refactored from demo mode to production mode.

For WhatsApp real-time testing, Twilio must call the FastAPI `/webhook` endpoint, not the demo Vercel UI.

## 14. Docker Setup

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

## 15. Production Deployment Checklist

- Use managed Supabase Postgres with automated backups.
- Enable `vector` in Supabase.
- Keep the receipt bucket private.
- Store `SUPABASE_SECRET_KEY` or `SUPABASE_SERVICE_ROLE_KEY`, `OPENAI_API_KEY`, and Twilio secrets in your platform secret manager.
- Restrict CORS in `api/main.py` to trusted origins.
- Put the API behind HTTPS.
- Configure Twilio webhook retries and monitor non-2xx responses.
- Add API request logging with secret redaction.
- Configure alerting for storage upload failures, extraction failures, and embedding failures.
- Run Alembic migrations in CI/CD before app rollout.
- Use separate Supabase projects for development, staging, and production.

## 16. Troubleshooting

### `No Supabase connection details found`

Set one of:

- `DATABASE_URL`
- `SUPABASE_DATABASE_URL`
- `SUPABASE_PROJECT_ID` and `SUPABASE_DB_PASSWORD`
- `SUPABASE_URL` or `NEXT_PUBLIC_SUPABASE_URL` plus `SUPABASE_DB_PASSWORD`

### `could not translate host name db.<project>.supabase.co`

Your runtime cannot resolve the Supabase hostname. Check network access, DNS, VPN, and whether the project reference is correct.

### `Supabase Storage upload failed`

Check:

- `SUPABASE_URL` or `NEXT_PUBLIC_SUPABASE_URL`
- `SUPABASE_SECRET_KEY` or `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_STORAGE_BUCKET`
- Whether the bucket exists
- Whether the key belongs to the same Supabase project

### Generated invoices are not saved

Check:

- `generated_invoices` and `generated_invoice_items` tables exist.
- `SUPABASE_SECRET_KEY` or `SUPABASE_SERVICE_ROLE_KEY` is set in the runtime that generates the invoice.
- `SUPABASE_STORAGE_BUCKET=receipts` points to an existing private bucket.
- The runtime is not the Vercel demo `app.py` route. Demo generated invoices are in memory only.
- Production logs do not show `Generated invoice storage is not available`.

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

### Vercel shows demo responses

This is expected while Vercel is serving `app.py`. The demo app returns `degraded: true` for generated invoices and database status. To test real data, run `ui/app.py` locally with `.env` or deploy the real Flask UI/backend paths with production environment variables.
