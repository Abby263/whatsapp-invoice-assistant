"""Lightweight structured observability helpers."""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Iterator, Optional
from uuid import uuid4


_context: ContextVar[Dict[str, Any]] = ContextVar("observability_context", default={})


def new_request_id() -> str:
    return uuid4().hex


def current_context() -> Dict[str, Any]:
    return dict(_context.get({}))


@contextmanager
def request_context(**fields: Any) -> Iterator[Dict[str, Any]]:
    base = current_context()
    merged = {
        **base,
        **{key: value for key, value in fields.items() if value not in (None, "")},
    }
    token = _context.set(merged)
    try:
        yield merged
    finally:
        _context.reset(token)


def bind_context(**fields: Any) -> None:
    current = current_context()
    current.update(
        {key: value for key, value in fields.items() if value not in (None, "")}
    )
    _context.set(current)


def event_payload(event: str, **fields: Any) -> Dict[str, Any]:
    payload = {
        **current_context(),
        **{key: value for key, value in fields.items() if value not in (None, "")},
    }
    payload["event"] = event
    return payload


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> Dict[str, Any]:
    payload = event_payload(event, **fields)
    logger.log(
        level,
        "event=%s payload=%s",
        event,
        json.dumps(payload, sort_keys=True, default=str),
    )
    return payload


def request_id_from_headers(headers: Any) -> Optional[str]:
    if not headers:
        return None
    return headers.get("X-Request-ID") or headers.get("X-Correlation-ID")
