"""Postgres-backed conversation memory for WhatsApp and web chat."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Union

logger = logging.getLogger(__name__)

DEFAULT_MEMORY_WINDOW = 12
DEFAULT_MAX_STORED_MESSAGES = 200


def _db_modules():
    from database.connection import ensure_application_schema, get_db_session
    from database.schemas import Conversation, Message, MessageRole, WhatsAppMessage

    return ensure_application_schema, get_db_session, Conversation, Message, MessageRole, WhatsAppMessage


def load_user_conversation_history(
    user_id: Optional[Union[str, int]],
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Load the recent active conversation messages for a user."""

    user_id_value = _coerce_user_id(user_id)
    if user_id_value is None:
        return []

    message_limit = _memory_window(limit)
    try:
        ensure_application_schema, get_db_session, _, Message, _, _ = _db_modules()
        ensure_application_schema()
        session = get_db_session()
        try:
            conversation = _get_active_conversation(session, user_id_value)
            if not conversation:
                return []

            messages = (
                session.query(Message)
                .filter(
                    Message.user_id == user_id_value,
                    Message.conversation_id == conversation.id,
                )
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(message_limit)
                .all()
            )
            return [_serialize_message(message) for message in reversed(messages)]
        finally:
            session.close()
    except Exception as exc:
        logger.warning("Could not load conversation memory for user %s: %s", user_id, exc)
        return []


def save_conversation_turn(
    user_id: Optional[Union[str, int]],
    *,
    user_message: Optional[str] = None,
    assistant_message: Optional[str] = None,
    whatsapp_message_sid: Optional[str] = None,
) -> Optional[int]:
    """Persist one user/assistant exchange to the active conversation."""

    user_id_value = _coerce_user_id(user_id)
    if user_id_value is None:
        return None

    try:
        ensure_application_schema, get_db_session, _, Message, MessageRole, WhatsAppMessage = _db_modules()
        entries = [
            (MessageRole.USER, user_message),
            (MessageRole.ASSISTANT, assistant_message),
        ]
        entries = [(role, content) for role, content in entries if _has_content(content)]
        if not entries:
            return None

        ensure_application_schema()
        session = get_db_session()
        try:
            conversation = _get_or_create_active_conversation(session, user_id_value)
            user_message_row: Optional[Message] = None
            for role, content in entries:
                message = Message(
                    user_id=user_id_value,
                    conversation_id=conversation.id,
                    role=role,
                    content=str(content).strip(),
                )
                session.add(message)
                session.flush()
                if role == MessageRole.USER:
                    user_message_row = message

            if whatsapp_message_sid and user_message_row is not None:
                existing = (
                    session.query(WhatsAppMessage)
                    .filter(WhatsAppMessage.whatsapp_message_id == whatsapp_message_sid)
                    .first()
                )
                if existing is None:
                    session.add(
                        WhatsAppMessage(
                            message_id=user_message_row.id,
                            whatsapp_message_id=whatsapp_message_sid,
                        )
                    )

            conversation.updated_at = datetime.utcnow()
            _prune_conversation_messages(session, conversation.id, user_id_value)
            session.commit()
            return int(conversation.id)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except Exception as exc:
        logger.warning("Could not save conversation memory for user %s: %s", user_id, exc)
        return None


def save_conversation_messages(
    user_id: Optional[Union[str, int]],
    messages: Iterable[Dict[str, Any]],
) -> Optional[int]:
    """Persist already-shaped memory messages."""

    user_message = None
    assistant_message = None
    try:
        _, _, _, _, MessageRole, _ = _db_modules()
    except Exception as exc:
        logger.warning("Could not save conversation messages: %s", exc)
        return None

    for message in messages:
        role = str(message.get("role") or "").strip().lower()
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        if role == MessageRole.USER.value:
            user_message = content
        elif role == MessageRole.ASSISTANT.value:
            assistant_message = content
    return save_conversation_turn(
        user_id,
        user_message=user_message,
        assistant_message=assistant_message,
    )


def start_new_conversation(user_id: Optional[Union[str, int]]) -> Optional[int]:
    """Close active conversations for a user and create a fresh memory thread."""

    user_id_value = _coerce_user_id(user_id)
    if user_id_value is None:
        return None

    try:
        ensure_application_schema, get_db_session, Conversation, _, _, _ = _db_modules()
        ensure_application_schema()
        session = get_db_session()
        try:
            (
                session.query(Conversation)
                .filter(Conversation.user_id == user_id_value, Conversation.is_active.is_(True))
                .update({"is_active": False, "updated_at": datetime.utcnow()})
            )
            conversation = Conversation(user_id=user_id_value, is_active=True)
            session.add(conversation)
            session.commit()
            session.refresh(conversation)
            return int(conversation.id)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except Exception as exc:
        logger.warning("Could not start a new conversation for user %s: %s", user_id, exc)
        return None


def _get_active_conversation(session: Any, user_id: int) -> Optional[Any]:
    _, _, Conversation, _, _, _ = _db_modules()
    return (
        session.query(Conversation)
        .filter(Conversation.user_id == user_id, Conversation.is_active.is_(True))
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .first()
    )


def _get_or_create_active_conversation(session: Any, user_id: int) -> Any:
    _, _, Conversation, _, _, _ = _db_modules()
    conversation = _get_active_conversation(session, user_id)
    if conversation:
        return conversation

    conversation = Conversation(user_id=user_id, is_active=True)
    session.add(conversation)
    session.flush()
    return conversation


def _serialize_message(message: Any) -> Dict[str, Any]:
    _, _, _, _, MessageRole, _ = _db_modules()
    role = message.role.value if isinstance(message.role, MessageRole) else str(message.role)
    return {
        "role": role,
        "content": message.content,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


def _prune_conversation_messages(session: Any, conversation_id: int, user_id: int) -> None:
    _, _, _, Message, _, WhatsAppMessage = _db_modules()
    from sqlalchemy import select

    max_messages = _max_stored_messages()
    rows_to_keep = (
        select(Message.id)
        .where(Message.user_id == user_id, Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(max_messages)
    )
    (
        session.query(WhatsAppMessage)
        .filter(
            WhatsAppMessage.message_id.in_(
                session.query(Message.id)
                .filter(
                    Message.user_id == user_id,
                    Message.conversation_id == conversation_id,
                    Message.id.notin_(rows_to_keep),
                )
            )
        )
        .delete(synchronize_session=False)
    )
    (
        session.query(Message)
        .filter(
            Message.user_id == user_id,
            Message.conversation_id == conversation_id,
            Message.id.notin_(rows_to_keep),
        )
        .delete(synchronize_session=False)
    )


def _coerce_user_id(user_id: Optional[Union[str, int]]) -> Optional[int]:
    if user_id is None:
        return None
    try:
        return int(str(user_id))
    except (TypeError, ValueError):
        return None


def _memory_window(limit: Optional[int]) -> int:
    if limit is not None:
        return max(1, int(limit))
    return _positive_int_from_env("CONVERSATION_MEMORY_WINDOW_MESSAGES", DEFAULT_MEMORY_WINDOW)


def _max_stored_messages() -> int:
    return _positive_int_from_env("CONVERSATION_MEMORY_MAX_STORED_MESSAGES", DEFAULT_MAX_STORED_MESSAGES)


def _positive_int_from_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def _has_content(value: Optional[str]) -> bool:
    return bool(str(value or "").strip())
