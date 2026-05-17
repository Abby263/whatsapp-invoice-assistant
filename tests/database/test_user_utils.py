"""Tests for user identity linking helpers."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.schemas import Base, User
from database.user_utils import link_clerk_user_to_whatsapp


@pytest.fixture(autouse=True)
def skip_application_schema_check(monkeypatch):
    """These tests use isolated SQLite tables, not the configured Supabase engine."""

    monkeypatch.setattr("database.user_utils._ensure_application_schema", lambda: None)


@pytest.fixture
def test_db():
    """Create an in-memory SQLite database for identity-linking tests."""

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    transaction.rollback()
    connection.close()
    session.close()


def test_link_clerk_user_updates_existing_placeholder_link(test_db):
    placeholder_user = User(
        whatsapp_number="+1234567890",
        clerk_user_id="clerk_123",
        name="User +1234567890",
        email=None,
        is_active=True,
    )
    test_db.add(placeholder_user)
    test_db.commit()

    linked = link_clerk_user_to_whatsapp(
        test_db,
        clerk_user_id="clerk_123",
        whatsapp_number="whatsapp:+15551234567",
        name="Real User",
        email="real@example.com",
    )

    saved = test_db.query(User).filter(User.clerk_user_id == "clerk_123").one()
    assert linked["id"] == str(saved.id)
    assert linked["whatsapp_number"] == "+15551234567"
    assert saved.whatsapp_number == "+15551234567"
    assert saved.name == "Real User"
    assert saved.email == "real@example.com"


def test_link_clerk_user_moves_to_existing_whatsapp_user(test_db):
    old_user = User(
        whatsapp_number="+1234567890",
        clerk_user_id="clerk_123",
        name="Placeholder",
        is_active=True,
    )
    whatsapp_user = User(
        whatsapp_number="+15551234567",
        name="WhatsApp User +15551234567",
        is_active=True,
    )
    test_db.add_all([old_user, whatsapp_user])
    test_db.commit()

    linked = link_clerk_user_to_whatsapp(
        test_db,
        clerk_user_id="clerk_123",
        whatsapp_number="+15551234567",
        name="Real User",
    )

    test_db.refresh(old_user)
    test_db.refresh(whatsapp_user)
    assert linked["id"] == str(whatsapp_user.id)
    assert old_user.clerk_user_id is None
    assert whatsapp_user.clerk_user_id == "clerk_123"
    assert whatsapp_user.name == "Real User"


def test_link_clerk_user_rejects_whatsapp_number_owned_by_other_clerk(test_db):
    existing_user = User(
        whatsapp_number="+15551234567",
        clerk_user_id="clerk_other",
        name="Existing User",
        is_active=True,
    )
    test_db.add(existing_user)
    test_db.commit()

    with pytest.raises(ValueError, match="already linked to another account"):
        link_clerk_user_to_whatsapp(
            test_db,
            clerk_user_id="clerk_123",
            whatsapp_number="+15551234567",
        )
