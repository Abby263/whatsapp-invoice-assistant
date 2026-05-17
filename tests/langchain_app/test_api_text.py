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
