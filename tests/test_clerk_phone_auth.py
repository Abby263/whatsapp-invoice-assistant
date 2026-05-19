"""Tests for Clerk verified phone account mapping."""

import pytest

from utils.clerk_auth import (
    ClerkAuthContext,
    ClerkAuthError,
    verified_phone_profile_from_clerk,
)
from services import live_backend


def _auth_context():
    return ClerkAuthContext(
        clerk_user_id="user_123",
        session_id="sess_123",
        issuer="https://example.clerk.accounts.dev",
        claims={"sub": "user_123"},
    )


def test_verified_phone_profile_uses_verified_primary_phone(monkeypatch):
    monkeypatch.setattr(
        "utils.clerk_auth.fetch_clerk_user",
        lambda clerk_user_id: {
            "id": clerk_user_id,
            "first_name": "Asha",
            "last_name": "Rao",
            "primary_phone_number_id": "phone_1",
            "phone_numbers": [
                {
                    "id": "phone_1",
                    "phone_number": "whatsapp:+15551234567",
                    "verification": {"status": "verified"},
                }
            ],
            "primary_email_address_id": "email_1",
            "email_addresses": [
                {"id": "email_1", "email_address": "asha@example.com"}
            ],
        },
    )

    profile = verified_phone_profile_from_clerk(_auth_context())

    assert profile.clerk_user_id == "user_123"
    assert profile.phone_number == "+15551234567"
    assert profile.name == "Asha Rao"
    assert profile.email == "asha@example.com"


def test_verified_phone_profile_rejects_unverified_phone(monkeypatch):
    monkeypatch.setattr(
        "utils.clerk_auth.fetch_clerk_user",
        lambda clerk_user_id: {
            "id": clerk_user_id,
            "primary_phone_number_id": "phone_1",
            "phone_numbers": [
                {
                    "id": "phone_1",
                    "phone_number": "+15551234567",
                    "verification": {"status": "unverified"},
                }
            ],
        },
    )

    with pytest.raises(ClerkAuthError, match="verified phone number"):
        verified_phone_profile_from_clerk(_auth_context())


def test_resolve_request_user_rejects_payload_user_id_when_auth_required(monkeypatch):
    monkeypatch.setattr(live_backend, "is_auth_required", lambda: True)

    user, needs_link = live_backend.resolve_request_user(
        None,
        {"user_id": "1", "whatsapp_number": "+15551234567"},
    )

    assert user is None
    assert needs_link is True


def test_resolve_request_user_does_not_fallback_to_payload_when_phone_sync_fails(monkeypatch):
    monkeypatch.setattr(live_backend, "is_auth_required", lambda: True)
    monkeypatch.setattr(live_backend, "get_linked_user", lambda clerk_user_id: None)

    def fail_sync(auth_context):
        raise ValueError("verified phone required")

    monkeypatch.setattr(live_backend, "sync_verified_phone_user", fail_sync)

    user, needs_link = live_backend.resolve_request_user(
        _auth_context(),
        {"user_id": "1", "whatsapp_number": "+15551234567"},
    )

    assert user is None
    assert needs_link is True
