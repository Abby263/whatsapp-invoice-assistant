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
