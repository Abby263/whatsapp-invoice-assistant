"""Durable async job queue backed by Supabase Postgres."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from sqlalchemy.exc import IntegrityError

from config.settings import get_settings


logger = logging.getLogger(__name__)

JOB_TYPE_TWILIO_MEDIA_BATCH = "twilio_media_batch"
JOB_TYPE_TWILIO_TEXT_MESSAGE = "twilio_text_message"


def enqueue_job(
    job_type: str,
    payload: Dict[str, Any],
    *,
    user_id: Optional[Any] = None,
    idempotency_key: Optional[str] = None,
    max_attempts: int = 3,
) -> Dict[str, Any]:
    from database.connection import ensure_application_schema, get_db_session
    from database.schemas import AsyncJob

    ensure_application_schema()
    session = get_db_session()
    try:
        job = AsyncJob(
            job_type=job_type,
            idempotency_key=idempotency_key,
            user_id=int(user_id) if user_id not in (None, "") else None,
            payload=payload,
            max_attempts=max(1, int(max_attempts or 3)),
            status="queued",
        )
        session.add(job)
        try:
            session.commit()
            session.refresh(job)
        except IntegrityError:
            session.rollback()
            if not idempotency_key:
                raise
            job = (
                session.query(AsyncJob)
                .filter(AsyncJob.idempotency_key == idempotency_key)
                .first()
            )
        return serialize_job(job)
    finally:
        session.close()


def run_ready_jobs(
    handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]],
    *,
    limit: int = 5,
) -> Dict[str, Any]:
    from database.connection import ensure_application_schema, get_db_session
    from database.schemas import AsyncJob

    ensure_application_schema()
    session = get_db_session()
    processed = []
    try:
        jobs = (
            session.query(AsyncJob)
            .filter(
                AsyncJob.status == "queued",
                AsyncJob.available_at <= datetime.utcnow(),
            )
            .order_by(AsyncJob.created_at.asc(), AsyncJob.id.asc())
            .limit(max(1, int(limit or 5)))
            .all()
        )
        for job in jobs:
            handler = handlers.get(job.job_type)
            if handler is None:
                job.status = "failed"
                job.error_message = f"No handler registered for {job.job_type}"
                job.completed_at = datetime.utcnow()
                processed.append(serialize_job(job))
                continue

            job.status = "running"
            job.started_at = datetime.utcnow()
            job.attempts = int(job.attempts or 0) + 1
            session.commit()
            try:
                result = handler(job.payload or {})
                job.result = result
                job.status = "completed"
                job.completed_at = datetime.utcnow()
                job.error_message = None
            except Exception as exc:
                logger.exception("Async job %s failed", job.id)
                job.error_message = str(exc)
                job.status = "failed" if job.attempts >= job.max_attempts else "queued"
            finally:
                job.updated_at = datetime.utcnow()
                session.commit()
                processed.append(serialize_job(job))
        return {"status": "success", "processed": processed, "count": len(processed)}
    finally:
        session.close()


def queue_enabled_for_media_count(media_count: int) -> bool:
    settings = get_settings()
    return (
        settings.async_work_queue_enabled
        and media_count > settings.async_inline_media_limit
    )


def queue_enabled_for_text_message(message_text: str) -> bool:
    settings = get_settings()
    return (
        settings.async_work_queue_enabled
        and settings.async_text_queue_enabled
        and bool((message_text or "").strip())
    )


def serialize_job(job: Any) -> Dict[str, Any]:
    if not job:
        return {}
    return {
        "id": job.id,
        "job_type": job.job_type,
        "idempotency_key": job.idempotency_key,
        "status": job.status,
        "user_id": str(job.user_id) if job.user_id is not None else None,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
