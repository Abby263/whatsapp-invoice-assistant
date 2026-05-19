"""Tests for API text message response handling."""

import pytest

from workflows import api


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
async def test_process_text_message_ignores_untrusted_supplied_history_for_user(monkeypatch):
    captured = {}

    async def fake_process_text(text_content, user_id=None, conversation_history=None):
        captured["conversation_history"] = conversation_history
        return {
            "content": "Scoped answer.",
            "error": None,
            "status": "success",
            "metadata": {"intent": "invoice_query"},
            "confidence": 0.9,
        }

    async def fake_load_conversation_history(user_id):
        assert user_id == "9"
        return [{"role": "user", "content": "User 9 previous question"}]

    monkeypatch.setattr(api, "process_text", fake_process_text)
    monkeypatch.setattr(api, "load_conversation_history", fake_load_conversation_history)
    monkeypatch.setattr(api, "save_conversation_turn", lambda *args, **kwargs: None)

    await api.process_text_message(
        message="Follow up",
        sender="whatsapp:+15551234567",
        user_id="9",
        conversation_history=[{"role": "user", "content": "Other user private context"}],
    )

    assert captured["conversation_history"] == [
        {"role": "user", "content": "User 9 previous question"}
    ]


@pytest.mark.asyncio
async def test_process_file_message_ignores_untrusted_supplied_history_for_user(monkeypatch, tmp_path):
    captured = {}
    receipt_path = tmp_path / "receipt.jpg"
    receipt_path.write_bytes(b"receipt")

    async def fake_process_file(**kwargs):
        captured["conversation_history"] = kwargs["conversation_history"]
        return {
            "content": "File processed.",
            "metadata": {"intent": "file_processing"},
        }

    async def fake_load_conversation_history(user_id):
        assert user_id == "11"
        return [{"role": "assistant", "content": "User 11 scoped context"}]

    monkeypatch.setattr(api, "process_file", fake_process_file)
    monkeypatch.setattr(api, "load_conversation_history", fake_load_conversation_history)
    monkeypatch.setattr(api, "save_conversation_turn", lambda *args, **kwargs: None)

    await api.process_file_message(
        file_path=str(receipt_path),
        file_name="receipt.jpg",
        mime_type="image/jpeg",
        sender="whatsapp:+15551234567",
        user_id="11",
        conversation_history=[{"role": "assistant", "content": "Other user file context"}],
    )

    assert captured["conversation_history"] == [
        {"role": "assistant", "content": "User 11 scoped context"}
    ]


@pytest.mark.asyncio
async def test_process_whatsapp_message_returns_help_command_without_user_lookup(monkeypatch):
    def fail_user_lookup(sender):
        raise AssertionError("help command must not wait on user lookup")

    def fail_enqueue(*args, **kwargs):
        raise AssertionError("help command must not be queued")

    monkeypatch.setenv("ASYNC_WORK_QUEUE_ENABLED", "true")
    monkeypatch.setenv("ASYNC_TEXT_QUEUE_ENABLED", "true")
    monkeypatch.setattr(api, "extract_user_id_from_sender", fail_user_lookup)
    monkeypatch.setattr(api, "enqueue_job", fail_enqueue)

    result = await api.process_whatsapp_message({
        "From": "whatsapp:+15551234567",
        "Body": "help",
        "NumMedia": "0",
        "MessageSid": "SM_HELP_FAST",
    })

    assert result["status"] == "success"
    assert result["message"].startswith("*Receipt Intelligence*")
    assert result["metadata"]["intent"] == api.IntentType.HELP.value


@pytest.mark.asyncio
async def test_process_whatsapp_text_sends_ack_before_slow_workflow(monkeypatch):
    events = []
    acknowledgements = []
    final_messages = []

    def fake_send_processing_ack(**kwargs):
        events.append("ack")
        acknowledgements.append(kwargs)
        return True

    def fake_send_whatsapp_message(**kwargs):
        events.append("final")
        final_messages.append(kwargs)
        return True

    async def fake_load_conversation_history(user_id):
        events.append("history")
        return []

    async def fake_process_text_message(*args, **kwargs):
        events.append("process_text")
        return {
            "message": "You spent 1,200.00 INR this month.",
            "metadata": {"intent": "invoice_query"},
            "status": "success",
            "type": "text",
            "user_id": "42",
        }

    def fake_extract_user_id(sender):
        events.append("user_lookup")
        return "42"

    monkeypatch.setattr(api, "_claim_webhook_event", lambda sid: {"claimed": True})
    monkeypatch.setattr(api, "_mark_webhook_event_processed", lambda sid, result: None)
    monkeypatch.setattr(api, "send_processing_ack", fake_send_processing_ack)
    monkeypatch.setattr(api, "send_whatsapp_message", fake_send_whatsapp_message)
    monkeypatch.setattr(api, "extract_user_id_from_sender", fake_extract_user_id)
    monkeypatch.setattr(
        api, "load_conversation_history", fake_load_conversation_history
    )
    monkeypatch.setattr(api, "process_text_message", fake_process_text_message)

    result = await api.process_whatsapp_message(
        {
            "From": "whatsapp:+15551234567",
            "To": "whatsapp:+16473628073",
            "Body": "What did I spend this month?",
            "NumMedia": "0",
            "MessageSid": "SM_TEXT_ACK",
        }
    )

    assert events == ["ack", "user_lookup", "history", "process_text", "final"]
    assert acknowledgements[0]["dedupe_key"] == "SM_TEXT_ACK"
    assert "Message Received" in acknowledgements[0]["body"]
    assert final_messages[0]["body"] == "You spent 1,200.00 INR this month."
    assert result["suppress_twiml_response"] is True
    assert result["metadata"]["twilio_processing_ack_sent"] is True
    assert result["metadata"]["twilio_final_reply_sent"] is True


@pytest.mark.asyncio
async def test_process_whatsapp_text_queues_after_ack_when_async_enabled(monkeypatch):
    events = []
    queued_jobs = []

    def fake_send_processing_ack(**kwargs):
        events.append("ack")
        return True

    def fake_enqueue_job(job_type, payload, **kwargs):
        events.append("enqueue")
        queued_jobs.append({"job_type": job_type, "payload": payload, "kwargs": kwargs})
        return {"id": 12, "status": "queued"}

    def fake_process_text_message(*args, **kwargs):
        raise AssertionError("queued text must not process inline")

    monkeypatch.setenv("ASYNC_WORK_QUEUE_ENABLED", "true")
    monkeypatch.setenv("ASYNC_TEXT_QUEUE_ENABLED", "true")
    monkeypatch.setattr(api, "_claim_webhook_event", lambda sid: {"claimed": True})
    monkeypatch.setattr(api, "_mark_webhook_event_processed", lambda sid, result: None)
    monkeypatch.setattr(api, "send_processing_ack", fake_send_processing_ack)
    monkeypatch.setattr(api, "enqueue_job", fake_enqueue_job)
    monkeypatch.setattr(api, "extract_user_id_from_sender", lambda sender: "42")
    monkeypatch.setattr(api, "process_text_message", fake_process_text_message)

    result = await api.process_whatsapp_message(
        {
            "From": "whatsapp:+15551234567",
            "To": "whatsapp:+16473628073",
            "Body": "What did I spend this month?",
            "NumMedia": "0",
            "MessageSid": "SM_QUEUE_TEXT",
        }
    )

    assert events == ["ack", "enqueue"]
    assert queued_jobs[0]["job_type"] == api.JOB_TYPE_TWILIO_TEXT_MESSAGE
    assert queued_jobs[0]["payload"]["SkipProcessingAck"] is True
    assert queued_jobs[0]["payload"]["SendFinalReply"] is True
    assert queued_jobs[0]["kwargs"]["idempotency_key"] == "twilio:SM_QUEUE_TEXT:text"
    assert result["status"] == "queued"
    assert result["suppress_twiml_response"] is True
    assert result["metadata"]["twilio_final_reply_pending"] is True


@pytest.mark.asyncio
async def test_queued_whatsapp_text_sends_final_without_second_ack(monkeypatch):
    acknowledgements = []
    final_messages = []

    async def fake_load_conversation_history(user_id):
        return []

    async def fake_process_text_message(*args, **kwargs):
        return {
            "message": "Your approved spend is 1,200.00 INR.",
            "metadata": {"intent": "invoice_query"},
            "status": "success",
            "type": "text",
            "user_id": "42",
        }

    monkeypatch.setattr(
        api,
        "send_processing_ack",
        lambda **kwargs: acknowledgements.append(kwargs) or True,
    )
    monkeypatch.setattr(
        api,
        "send_whatsapp_message",
        lambda **kwargs: final_messages.append(kwargs) or True,
    )
    monkeypatch.setattr(api, "_mark_webhook_event_processed", lambda sid, result: None)
    monkeypatch.setattr(api, "extract_user_id_from_sender", lambda sender: "42")
    monkeypatch.setattr(
        api, "load_conversation_history", fake_load_conversation_history
    )
    monkeypatch.setattr(api, "process_text_message", fake_process_text_message)

    result = await api.process_queued_whatsapp_message(
        {
            "From": "whatsapp:+15551234567",
            "To": "whatsapp:+16473628073",
            "Body": "What did I spend this month?",
            "NumMedia": "0",
            "MessageSid": "SM_QUEUE_TEXT",
            "SkipProcessingAck": True,
            "SendFinalReply": True,
        }
    )

    assert acknowledgements == []
    assert final_messages[0]["body"] == "Your approved spend is 1,200.00 INR."
    assert result["suppress_twiml_response"] is True
    assert result["metadata"]["twilio_final_reply_sent"] is True


@pytest.mark.asyncio
async def test_process_whatsapp_text_skips_ack_for_fast_help(monkeypatch):
    acknowledgements = []
    final_messages = []

    monkeypatch.setattr(api, "_claim_webhook_event", lambda sid: {"claimed": True})
    monkeypatch.setattr(api, "_mark_webhook_event_processed", lambda sid, result: None)
    monkeypatch.setattr(
        api,
        "send_processing_ack",
        lambda **kwargs: acknowledgements.append(kwargs) or True,
    )
    monkeypatch.setattr(
        api,
        "send_whatsapp_message",
        lambda **kwargs: final_messages.append(kwargs) or True,
    )

    result = await api.process_whatsapp_message(
        {
            "From": "whatsapp:+15551234567",
            "To": "whatsapp:+16473628073",
            "Body": "help",
            "NumMedia": "0",
            "MessageSid": "SM_HELP",
        }
    )

    assert acknowledgements == []
    assert final_messages == []
    assert result["message"].startswith("*Receipt Intelligence*")
    assert "suppress_twiml_response" not in result
