"""Tests for persistent conversation memory."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.schemas import (
    Base,
    Conversation,
    Message,
    MessageRole,
    User,
    WhatsAppMessage,
)
from services import conversation_memory


def _memory_db_modules(session_factory):
    return (
        lambda: None,
        session_factory,
        Conversation,
        Message,
        MessageRole,
        WhatsAppMessage,
    )


def test_save_and_load_user_conversation_history(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    connection = engine.connect()
    transaction = connection.begin()

    def session_factory():
        return Session(bind=connection)

    monkeypatch.setattr(
        conversation_memory,
        "_db_modules",
        lambda: _memory_db_modules(session_factory),
    )

    session = session_factory()
    try:
        user = User(whatsapp_number="+15551234567", name="Memory User")
        session.add(user)
        session.commit()

        conversation_id = conversation_memory.save_conversation_turn(
            user.id,
            user_message="Show my coffee spend",
            assistant_message="You spent 42 on coffee.",
            whatsapp_message_sid="SM-memory-1",
        )

        history = conversation_memory.load_user_conversation_history(user.id)
        whatsapp_message = session.query(WhatsAppMessage).first()

        assert conversation_id is not None
        assert history == [
            {
                "role": "user",
                "content": "Show my coffee spend",
                "created_at": history[0]["created_at"],
            },
            {
                "role": "assistant",
                "content": "You spent 42 on coffee.",
                "created_at": history[1]["created_at"],
            },
        ]
        assert whatsapp_message.whatsapp_message_id == "SM-memory-1"
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def test_start_new_conversation_resets_active_history(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    connection = engine.connect()
    transaction = connection.begin()

    def session_factory():
        return Session(bind=connection)

    monkeypatch.setattr(
        conversation_memory,
        "_db_modules",
        lambda: _memory_db_modules(session_factory),
    )

    session = session_factory()
    try:
        user = User(whatsapp_number="+15557654321", name="Reset User")
        session.add(user)
        session.commit()

        first_conversation_id = conversation_memory.save_conversation_turn(
            user.id,
            user_message="First turn",
            assistant_message="First response",
        )
        reset_conversation_id = conversation_memory.start_new_conversation(user.id)

        assert reset_conversation_id != first_conversation_id
        assert conversation_memory.load_user_conversation_history(user.id) == []
    finally:
        session.close()
        transaction.rollback()
        connection.close()
