"""Tests for API text message response handling."""

import pytest

from langchain_app import api


@pytest.mark.asyncio
async def test_process_text_message_ignores_empty_agent_error(monkeypatch):
    async def fake_process_text(text_content, user_id=None, conversation_history=None):
        return {
            "content": "Hi, I'm your WhatsApp Invoice Assistant.",
            "error": None,
            "status": "success",
            "metadata": {"intent": "greeting"},
            "confidence": 0.9,
        }

    monkeypatch.setattr(api, "process_text", fake_process_text)

    result = await api.process_text_message(
        message="Hey",
        sender="whatsapp:+15551234567",
        user_id="1",
    )

    assert result["status"] == "success"
    assert result["message"].startswith("Hi, I'm your WhatsApp Invoice Assistant")
    assert result["message"] != "Error: None"


@pytest.mark.asyncio
async def test_process_text_message_resolves_missing_user_id_from_sender(monkeypatch):
    captured = {}

    async def fake_process_text(text_content, user_id=None, conversation_history=None):
        captured["user_id"] = user_id
        return {
            "content": "You spent INR 7,825 across 1 invoice.",
            "error": None,
            "status": "success",
            "metadata": {"intent": "invoice_query"},
            "confidence": 0.9,
        }

    monkeypatch.setattr(api, "process_text", fake_process_text)
    monkeypatch.setattr(api, "extract_user_id_from_sender", lambda sender: "42")

    result = await api.process_text_message(
        message="Show my expense summary",
        sender="whatsapp:+15551234567",
    )

    assert captured["user_id"] == "42"
    assert result["status"] == "success"
    assert result["user_id"] == "42"


@pytest.mark.asyncio
async def test_process_text_message_loads_and_saves_memory(monkeypatch):
    captured = {}
    saved_turns = []

    async def fake_process_text(text_content, user_id=None, conversation_history=None):
        captured["conversation_history"] = conversation_history
        return {
            "content": "Last answer was about coffee.",
            "error": None,
            "status": "success",
            "metadata": {"intent": "invoice_query"},
            "confidence": 0.9,
        }

    async def fake_load_conversation_history(user_id):
        assert user_id == "7"
        return [{"role": "user", "content": "What did I spend on coffee?"}]

    def fake_save_conversation_turn(user_id, **kwargs):
        saved_turns.append({"user_id": user_id, **kwargs})
        return 1

    monkeypatch.setattr(api, "process_text", fake_process_text)
    monkeypatch.setattr(api, "load_conversation_history", fake_load_conversation_history)
    monkeypatch.setattr(api, "save_conversation_turn", fake_save_conversation_turn)

    result = await api.process_text_message(
        message="What about last month?",
        sender="whatsapp:+15551234567",
        user_id="7",
        whatsapp_message_sid="SM123",
    )

    assert captured["conversation_history"] == [
        {"role": "user", "content": "What did I spend on coffee?"}
    ]
    assert saved_turns == [{
        "user_id": "7",
        "user_message": "What about last month?",
        "assistant_message": "Last answer was about coffee.",
        "whatsapp_message_sid": "SM123",
    }]
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_process_whatsapp_message_returns_greeting_content(monkeypatch):
    async def fake_process_text(text_content, user_id=None, conversation_history=None):
        return {
            "content": "Hi, I'm your WhatsApp Invoice Assistant.",
            "error": None,
            "status": "success",
            "metadata": {"intent": "greeting"},
            "confidence": 0.9,
        }

    async def fake_load_conversation_history(user_id):
        return []

    monkeypatch.setattr(api, "process_text", fake_process_text)
    monkeypatch.setattr(api, "extract_user_id_from_sender", lambda sender: "1")
    monkeypatch.setattr(api, "load_conversation_history", fake_load_conversation_history)

    result = await api.process_whatsapp_message({
        "From": "whatsapp:+15551234567",
        "Body": "Hey",
        "NumMedia": "0",
    })

    assert result["status"] == "success"
    assert result["message"].startswith("Hi, I'm your WhatsApp Invoice Assistant")
