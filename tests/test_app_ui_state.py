"""Tests for hosted UI user-linking defaults."""

import app as hosted_app
from routes import shared as hosted_shared
from workflows import api as workflow_api


class _AuthContext:
    clerk_user_id = "clerk_test"
    session_id = "sess_test"


def test_demo_users_do_not_expose_default_whatsapp_number(monkeypatch):
    monkeypatch.setattr(hosted_shared, "_live_backend_enabled", lambda: False)
    monkeypatch.setattr(hosted_shared, "is_clerk_enabled", lambda: False)
    hosted_app.DEMO_LINKS.clear()

    client = hosted_app.app.test_client()
    response = client.get("/api/users")

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["users"] == []


def test_demo_init_starts_without_default_whatsapp_number(monkeypatch):
    monkeypatch.setattr(hosted_shared, "_live_backend_enabled", lambda: False)
    monkeypatch.setattr(hosted_shared, "is_clerk_enabled", lambda: False)
    hosted_app.DEMO_LINKS.clear()

    client = hosted_app.app.test_client()
    response = client.get("/api/init")

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["user_id"] is None
    assert data["whatsapp_number"] is None


def test_hosted_ui_uses_phone_auth_without_connections_tab(monkeypatch):
    monkeypatch.setattr(hosted_shared, "_live_backend_enabled", lambda: False)
    monkeypatch.setattr(hosted_shared, "is_clerk_enabled", lambda: False)

    client = hosted_app.app.test_client()
    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-view="connections"' not in html
    assert 'id="linkWhatsappBtn"' not in html
    assert "Connect WhatsApp" not in html
    assert "Sign in with phone" in html
    assert "Phone sign-in required" in html


def test_hosted_ui_sidebar_uses_addressable_routes(monkeypatch):
    monkeypatch.setattr(hosted_shared, "_live_backend_enabled", lambda: False)
    monkeypatch.setattr(hosted_shared, "is_clerk_enabled", lambda: False)

    client = hosted_app.app.test_client()
    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'href="/chat" class="nav-item" data-view="chat"' in html
    assert 'href="/receipts" class="nav-item" data-view="receipts"' in html
    assert 'aria-current="page"' in html


def test_hosted_ui_supports_direct_sidebar_routes(monkeypatch):
    monkeypatch.setattr(hosted_shared, "_live_backend_enabled", lambda: False)
    monkeypatch.setattr(hosted_shared, "is_clerk_enabled", lambda: False)

    client = hosted_app.app.test_client()

    for route in ["/chat", "/receipts", "/inspector", "/settings"]:
        response = client.get(route)
        assert response.status_code == 200
        assert 'data-view="overview"' in response.get_data(as_text=True)


def test_demo_link_whatsapp_requires_explicit_number(monkeypatch):
    monkeypatch.setattr(hosted_shared, "_live_backend_enabled", lambda: False)
    monkeypatch.setattr(hosted_shared, "_require_demo_auth", lambda: _AuthContext())
    hosted_app.DEMO_LINKS.clear()

    client = hosted_app.app.test_client()
    response = client.post("/api/auth/link-whatsapp", json={})

    assert response.status_code == 400
    assert hosted_app.DEMO_LINKS == {}


def test_demo_link_whatsapp_normalizes_number(monkeypatch):
    monkeypatch.setattr(hosted_shared, "_live_backend_enabled", lambda: False)
    monkeypatch.setattr(hosted_shared, "_require_demo_auth", lambda: _AuthContext())
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
    monkeypatch.setenv("TWILIO_VALIDATE_REQUESTS", "false")
    monkeypatch.setattr(hosted_shared, "_live_backend_enabled", lambda: True)
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
    assert response.headers["X-Request-ID"]


def test_twilio_validation_is_optional_in_demo_mode_when_env_missing(monkeypatch):
    monkeypatch.delenv("TWILIO_VALIDATE_REQUESTS", raising=False)
    monkeypatch.setattr(hosted_shared, "_live_backend_enabled", lambda: False)

    with hosted_app.app.test_request_context("/webhook", method="POST", data={}):
        assert hosted_app._twilio_request_is_valid() is True


def test_twilio_webhook_validates_signature_by_default_when_live(monkeypatch):
    monkeypatch.delenv("TWILIO_VALIDATE_REQUESTS", raising=False)
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test-token")
    monkeypatch.setattr(hosted_shared, "_live_backend_enabled", lambda: True)

    called = {"value": False}

    def fail_if_called(_form):
        called["value"] = True
        raise AssertionError("webhook processing must not run for invalid Twilio signatures")

    monkeypatch.setattr(hosted_app.live_backend, "process_twilio_webhook", fail_if_called)

    client = hosted_app.app.test_client()
    response = client.post(
        "/webhook",
        data={
            "From": "whatsapp:+15551234567",
            "To": "whatsapp:+16473628073",
            "Body": "Hi",
            "MessageSid": "SM-invalid",
        },
    )

    assert response.status_code == 403
    assert b"Invalid Twilio request signature" in response.data
    assert called["value"] is False


def test_twilio_webhook_hides_internal_exception_details(monkeypatch):
    monkeypatch.setenv("TWILIO_VALIDATE_REQUESTS", "false")
    monkeypatch.setattr(hosted_shared, "_live_backend_enabled", lambda: True)

    def fail_processing(_form):
        raise RuntimeError("database password leaked")

    monkeypatch.setattr(hosted_app.live_backend, "process_twilio_webhook", fail_processing)

    client = hosted_app.app.test_client()
    response = client.post(
        "/webhook",
        data={
            "From": "whatsapp:+15551234567",
            "To": "whatsapp:+16473628073",
            "Body": "Hi",
            "MessageSid": "SM-fail",
        },
    )

    assert response.status_code == 500
    assert b"Something went wrong. Please try again." in response.data
    assert b"database password leaked" not in response.data
    assert response.headers["X-Request-ID"]


def test_twilio_webhook_help_returns_menu_without_user_lookup(monkeypatch):
    def fail_user_lookup(sender):
        raise AssertionError("help webhook should not wait on user lookup")

    def fail_enqueue(*args, **kwargs):
        raise AssertionError("help webhook should not be queued")

    monkeypatch.setenv("TWILIO_VALIDATE_REQUESTS", "false")
    monkeypatch.setenv("ASYNC_WORK_QUEUE_ENABLED", "true")
    monkeypatch.setenv("ASYNC_TEXT_QUEUE_ENABLED", "true")
    monkeypatch.setattr(hosted_shared, "_live_backend_enabled", lambda: True)
    monkeypatch.setattr(workflow_api, "extract_user_id_from_sender", fail_user_lookup)
    monkeypatch.setattr(workflow_api, "enqueue_job", fail_enqueue)

    client = hosted_app.app.test_client()
    response = client.post(
        "/webhook",
        data={
            "From": "whatsapp:+15551234567",
            "To": "whatsapp:+16473628073",
            "Body": "help",
            "NumMedia": "0",
            "MessageSid": "SM-help-fast",
        },
    )

    assert response.status_code == 200
    assert b"Receipt Intelligence" in response.data
    assert b"<Message>" in response.data


def test_agent_flow_requires_auth_when_auth_required(monkeypatch):
    def auth_response():
        return hosted_app.jsonify({"status": "error", "message": "auth required"}), 401

    monkeypatch.setattr(hosted_shared, "_require_demo_auth", auth_response)

    client = hosted_app.app.test_client()
    response = client.get("/api/agent-flow")

    assert response.status_code == 401


def test_embeddings_update_disabled_on_live_backend(monkeypatch):
    monkeypatch.setattr(hosted_shared, "_require_demo_auth", lambda: None)
    monkeypatch.setattr(hosted_shared, "_live_backend_enabled", lambda: True)

    client = hosted_app.app.test_client()
    response = client.post("/api/embeddings/update", json={"force": True})

    assert response.status_code == 403
    assert response.get_json()["status"] == "error"


def test_jobs_run_accepts_cron_authorization(monkeypatch):
    captured = {}

    def fail_auth():
        raise AssertionError("cron-authorized job runner should not require UI auth")

    def fake_run_async_jobs(auth_context, payload):
        captured["auth_context"] = auth_context
        captured["payload"] = payload
        return {"status": "success", "count": 0, "processed": []}

    monkeypatch.setenv("CRON_SECRET", "cron-secret")
    monkeypatch.setenv("ASYNC_JOB_SECRET", "job-secret")
    monkeypatch.setattr(hosted_shared, "_require_demo_auth", fail_auth)
    monkeypatch.setattr(hosted_shared, "_live_backend_enabled", lambda: True)
    monkeypatch.setattr(hosted_app.live_backend, "run_async_jobs", fake_run_async_jobs)

    client = hosted_app.app.test_client()
    response = client.get(
        "/api/jobs/run?limit=2",
        headers={"Authorization": "Bearer cron-secret"},
    )

    assert response.status_code == 200
    assert captured["auth_context"] is None
    assert captured["payload"]["limit"] == "2"
    assert captured["payload"]["secret"] == "job-secret"


def test_jobs_run_get_requires_cron_authorization(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "cron-secret")
    monkeypatch.setattr(hosted_shared, "_live_backend_enabled", lambda: True)

    client = hosted_app.app.test_client()
    response = client.get("/api/jobs/run")

    assert response.status_code == 401
    assert response.get_json()["message"] == "Unauthorized job runner"
