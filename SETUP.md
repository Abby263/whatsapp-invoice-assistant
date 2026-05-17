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
| Clerk | Website authentication and linking a web user to a WhatsApp number. |
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

NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=<clerk-publishable-key>
CLERK_SECRET_KEY=<clerk-secret-key>
CLERK_REQUIRE_AUTH=true
CLERK_AUTHORIZED_PARTIES=https://whatsapp-invoice-assistant.vercel.app

OPENAI_API_KEY=<openai-api-key>
OPENAI_API_MODEL=gpt-5.4-mini

TWILIO_ACCOUNT_SID=<twilio-account-sid>
TWILIO_AUTH_TOKEN=<twilio-auth-token>
TWILIO_PHONE_NUMBER=whatsapp:+1<approved-twilio-whatsapp-sender>
```

Notes:

- `DATABASE_URL` is for runtime. Use the Supabase pooler URL for Vercel/serverless.
- `DIRECT_URL` is for migrations.
- If the database password contains reserved URL characters, encode them before placing it in `DATABASE_URL` or `DIRECT_URL`. For example, `@` becomes `%40`.
- `SUPABASE_SECRET_KEY` is server-side only. Never expose it as a `NEXT_PUBLIC_*` variable.
- `SUPABASE_SERVICE_ROLE_KEY` is accepted as a legacy fallback if your Supabase project does not show `SUPABASE_SECRET_KEY`.
- `TWILIO_PHONE_NUMBER` must be the WhatsApp-enabled sender, with the `whatsapp:` prefix.

Optional local-only variables:

```env
USE_MONGODB=false
MONGODB_URI=mongodb://localhost:27017/whatsapp_invoice_assistant
REDIS_URL=redis://localhost:6379/0
DEBUG=false
LOG_LEVEL=INFO
PORT=8000
HOST=0.0.0.0
```

MongoDB and Redis are not required for the current Vercel real-time WhatsApp test path.

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
2. Enable the sign-in methods you want. Phone plus email is recommended.
3. Open `Configure` -> `API keys`.
4. Set:

```env
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=<clerk-publishable-key>
CLERK_SECRET_KEY=<clerk-secret-key>
CLERK_REQUIRE_AUTH=true
CLERK_AUTHORIZED_PARTIES=https://whatsapp-invoice-assistant.vercel.app
```

How account linking works:

1. User signs in on the website.
2. User clicks `Link WhatsApp`.
3. User enters the same WhatsApp number used to send receipts.
4. The app links Clerk `sub` to the internal `users` row for that WhatsApp number.
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

### 3. Deploy

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

Run the local UI:

```bash
make ui-run
```

Open:

```text
http://localhost:5001
```

Run the alternate FastAPI webhook locally only when you need local API testing:

```bash
make start
curl http://localhost:8000/health
```

Local Twilio webhook testing requires a public HTTPS tunnel, but production Twilio should use the Vercel webhook URL.

## End-to-End Test Plan

### 1. Backend Health

```bash
curl https://whatsapp-invoice-assistant.vercel.app/health
```

Expected:

- `status=ok`
- `backend_enabled=true`
- `runtime=vercel-production`

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
2. Sign in with Clerk.
3. Click `Link WhatsApp`.
4. Enter the same WhatsApp number used in the Twilio `From` field, including country code.
5. Confirm the top-right user selector shows the linked WhatsApp number.
6. Confirm receipts and generated invoices are visible for that user.

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
- The user clicked `Link WhatsApp`.
- The linked number matches Twilio `From`, including country code.
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
