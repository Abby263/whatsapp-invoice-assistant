# Setup Guide

This guide is for running the WhatsApp Invoice Assistant end to end with the current Vercel deployment, Supabase, Clerk, OpenAI, and Twilio WhatsApp.

## Production URLs

Hosted app:

```text
https://whatsapp-invoice-assistant.vercel.app
```

Twilio incoming WhatsApp webhook:

```text
https://whatsapp-invoice-assistant.vercel.app/webhook
```

Use `POST` for the webhook method. Do not use an ngrok URL for production Twilio traffic.

Quick checks:

```bash
curl https://whatsapp-invoice-assistant.vercel.app/health

curl -i -X POST https://whatsapp-invoice-assistant.vercel.app/webhook \
  --data-urlencode 'From=whatsapp:+15551234567' \
  --data-urlencode 'To=whatsapp:+1<your-twilio-whatsapp-sender>' \
  --data-urlencode 'Body=Hey' \
  --data-urlencode 'NumMedia=0'
```

Expected webhook result:

- HTTP `200`
- `content-type: application/xml`
- response body starts with `<Response><Message>...`

## Required Services

| Service | Used for |
| --- | --- |
| Vercel | Hosted web UI and Flask webhook/API routes in `app.py`. |
| Supabase Postgres | Users, receipts, extracted invoice data, generated invoices, and pgvector embeddings. |
| Supabase Storage | Private storage for uploaded receipts and generated invoice documents. |
| Clerk | Website authentication with verified phone-number ownership. |
| OpenAI | Intent routing, extraction, responses, and embeddings. |
| Twilio WhatsApp | Incoming WhatsApp text/media webhooks. |

## Required Environment Variables

Set these in Vercel production and in local `.env` when testing locally.

```env
DATABASE_URL=postgresql://postgres.<project-ref>:<encoded-password>@aws-1-us-west-2.pooler.supabase.com:6543/postgres
DIRECT_URL=postgresql://postgres.<project-ref>:<encoded-password>@aws-1-us-west-2.pooler.supabase.com:5432/postgres

NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<sb_publishable_...>
SUPABASE_SECRET_KEY=<sb_secret_...>
SUPABASE_STORAGE_BUCKET=receipts
AUTO_CREATE_DATABASE_SCHEMA=true

NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=<clerk-publishable-key>
CLERK_SECRET_KEY=<clerk-secret-key>
CLERK_REQUIRE_AUTH=true
CLERK_AUTHORIZED_PARTIES=https://whatsapp-invoice-assistant.vercel.app

OPENAI_API_KEY=<openai-api-key>
OPENAI_API_MODEL=gpt-5.4-mini

TWILIO_ACCOUNT_SID=<twilio-account-sid>
TWILIO_AUTH_TOKEN=<twilio-auth-token>
TWILIO_PHONE_NUMBER=whatsapp:+1<approved-twilio-whatsapp-sender>
TWILIO_VALIDATE_REQUESTS=true
TWILIO_OUTBOUND_MESSAGES_ENABLED=true
TWILIO_PROCESSING_ACK_ENABLED=true
TWILIO_PROCESSING_ACK_COOLDOWN_SECONDS=75
TWILIO_PROCESSING_ACK_DATABASE_DEDUPE_ENABLED=true
TWILIO_MEDIA_FINAL_REPLY_ENABLED=true

HITL_CONFIRMATION_REQUIRED=true
CLERK_STEP_UP_MAX_AGE_SECONDS=300
CONVERSATION_MEMORY_WINDOW_MESSAGES=12
CONVERSATION_MEMORY_MAX_STORED_MESSAGES=200

RATE_LIMITS_ENABLED=true
RATE_LIMIT_WINDOW_SECONDS=86400
RATE_LIMIT_TEXT_TURNS_PER_WINDOW=500
RATE_LIMIT_MEDIA_UPLOADS_PER_WINDOW=100
RATE_LIMIT_APPROVALS_PER_WINDOW=200
RATE_LIMIT_EMBEDDINGS_PER_WINDOW=1000

ASYNC_WORK_QUEUE_ENABLED=false
ASYNC_INLINE_MEDIA_LIMIT=3
ASYNC_JOB_SECRET=<long-random-secret-for-job-runner>

DEPLOYMENT_SMOKE_BASE_URL=https://whatsapp-invoice-assistant.vercel.app
DEPLOYMENT_SMOKE_TIMEOUT_SECONDS=10
```

Notes:

- `DATABASE_URL` is for runtime. Use the Supabase pooler URL for Vercel/serverless.
- `DIRECT_URL` is for migrations.
- If the database password contains reserved URL characters, encode them before placing it in `DATABASE_URL` or `DIRECT_URL`. For example, `@` becomes `%40`.
- `SUPABASE_SECRET_KEY` is server-side only. Never expose it as a `NEXT_PUBLIC_*` variable.
- `SUPABASE_SERVICE_ROLE_KEY` is accepted as a legacy fallback if your Supabase project does not show `SUPABASE_SECRET_KEY`.
- `TWILIO_PHONE_NUMBER` must be the WhatsApp-enabled sender, with the `whatsapp:` prefix.
- `TWILIO_VALIDATE_REQUESTS=true` validates Twilio signatures on incoming webhooks. It is required in production and defaults on when the live backend is enabled; set it to `false` only for controlled local tunnel testing.
- `TWILIO_PROCESSING_ACK_COOLDOWN_SECONDS` prevents repeated "processing" acknowledgements when WhatsApp/Twilio splits a multi-image forward into multiple one-file webhooks.
- `TWILIO_PROCESSING_ACK_DATABASE_DEDUPE_ENABLED` stores that acknowledgement claim in Postgres so the cooldown still works when Vercel handles the rapid webhooks on different function instances.
- `TWILIO_MEDIA_FINAL_REPLY_ENABLED` sends the final media processing summary as an outbound Twilio message, which is more reliable than waiting for a long-running webhook response.
- `HITL_CONFIRMATION_REQUIRED=true` keeps extracted receipt rows out of `invoices`, `items`, and embeddings until the user replies on WhatsApp with `APPROVE <upload_id>`. `REJECT <upload_id>` discards the pending upload. Delete requests require exact `CONFIRM DELETE ...` commands.
- `CLERK_STEP_UP_MAX_AGE_SECONDS` controls how fresh the Clerk session token must be before optional browser approval can finalize a pending upload.
- `CONVERSATION_MEMORY_WINDOW_MESSAGES` controls how many recent user/assistant messages are passed back into the agent for multi-turn context.
- `CONVERSATION_MEMORY_MAX_STORED_MESSAGES` caps stored messages per active user conversation before older messages are pruned.
- Conversation memory is always loaded by internal `users.id` for production user-scoped requests. Do not send browser/client-provided conversation history to the backend as a source of truth.
- `RATE_LIMIT_*` settings enforce per-user rolling-window limits for text turns, media uploads, approval finalization, and embeddings.
- `ASYNC_WORK_QUEUE_ENABLED=true` queues large media batches instead of processing every attachment inside the Twilio webhook. Run queued jobs through `POST /api/jobs/run` with `ASYNC_JOB_SECRET`.
- `DEPLOYMENT_SMOKE_*` settings are used by `scripts/deployment_smoke.py`.

Optional local-only variables:

```env
DEBUG=false
LOG_LEVEL=INFO
PORT=8000
HOST=0.0.0.0
```

## Supabase Setup

### 1. Create Project

1. Open Supabase.
2. Create or open the project used by this app.
3. Copy the project ref from the project URL: `https://<project-ref>.supabase.co`.
4. Open `Project Settings` -> `Database` and copy/reset the database password.

### 2. Configure Database URLs

Use the Supabase pooler connection string for Vercel runtime:

```env
DATABASE_URL=postgresql://postgres.<project-ref>:<encoded-password>@aws-1-us-west-2.pooler.supabase.com:6543/postgres
```

Use the direct/session connection string for migrations:

```env
DIRECT_URL=postgresql://postgres.<project-ref>:<encoded-password>@aws-1-us-west-2.pooler.supabase.com:5432/postgres
```

If Supabase includes `?pgbouncer=true`, the app strips it for Python runtime compatibility, but it is cleaner to omit it.

### 3. Enable pgvector

Open Supabase SQL Editor and run:

```sql
create extension if not exists vector;
```

### 4. Run Migrations

From the repository root:

```bash
PYTHONPATH=. poetry run alembic upgrade head
```

Confirm core tables exist:

```sql
select table_name
from information_schema.tables
where table_schema = 'public'
  and table_name in (
    'users',
    'invoices',
    'items',
    'media',
    'invoice_embeddings',
    'generated_invoices',
    'generated_invoice_items'
  )
order by table_name;
```

### 5. Configure Storage

1. Open `Storage`.
2. Create a private bucket named `receipts`.
3. Set:

```env
SUPABASE_STORAGE_BUCKET=receipts
```

Storage paths are user-scoped:

- Uploaded receipts: `<user-id>/invoices/...`
- Generated invoice files: `<user-id>/generated-invoices/...`

## OpenAI Setup

1. Open the OpenAI dashboard.
2. Create an API key for this project.
3. Set:

```env
OPENAI_API_KEY=<openai-api-key>
OPENAI_API_MODEL=gpt-5.4-mini
```

The configured model handles chat, intent routing, and image/text extraction. Embeddings use `text-embedding-3-small`.

## Clerk Setup

1. Create a Clerk application.
2. Enable phone-number sign-in and sign-up, and disable email-only sign-in for this app.
3. Open `Configure` -> `API keys`.
4. Set:

```env
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=<clerk-publishable-key>
CLERK_SECRET_KEY=<clerk-secret-key>
CLERK_REQUIRE_AUTH=true
CLERK_REQUIRE_VERIFIED_PHONE=true
CLERK_AUTHORIZED_PARTIES=https://whatsapp-invoice-assistant.vercel.app
```

How account identity works:

1. User signs in or signs up on the website with a phone-number OTP.
2. The backend fetches the canonical Clerk user profile with `CLERK_SECRET_KEY`.
3. The app only creates or links an internal `users` row when Clerk returns a verified phone number.
4. The verified phone number becomes the user's WhatsApp account number.
5. Website receipts, WhatsApp uploads, generated invoices, and analytics resolve to the same `users.id`.

## Twilio WhatsApp Setup

### 1. Use an Approved WhatsApp Sender

A purchased Twilio phone number only works for WhatsApp after it is onboarded and approved as a WhatsApp sender.

1. Open Twilio Console.
2. Go to `Messaging` -> `Senders` -> `WhatsApp senders`.
3. Open the approved sender, for example `whatsapp:+1...`.
4. Set `Webhook URL for incoming messages` / `When a message comes in` to:

```text
https://whatsapp-invoice-assistant.vercel.app/webhook
```

5. Set method to `POST`.
6. Save.

Set the sender in Vercel:

```env
TWILIO_PHONE_NUMBER=whatsapp:+1<approved-twilio-whatsapp-sender>
```

### 2. Update the Messaging Service

If the WhatsApp sender is attached to a Twilio Messaging Service, update the service webhook too. When Twilio Request Inspector shows a `MessagingServiceSid`, this Messaging Service integration is the webhook path Twilio is using.

1. Open Twilio Console.
2. Go to `Messaging` -> `Services`.
3. Open the service, for example `Invoice Assistant`.
4. Open `Integration`.
5. Under incoming messages, set `Request URL` / `Send a webhook` to:

```text
https://whatsapp-invoice-assistant.vercel.app/webhook
```

6. Set method to `POST`.
7. Save.

### 3. Verify Twilio Delivery

Send `Hey` to your Twilio WhatsApp number. In Twilio Message Details -> Request Inspector, verify:

| Field | Expected value |
| --- | --- |
| URL | `https://whatsapp-invoice-assistant.vercel.app/webhook` |
| Product | Programmable SMS / WhatsApp |
| HTTP status | `200` |
| Response content type | `application/xml` |
| Response body | TwiML `<Response><Message>...` |

If Twilio shows `11200` and the URL is an old ngrok domain, the webhook is still configured incorrectly. Replace every inbound WhatsApp webhook URL with the Vercel webhook above.

For media uploads, the app sends a short processing acknowledgement first and then sends the extraction summary as a separate outbound Twilio message. If several images are forwarded together and Twilio delivers them as separate webhooks, the acknowledgement is rate-limited per sender while each file still gets processed.

How to read multi-image results:

- A `Document Review`, `Document Saved`, or `Document Not Processed` message is for one file only.
- A `Batch Processing Result` message is only for attachments Twilio delivered inside the same webhook.
- If six images are forwarded and Twilio splits them, expect six final file-status messages.
- Every processed financial document reply uses business labels such as `File`, `Type`, `Vendor`, `Date`, `Total`, `Entries`, and `Action Needed`.
- Non-financial images receive `Document Not Processed` with a clear reason and are not stored as expenses.

## Vercel Setup

### 1. Link Project

From the repository root:

```bash
npx vercel link
```

### 2. Add Production Env Vars

```bash
npx vercel env add DATABASE_URL production
npx vercel env add DIRECT_URL production
npx vercel env add NEXT_PUBLIC_SUPABASE_URL production
npx vercel env add NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY production
npx vercel env add SUPABASE_SECRET_KEY production
npx vercel env add SUPABASE_STORAGE_BUCKET production
npx vercel env add NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY production
npx vercel env add CLERK_SECRET_KEY production
npx vercel env add CLERK_REQUIRE_AUTH production
npx vercel env add CLERK_AUTHORIZED_PARTIES production
npx vercel env add OPENAI_API_KEY production
npx vercel env add OPENAI_API_MODEL production
npx vercel env add TWILIO_ACCOUNT_SID production
npx vercel env add TWILIO_AUTH_TOKEN production
npx vercel env add TWILIO_PHONE_NUMBER production
npx vercel env add TWILIO_VALIDATE_REQUESTS production
npx vercel env add TWILIO_PROCESSING_ACK_DATABASE_DEDUPE_ENABLED production
npx vercel env add TWILIO_MEDIA_FINAL_REPLY_ENABLED production
npx vercel env add HITL_CONFIRMATION_REQUIRED production
```

Check values are present:

```bash
npx vercel env ls
```

Validate local `.env` values before copying them to Vercel:

```bash
python3 scripts/validate_env.py --env-file .env
```

The validator redacts secret values and rejects common placeholders such as `sb`, `sk-pro`, `AC2`, and `cf3`.

### 3. Verify Runtime Packaging

Vercel must receive every Python package used by `app.py` and the Twilio webhook. Do not add these runtime paths to `.vercelignore`:

```text
agents/
config/
constants/
database/
prompts/
schemas/
services/
storage/
ui/
utils/
workflows/
```

The `workflows/` package is required in production because `services/live_backend.py` imports `workflows.api.process_whatsapp_message` for WhatsApp text and media handling.

Before deploying a packaging change, run:

```bash
python -c "from workflows.api import process_whatsapp_message; print(process_whatsapp_message.__name__)"
```

### 4. Deploy

```bash
npx vercel deploy --prod
```

After changing env vars, redeploy:

```bash
npx vercel redeploy --prod
```

## Local Development

Install:

```bash
git clone https://github.com/Abby263/whatsapp-invoice-assistant.git
cd whatsapp-invoice-assistant
cp .env.example .env
poetry install
```

The repository targets Python 3.12 for Vercel/local development and also tests Python 3.10 and 3.11 in CI for compatibility.

Run the local UI:

```bash
make ui-run
```

Open:

```text
http://localhost:5001
```

Local Twilio webhook testing requires a public HTTPS tunnel that forwards to the Flask app. Production Twilio should use the Vercel webhook URL.

## End-to-End Test Plan

### 1. Backend Health

```bash
curl https://whatsapp-invoice-assistant.vercel.app/health
```

Expected:

- `status=ok`
- `backend_enabled=true`
- `runtime=vercel-production`

You can run the automated post-deploy smoke checks with:

```bash
python3 scripts/deployment_smoke.py --base-url https://whatsapp-invoice-assistant.vercel.app
```

### 2. Webhook Smoke Test

```bash
curl -i -X POST https://whatsapp-invoice-assistant.vercel.app/webhook \
  --data-urlencode 'From=whatsapp:+15551234567' \
  --data-urlencode 'To=whatsapp:+1<your-twilio-whatsapp-sender>' \
  --data-urlencode 'Body=Hey' \
  --data-urlencode 'NumMedia=0'
```

Expected: HTTP `200` with TwiML.

### 3. WhatsApp Text Test

1. Send `Hey` from WhatsApp to the Twilio sender.
2. Confirm Twilio Request Inspector shows the Vercel webhook URL and HTTP `200`.
3. Confirm WhatsApp receives an assistant response.

### 4. WhatsApp Receipt Test

1. Send a receipt image or PDF over WhatsApp.
2. Confirm Supabase Storage has a new object under `<user-id>/invoices/...`.
3. Confirm Supabase tables have new `invoices`, `items`, `media`, and embedding rows.
4. Ask a question such as `What did I spend this month?`.

### 5. Web Link Test

1. Open `https://whatsapp-invoice-assistant.vercel.app`.
2. Sign in or sign up with a verified phone number.
3. Use the same phone number in the Twilio `From` field, including country code.
4. Confirm the top-right account selector shows the signed-in phone number.
5. Confirm receipts and generated invoices are visible for that user.

### 6. Invoice Generation Test

1. Save company defaults in `Settings` -> `Company profile`.
2. Generate an invoice from the website or ask over WhatsApp.
3. Confirm Supabase Storage has `<user-id>/generated-invoices/...`.
4. Confirm Supabase Postgres has a `generated_invoices` row.

## Troubleshooting

### Twilio Error `11200`

Check Twilio Request Inspector:

- If the URL is an old ngrok URL, update the WhatsApp sender and Messaging Service webhooks to `https://whatsapp-invoice-assistant.vercel.app/webhook`.
- If HTTP status is not `200`, open Vercel logs for the production deployment.
- If response is not XML/TwiML, verify the webhook method is `POST`.

### Twilio Request Inspector Shows HTTP `404`

The webhook URL is wrong or points to an offline tunnel. Use:

```text
https://whatsapp-invoice-assistant.vercel.app/webhook
```

### `/health` Shows Missing Supabase Secret

Add one server-side key:

```env
SUPABASE_SECRET_KEY=<sb_secret_...>
```

or:

```env
SUPABASE_SERVICE_ROLE_KEY=<legacy-service-role-key>
```

Redeploy after adding it.

### Database Connection Fails

Check:

- `DATABASE_URL` uses the right project ref.
- Password is URL-encoded in `DATABASE_URL` and `DIRECT_URL`.
- Pooler host and port are correct.
- `NEXT_PUBLIC_SUPABASE_URL` belongs to the same project.

### Receipts Upload But Do Not Appear on Website

Check:

- The web user signed in with Clerk.
- The Clerk account has a verified phone number.
- The verified phone number matches Twilio `From`, including country code.
- The `users` row has both `whatsapp_number` and `clerk_user_id`.

### Generated Invoices Are Not Saved

Check:

- Migrations ran successfully.
- `generated_invoices` and `generated_invoice_items` exist.
- `SUPABASE_SECRET_KEY` or `SUPABASE_SERVICE_ROLE_KEY` is present.
- `SUPABASE_STORAGE_BUCKET=receipts` points to an existing private bucket.

### Embeddings Are Missing

Check:

- `OPENAI_API_KEY` is valid.
- OpenAI billing and model access are enabled.
- `vector` extension exists in Supabase.
- Embedding jobs are not failing in Vercel logs.
