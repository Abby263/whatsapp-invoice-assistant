# Production Backlog

This backlog captures the next production hardening work after the Vercel-only architecture cleanup, WhatsApp HITL approval fixes, SQL guardrails, auth hardening, CI baseline, and Flask route split.

## Operating Baseline

- WhatsApp media uploads are validated, extracted, and held as pending media before analytics or RAG indexing.
- `APPROVE <upload_id>` / `REJECT <upload_id>` are deterministic WhatsApp commands.
- Approved uploads write from cached extraction when media metadata still matches, and reprocess only when the cache is unavailable or stale.
- Query execution enforces SQL guardrails at the execution choke point.
- Live API routes resolve users from Clerk verified phone identity, not caller-supplied `user_id`.
- Hosted Flask routes are split into blueprints under `routes/`; `app.py` remains the Vercel entrypoint.
- GitHub Actions runs environment-template validation, syntax compilation, and pytest.

## Backlog Items

| Item | Why It Matters | Suggested Shape |
| --- | --- | --- |
| Structured observability | Production support needs request-level traces across webhook, extraction, approval, storage, SQL, RAG, and outbound Twilio responses. | Add a `request_id` / `message_sid` logging context, token usage metrics, extraction latency metrics, and final status counters. |
| Per-user LLM rate limits | Prevent one account or replay storm from driving unbounded OpenAI and Twilio cost. | Add user-scoped counters for text turns, media extraction, approval finalization, and embeddings; enforce soft and hard limits with clear WhatsApp responses. |
| Web approval with step-up auth | Website approval is useful for operators, but WhatsApp remains the primary approval surface. | Add optional web approval only after fresh Clerk step-up verification and display the exact same pending extraction summary used in WhatsApp. |
| Python 3.11+ upgrade | Newer runtimes improve security support, performance, and dependency compatibility. | Test on Python 3.11 first in CI, then update Vercel/runtime docs and local setup after dependency issues are resolved. |
| Single typed settings object | Environment access is currently spread across modules and helper functions. | Introduce `pydantic-settings` with explicit production/demo defaults, validation, and one importable settings instance. |
| Async work queue | Multi-page PDFs and large batches can exceed serverless request time even with ack-first behavior. | Move long extraction/finalization jobs to a durable queue or workflow runner with idempotent job records and outbound Twilio status updates. |
| Deployment smoke tests | CI proves code health, but production needs webhook and health-path verification after deploys. | Add a post-deploy script that checks `/health`, auth config, and a signed test webhook with mocked Twilio/OpenAI where possible. |

## Guardrails For Future Work

- Pending WhatsApp media must not become SQL/RAG retrieval data before approval.
- Any retrieval path must be scoped to the resolved internal `users.id`.
- Any destructive action must keep an explicit confirmation step.
- Any new LLM output shown to business users should be compact, structured, and free of raw provider errors.
- Any new route should live in the relevant blueprint and keep `app.py` as the thin Vercel entrypoint.
