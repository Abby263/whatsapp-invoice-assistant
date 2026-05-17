"""Tests for outbound Twilio messaging helpers."""

from services import twilio_messaging


def test_processing_ack_is_debounced(monkeypatch):
    sent = []
    twilio_messaging._RECENT_PROCESSING_ACKS.clear()

    def fake_send_whatsapp_message(**kwargs):
        sent.append(kwargs)
        return True

    monkeypatch.setattr(twilio_messaging, "send_whatsapp_message", fake_send_whatsapp_message)
    monkeypatch.setenv("TWILIO_PROCESSING_ACK_ENABLED", "true")
    monkeypatch.setenv("TWILIO_PROCESSING_ACK_COOLDOWN_SECONDS", "60")

    assert twilio_messaging.send_processing_ack(
        to_number="whatsapp:+15551234567",
        from_number="whatsapp:+16473628073",
        body="Received 1 file.",
    ) is True
    assert twilio_messaging.send_processing_ack(
        to_number="whatsapp:+15551234567",
        from_number="whatsapp:+16473628073",
        body="Received 1 file.",
    ) is False
    assert len(sent) == 1

    twilio_messaging._RECENT_PROCESSING_ACKS.clear()
