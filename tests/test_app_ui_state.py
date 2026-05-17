"""Tests for hosted UI user-linking defaults."""

import app as hosted_app


class _AuthContext:
    clerk_user_id = "clerk_test"
    session_id = "sess_test"


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


def test_hosted_ui_uses_single_connections_entrypoint(monkeypatch):
    monkeypatch.setattr(hosted_app, "_live_backend_enabled", lambda: False)
    monkeypatch.setattr(hosted_app, "is_clerk_enabled", lambda: False)

    client = hosted_app.app.test_client()
    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-view="connections"' in html
    assert 'id="linkWhatsappBtn"' not in html
    assert html.count("Connect WhatsApp") == 1
    assert "No WhatsApp linked" in html


def test_demo_link_whatsapp_requires_explicit_number(monkeypatch):
    monkeypatch.setattr(hosted_app, "_live_backend_enabled", lambda: False)
    monkeypatch.setattr(hosted_app, "_require_demo_auth", lambda: _AuthContext())
    hosted_app.DEMO_LINKS.clear()

    client = hosted_app.app.test_client()
    response = client.post("/api/auth/link-whatsapp", json={})

    assert response.status_code == 400
    assert hosted_app.DEMO_LINKS == {}


def test_demo_link_whatsapp_normalizes_number(monkeypatch):
    monkeypatch.setattr(hosted_app, "_live_backend_enabled", lambda: False)
    monkeypatch.setattr(hosted_app, "_require_demo_auth", lambda: _AuthContext())
    hosted_app.DEMO_LINKS.clear()

    client = hosted_app.app.test_client()
    response = client.post(
        "/api/auth/link-whatsapp",
        json={"whatsapp_number": "whatsapp:+15551234567"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["user"]["whatsapp_number"] == "+15551234567"


def test_twilio_webhook_can_suppress_twiml_after_outbound_reply(monkeypatch):
    monkeypatch.setattr(hosted_app, "_live_backend_enabled", lambda: True)
    monkeypatch.setattr(hosted_app, "_twilio_request_is_valid", lambda: True)
    monkeypatch.setattr(
        hosted_app.live_backend,
        "process_twilio_webhook",
        lambda form: {
            "status": "success",
            "message": "Already sent out of band.",
            "suppress_twiml_response": True,
            "metadata": {"twilio_final_reply_sent": True},
        },
    )

    client = hosted_app.app.test_client()
    response = client.post(
        "/webhook",
        data={
            "From": "whatsapp:+15551234567",
            "To": "whatsapp:+16473628073",
            "NumMedia": "1",
        },
    )

    assert response.status_code == 200
    assert b"<Response></Response>" in response.data
    assert b"<Message>" not in response.data
