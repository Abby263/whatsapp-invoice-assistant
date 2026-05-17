"""User-scoped upload storage and media registry helpers."""

from __future__ import annotations

import logging
import mimetypes
import os
from datetime import datetime
from typing import Any, Dict, Optional, Union
from uuid import UUID

from storage.supabase_storage_handler import SupabaseStorageHandler

logger = logging.getLogger(__name__)


def store_user_upload(
    file_path: str,
    file_name: str,
    user_id: Union[str, UUID, int],
    document_type: str,
    metadata: Optional[Dict[str, Any]] = None,
    content_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Upload the original user file to private user-scoped storage."""

    with open(file_path, "rb") as handle:
        file_bytes = handle.read()

    resolved_content_type = (
        content_type
        or mimetypes.guess_type(file_name)[0]
        or "application/octet-stream"
    )
    storage_handler = SupabaseStorageHandler()
    storage_metadata = storage_handler.upload_file(
        file_content=file_bytes,
        file_name=file_name,
        user_id=user_id,
        content_type=resolved_content_type,
        file_type=document_type,
        metadata=metadata or {},
    )
    storage_metadata["access_scope"] = "user"
    storage_metadata["user_scope_prefix"] = storage_handler.generate_user_path(user_id, document_type)
    storage_metadata["storage_class"] = "original_upload"
    return storage_metadata


def record_media_upload(
    user_id: Union[str, UUID, int],
    file_storage: Dict[str, Any],
    status: str = "uploaded",
    invoice_id: Optional[Union[str, int]] = None,
    processing_metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Create or update the media table row for an uploaded file."""

    try:
        user_id_value = _coerce_user_id(user_id)
    except ValueError:
        logger.warning("Skipping media registry for non-integer user_id=%s", user_id)
        return None

    try:
        from database.connection import get_db_session
        from database.schemas import Media

        session = get_db_session()
        try:
            checksum = file_storage.get("checksum_sha256")
            media = None
            if checksum:
                media = (
                    session.query(Media)
                    .filter(Media.user_id == user_id_value, Media.content_hash == checksum)
                    .first()
                )
            file_path_value = file_storage.get("file_key") or file_storage.get("path") or ""
            if not media and file_path_value:
                media = (
                    session.query(Media)
                    .filter(Media.user_id == user_id_value, Media.file_path == file_path_value)
                    .first()
                )

            if not media:
                media = Media(
                    user_id=user_id_value,
                    filename=file_storage.get("original_filename") or os.path.basename(file_path_value or "upload"),
                    original_filename=file_storage.get("original_filename"),
                    file_path=file_path_value,
                    file_url=file_storage.get("url") or "",
                    content_hash=checksum,
                    content_type=file_storage.get("content_type") or "application/octet-stream",
                    file_size=file_storage.get("file_size"),
                    file_type=_media_file_type(file_storage.get("content_type")),
                    created_at=datetime.utcnow(),
                )
                session.add(media)

            if invoice_id is not None:
                media.invoice_id = int(invoice_id)
            media.filename = file_storage.get("original_filename") or media.filename
            media.original_filename = file_storage.get("original_filename") or media.original_filename
            media.file_path = file_path_value or media.file_path
            media.file_url = file_storage.get("url") or media.file_url
            media.content_hash = checksum or media.content_hash
            media.content_type = file_storage.get("content_type") or media.content_type
            media.file_size = file_storage.get("file_size") or media.file_size
            media.file_type = _media_file_type(media.content_type)
            media.status = status
            media.processing_metadata = {
                **(media.processing_metadata if isinstance(media.processing_metadata, dict) else {}),
                **(processing_metadata or {}),
                "file_storage": file_storage,
                "user_scope_prefix": file_storage.get("user_scope_prefix"),
                "access_scope": "user",
            }
            media.updated_at = datetime.utcnow()
            session.commit()
            return {
                "media_id": str(media.id),
                "status": media.status,
                "file_path": media.file_path,
                "content_hash": media.content_hash,
            }
        finally:
            session.close()
    except Exception as exc:
        logger.warning("Could not persist media upload registry row: %s", exc)
        return None


def _coerce_user_id(user_id: Union[str, UUID, int]) -> int:
    if isinstance(user_id, int):
        return user_id
    if isinstance(user_id, str) and user_id.isdigit():
        return int(user_id)
    raise ValueError(f"Invalid integer user_id: {user_id}")


def _media_file_type(content_type: Optional[str]) -> str:
    value = (content_type or "").lower()
    if "image" in value:
        return "image"
    if "pdf" in value:
        return "pdf"
    if "spreadsheet" in value or "excel" in value:
        return "excel"
    if "word" in value:
        return "word"
    if "text" in value or "csv" in value:
        return "text"
    return "other"
