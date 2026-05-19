# Production Backlog

This document records the production hardening work completed after the Vercel-only architecture cleanup, WhatsApp HITL approval fixes, SQL guardrails, auth hardening, CI baseline, and Flask route split.

## Operating Baseline

- WhatsApp media uploads are validated, extracted, and held as pending media before analytics or RAG indexing.
- `APPROVE <upload_id>` / `REJECT <upload_id>` are deterministic WhatsApp commands.
- Approved uploads write from cached extraction when media metadata still matches, and reprocess only when the cache is unavailable or stale.
- Query execution enforces SQL guardrails at the execution choke point.
- Live API routes resolve users from Clerk verified phone identity, not caller-supplied `user_id`.
- Hosted Flask routes are split into blueprints under `routes/`; `app.py` remains the Vercel entrypoint.
- GitHub Actions runs environment-template validation, syntax compilation, and pytest.

## Completed Backlog Items

| Item | Status | Implementation |
| --- | --- | --- |
| Structured observability | Done | `utils/observability.py` provides request context, request ids, message ids, user ids, and structured event logs for webhook/text/media flows. |
| Per-user LLM rate limits | Done | `services/rate_limit_service.py` persists rolling-window counters in `rate_limit_events`, records token usage metadata in `usage`, and enforces limits for text, media, approval, and embeddings. |
| Web approval with step-up auth | Done | Browser approval is optional and requires a fresh Clerk session token before it can approve or reject; WhatsApp approval remains available. |
| Python 3.11+ upgrade | Done | `.python-version` targets Python 3.12 and CI tests Python 3.10, 3.11, and 3.12. |
| Single typed settings object | Done | `config/settings.py` centralizes production/demo settings with `pydantic-settings`. |
| Async work queue | Done | `async_jobs` and `services/job_queue.py` provide durable idempotent jobs; large media batches can be queued and processed through `/api/jobs/run`. |
| Deployment smoke tests | Done | `scripts/deployment_smoke.py` checks `/health` and `/api/auth/config` against a deployment URL. |

## Guardrails For Future Work

- Pending WhatsApp media must not become SQL/RAG retrieval data before approval.
- Any retrieval path must be scoped to the resolved internal `users.id`.
- Any destructive action must keep an explicit confirmation step.
- Any new LLM output shown to business users should be compact, structured, and free of raw provider errors.
- Any new route should live in the relevant blueprint and keep `app.py` as the thin Vercel entrypoint.
