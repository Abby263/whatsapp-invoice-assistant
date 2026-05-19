"""Tests for the durable async job queue."""

import sys
import types

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import database.schemas as schema_module
from database.schemas import AsyncJob, Base, User
from services import job_queue


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


def test_enqueue_job_is_idempotent(monkeypatch, session_factory):
    _patch_connection(monkeypatch, session_factory)
    session = session_factory()
    user = User(whatsapp_number="+15551234567")
    session.add(user)
    session.commit()
    user_id = user.id
    session.close()

    first = job_queue.enqueue_job(
        "example", {"value": 1}, user_id=user_id, idempotency_key="same"
    )
    second = job_queue.enqueue_job(
        "example", {"value": 2}, user_id=user_id, idempotency_key="same"
    )

    assert first["id"] == second["id"]
    session = session_factory()
    try:
        assert session.query(AsyncJob).count() == 1
    finally:
        session.close()


def test_run_ready_jobs_marks_completed(monkeypatch, session_factory):
    _patch_connection(monkeypatch, session_factory)
    job_queue.enqueue_job("example", {"value": 3})

    result = job_queue.run_ready_jobs(
        {"example": lambda payload: {"doubled": payload["value"] * 2}}
    )

    assert result["status"] == "success"
    assert result["count"] == 1
    session = session_factory()
    try:
        job = session.query(AsyncJob).one()
        assert job.status == "completed"
        assert job.result == {"doubled": 6}
    finally:
        session.close()
