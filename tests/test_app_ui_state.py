"""Tests for hosted UI user-linking defaults."""

import app as hosted_app


def test_demo_users_do_not_expose_default_whatsapp_number(monkeypatch):
    monkeypatch.setattr(hosted_app, "_live_backend_enabled", lambda: False)
    monkeypatch.setattr(hosted_app, "is_clerk_enabled", lambda: False)
    hosted_app.DEMO_LINKS.clear()

    client = hosted_app.app.test_client()
    response = client.get("/api/users")

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["users"] == []


def test_demo_init_starts_without_default_whatsapp_number(monkeypatch):
    monkeypatch.setattr(hosted_app, "_live_backend_enabled", lambda: False)
    monkeypatch.setattr(hosted_app, "is_clerk_enabled", lambda: False)
    hosted_app.DEMO_LINKS.clear()

    client = hosted_app.app.test_client()
    response = client.get("/api/init")

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["user_id"] is None
    assert data["whatsapp_number"] is None
