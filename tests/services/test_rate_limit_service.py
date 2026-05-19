"""Tests for persisted rate limiting and usage accounting."""

import sys
import types

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import database.schemas as schema_module
from database.schemas import Base, RateLimitEvent, Usage, User
from services import rate_limit_service


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    Base.metadata.drop_all(engine)


def _patch_connection(monkeypatch, session_factory):
    fake_connection = types.SimpleNamespace(
        ensure_application_schema=lambda: None,
        get_db_session=lambda: session_factory(),
    )
    monkeypatch.setitem(sys.modules, "database.schemas", schema_module)
    monkeypatch.setitem(sys.modules, "database.connection", fake_connection)


def _seed_user(session_factory):
    session = session_factory()
    user = User(whatsapp_number="+15551234567")
    session.add(user)
    session.commit()
    user_id = user.id
    session.close()
    return user_id


def test_rate_limit_rejects_after_window_limit(monkeypatch, session_factory):
    _patch_connection(monkeypatch, session_factory)
    monkeypatch.setenv("RATE_LIMIT_TEXT_TURNS_PER_WINDOW", "1")
    user_id = _seed_user(session_factory)

    first = rate_limit_service.check_and_record(
        user_id, rate_limit_service.SCOPE_TEXT_TURN
    )
    second = rate_limit_service.check_and_record(
        user_id, rate_limit_service.SCOPE_TEXT_TURN
    )

    assert first.allowed is True
    assert second.allowed is False
    assert second.remaining == 0

    session = session_factory()
    try:
        events = session.query(RateLimitEvent).order_by(RateLimitEvent.id.asc()).all()
        assert [event.status for event in events] == ["allowed", "rejected"]
    finally:
        session.close()


def test_record_token_usage_persists_operation_metadata(monkeypatch, session_factory):
    _patch_connection(monkeypatch, session_factory)
    user_id = _seed_user(session_factory)

    rate_limit_service.record_token_usage(
        user_id,
        {"input_tokens": 12, "output_tokens": 8, "cost": 0.01},
        operation_type="text_turn",
        request_id="req-123",
        metadata={"source": "test"},
    )

    session = session_factory()
    try:
        usage = session.query(Usage).one()
        assert usage.tokens_in == 12
        assert usage.tokens_out == 8
        assert usage.operation_type == "text_turn"
        assert usage.request_id == "req-123"
        assert usage.usage_metadata == {"source": "test"}
    finally:
        session.close()
