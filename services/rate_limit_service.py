"""Persisted per-user rate limiting and usage accounting."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from config.settings import get_settings


logger = logging.getLogger(__name__)

SCOPE_TEXT_TURN = "text_turn"
SCOPE_MEDIA_UPLOAD = "media_upload"
SCOPE_APPROVAL = "approval_finalization"
SCOPE_EMBEDDING = "embedding"


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    scope: str
    limit: int
    used: int
    remaining: int
    retry_after_seconds: int
    message: Optional[str] = None

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "scope": self.scope,
            "limit": self.limit,
            "used": self.used,
            "remaining": self.remaining,
            "retry_after_seconds": self.retry_after_seconds,
        }


def check_and_record(
    user_id: Any,
    scope: str,
    *,
    units: int = 1,
    request_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> RateLimitDecision:
    settings = get_settings()
    limit = _limit_for_scope(scope)
    units = max(1, int(units or 1))
    if not settings.rate_limits_enabled or not user_id or limit <= 0:
        return RateLimitDecision(
            allowed=True,
            scope=scope,
            limit=limit,
            used=0,
            remaining=max(limit - units, 0),
            retry_after_seconds=0,
        )

    try:
        from sqlalchemy import func

        from database.connection import ensure_application_schema, get_db_session
        from database.schemas import RateLimitEvent

        ensure_application_schema()
        session = get_db_session()
        try:
            window_start = datetime.utcnow() - timedelta(
                seconds=settings.rate_limit_window_seconds
            )
            used = (
                session.query(func.coalesce(func.sum(RateLimitEvent.units), 0))
                .filter(
                    RateLimitEvent.user_id == int(user_id),
                    RateLimitEvent.scope == scope,
                    RateLimitEvent.status == "allowed",
                    RateLimitEvent.created_at >= window_start,
                )
                .scalar()
                or 0
            )
            allowed = used + units <= limit
            event = RateLimitEvent(
                user_id=int(user_id),
                scope=scope,
                request_id=request_id,
                units=units,
                status="allowed" if allowed else "rejected",
                event_metadata=metadata or {},
            )
            session.add(event)
            session.commit()
            remaining = max(limit - used - (units if allowed else 0), 0)
            return RateLimitDecision(
                allowed=allowed,
                scope=scope,
                limit=limit,
                used=int(used),
                remaining=int(remaining),
                retry_after_seconds=settings.rate_limit_window_seconds,
                message=None if allowed else _limit_message(scope),
            )
        finally:
            session.close()
    except Exception as exc:
        logger.warning(
            "Rate limit check unavailable for user=%s scope=%s: %s", user_id, scope, exc
        )
        return RateLimitDecision(
            allowed=True,
            scope=scope,
            limit=limit,
            used=0,
            remaining=max(limit - units, 0),
            retry_after_seconds=0,
        )


def record_token_usage(
    user_id: Any,
    token_usage: Optional[Dict[str, Any]],
    *,
    operation_type: str,
    request_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    if not user_id or not isinstance(token_usage, dict):
        return

    try:
        from database.connection import ensure_application_schema, get_db_session
        from database.schemas import Usage

        ensure_application_schema()
        tokens_in = int(
            token_usage.get("input_tokens") or token_usage.get("prompt_tokens") or 0
        )
        tokens_out = int(
            token_usage.get("output_tokens")
            or token_usage.get("completion_tokens")
            or 0
        )
        cost = float(token_usage.get("cost") or 0.0)
        session = get_db_session()
        try:
            session.add(
                Usage(
                    user_id=int(user_id),
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost=cost,
                    operation_type=operation_type,
                    request_id=request_id,
                    usage_metadata=metadata or {},
                )
            )
            session.commit()
        finally:
            session.close()
    except Exception as exc:
        logger.warning(
            "Could not record token usage for user=%s operation=%s: %s",
            user_id,
            operation_type,
            exc,
        )


def _limit_for_scope(scope: str) -> int:
    settings = get_settings()
    return {
        SCOPE_TEXT_TURN: settings.rate_limit_text_turns_per_window,
        SCOPE_MEDIA_UPLOAD: settings.rate_limit_media_uploads_per_window,
        SCOPE_APPROVAL: settings.rate_limit_approvals_per_window,
        SCOPE_EMBEDDING: settings.rate_limit_embeddings_per_window,
    }.get(scope, settings.rate_limit_text_turns_per_window)


def _limit_message(scope: str) -> str:
    label = {
        SCOPE_TEXT_TURN: "message",
        SCOPE_MEDIA_UPLOAD: "upload",
        SCOPE_APPROVAL: "approval",
        SCOPE_EMBEDDING: "embedding",
    }.get(scope, "request")
    return (
        f"Daily {label} limit reached for this account. "
        "Please try again after the rolling usage window resets."
    )
