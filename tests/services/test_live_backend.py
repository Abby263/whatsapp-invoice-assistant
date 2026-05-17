from services import live_backend


def test_backend_configuration_rejects_database_placeholder(monkeypatch):
    monkeypatch.delenv("APP_MODE", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://postgres.ref:[YOUR-PASSWORD]@aws-1-us-west-2.pooler.supabase.com:6543/postgres",
    )

    status = live_backend.backend_configuration_status()

    assert status["enabled"] is False
    assert "placeholder" in status["reason"]


def test_backend_configuration_accepts_runtime_database_url(monkeypatch):
    monkeypatch.delenv("APP_MODE", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://postgres.ref:actual-password@aws-1-us-west-2.pooler.supabase.com:6543/postgres",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")

    status = live_backend.backend_configuration_status()

    assert status["enabled"] is True
    assert status["reason"] == "configured"


def test_backend_configuration_rejects_unescaped_database_password(monkeypatch):
    monkeypatch.delenv("APP_MODE", raising=False)
    monkeypatch.delenv("SUPABASE_DB_PASSWORD", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://postgres.ref:pass@word@aws-1-us-west-2.pooler.supabase.com:6543/postgres",
    )

    status = live_backend.backend_configuration_status()

    assert status["enabled"] is False
    assert "unescaped '@'" in status["reason"]


def test_normalize_whatsapp_number_can_require_explicit_value():
    assert live_backend.normalize_whatsapp_number(None, default="") == ""
    assert live_backend.normalize_whatsapp_number("whatsapp:+15551234567", default="") == "+15551234567"
