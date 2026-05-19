"""Tests for Clerk verified phone account mapping."""

import pytest

from utils.clerk_auth import (
    ClerkAuthContext,
    ClerkAuthError,
    verified_phone_profile_from_clerk,
)


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
