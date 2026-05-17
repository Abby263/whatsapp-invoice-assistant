"""
Supabase Storage handler for receipt and invoice files.

The application stores file bytes in a private Supabase Storage bucket and
persists only object metadata in Postgres. Signed URLs are generated on demand.
"""

import hashlib
import logging
import mimetypes
import os
import re
import time
from pathlib import Path
from typing import Any, BinaryIO, Dict, Optional, Union
from urllib.parse import quote
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)


class StorageConfigurationError(RuntimeError):
    """Raised when Supabase Storage is not configured."""


def _first_env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""


class SupabaseStorageHandler:
    """Upload, sign, and delete files in Supabase Storage."""

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        api_key: Optional[str] = None,
        bucket_name: Optional[str] = None,
    ) -> None:
        self.supabase_url = (
            supabase_url
            or _first_env("SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL")
        ).rstrip("/")
        secret_key = _first_env("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY")
        publishable_key = _first_env(
            "SUPABASE_KEY",
            "SUPABASE_ANON_KEY",
            "SUPABASE_PUBLISHABLE_KEY",
            "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
            "NEXT_PUBLIC_SUPABASE_ANON_KEY",
        )
        self.api_key = api_key or secret_key or publishable_key or ""
        self.key_source = (
            "explicit"
            if api_key
            else "secret"
            if secret_key
            else "publishable"
            if publishable_key
            else "missing"
        )
        if self.key_source == "publishable":
            logger.warning(
                "Supabase Storage is using a publishable/anon key. Private bucket uploads "
                "and signed URLs usually require SUPABASE_SECRET_KEY or SUPABASE_SERVICE_ROLE_KEY."
            )
        self.bucket_name = bucket_name or _first_env(
            "SUPABASE_STORAGE_BUCKET",
            "SUPABASE_RECEIPTS_BUCKET",
        ) or "receipts"
        self.timeout = float(os.environ.get("SUPABASE_STORAGE_TIMEOUT", "30"))

        if not self.supabase_url:
            raise StorageConfigurationError(
                "SUPABASE_URL or NEXT_PUBLIC_SUPABASE_URL is required for file storage"
            )
        if not self.api_key:
            raise StorageConfigurationError(
                "SUPABASE_SECRET_KEY, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_KEY, "
                "or NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY is required for file storage"
            )

    def upload_file(
        self,
        file_content: Union[bytes, BinaryIO],
        file_name: str,
        user_id: Union[str, UUID, int],
        content_type: Optional[str] = None,
        file_type: str = "invoices",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Upload a file and return normalized storage metadata."""
        file_bytes = file_content if isinstance(file_content, bytes) else file_content.read()
        if not file_bytes:
            raise ValueError("Cannot upload empty file content")

        checksum = hashlib.sha256(file_bytes).hexdigest()
        metadata = metadata or {}
        user_scope_prefix = self.generate_user_path(user_id, file_type)
        object_path = self._generate_file_key(
            file_name=file_name,
            user_id=user_id,
            file_type=file_type,
            checksum=metadata.get("checksum_sha256") or checksum,
        )
        resolved_content_type = (
            content_type
            or mimetypes.guess_type(file_name)[0]
            or "application/octet-stream"
        )

        headers = self._headers(content_type=resolved_content_type)
        headers["x-upsert"] = "false"

        url = self._object_url(object_path)
        logger.info(
            "Uploading file to Supabase Storage bucket=%s path=%s size=%s",
            self.bucket_name,
            object_path,
            len(file_bytes),
        )

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, content=file_bytes, headers=headers)

        if response.status_code >= 400:
            response_text = response.text or ""
            if (
                checksum
                and response.status_code in {400, 409}
                and "exist" in response_text.lower()
            ):
                logger.info(
                    "Supabase Storage object already exists for checksum=%s path=%s",
                    checksum,
                    object_path,
                )
                signed_url = self.generate_url(object_path)
                return {
                    "provider": "supabase",
                    "bucket": self.bucket_name,
                    "file_key": object_path,
                    "path": object_path,
                    "url": signed_url,
                    "content_type": resolved_content_type,
                    "file_size": len(file_bytes),
                    "checksum_sha256": checksum,
                    "user_id": str(user_id),
                    "original_filename": file_name,
                    "metadata": metadata,
                    "access_scope": "user",
                    "user_scope_prefix": user_scope_prefix,
                    "existing_object": True,
                }
            raise RuntimeError(
                f"Supabase Storage upload failed ({response.status_code}): {response_text}"
            )

        signed_url = self.generate_url(object_path)

        return {
            "provider": "supabase",
            "bucket": self.bucket_name,
            "file_key": object_path,
            "path": object_path,
            "url": signed_url,
            "content_type": resolved_content_type,
            "file_size": len(file_bytes),
            "checksum_sha256": checksum,
            "user_id": str(user_id),
            "original_filename": file_name,
            "metadata": metadata,
            "access_scope": "user",
            "user_scope_prefix": user_scope_prefix,
        }

    def generate_url(self, file_key: str, expiration: int = 3600) -> str:
        """Create a signed URL for a private object."""
        sign_url = self._sign_url(file_key)
        headers = self._headers(content_type="application/json")
        payload = {"expiresIn": expiration}

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(sign_url, json=payload, headers=headers)

        if response.status_code >= 400:
            raise RuntimeError(
                f"Supabase signed URL generation failed ({response.status_code}): {response.text}"
            )

        data = response.json()
        signed_path = data.get("signedURL") or data.get("signedUrl")
        if not signed_path:
            raise RuntimeError("Supabase signed URL response did not include signedURL")

        if signed_path.startswith("http"):
            return signed_path
        return f"{self.supabase_url}{signed_path}"

    def delete_file(self, file_key: str) -> bool:
        """Delete a file from Supabase Storage."""
        url = f"{self.supabase_url}/storage/v1/object/{quote(self.bucket_name, safe='')}"
        headers = self._headers(content_type="application/json")

        with httpx.Client(timeout=self.timeout) as client:
            response = client.delete(url, json={"prefixes": [file_key]}, headers=headers)

        if response.status_code >= 400:
            logger.error(
                "Supabase Storage delete failed for %s: %s %s",
                file_key,
                response.status_code,
                response.text,
            )
            return False
        return True

    def generate_user_path(self, user_id: Union[str, UUID, int], file_type: str) -> str:
        """Return the user-scoped object path prefix."""
        return f"users/{self._safe_path_segment(user_id)}/{self._safe_path_segment(file_type)}"

    def _safe_path_segment(self, value: Union[str, UUID, int]) -> str:
        """Normalize a user-controlled value into one Supabase object key segment."""
        safe_value = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip())
        safe_value = safe_value.strip(".-/")
        return safe_value or "unknown"

    def _headers(self, content_type: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "apikey": self.api_key,
            "Content-Type": content_type,
        }

    def _object_url(self, object_path: str) -> str:
        return (
            f"{self.supabase_url}/storage/v1/object/"
            f"{quote(self.bucket_name, safe='')}/{quote(object_path, safe='/')}"
        )

    def _sign_url(self, object_path: str) -> str:
        return (
            f"{self.supabase_url}/storage/v1/object/sign/"
            f"{quote(self.bucket_name, safe='')}/{quote(object_path, safe='/')}"
        )

    def _generate_unique_file_key(
        self,
        file_name: str,
        user_id: Union[str, UUID, int],
        file_type: str,
    ) -> str:
        _, ext = os.path.splitext(file_name)
        timestamp = int(time.time())
        digest = hashlib.sha256(f"{file_name}:{user_id}:{timestamp}".encode()).hexdigest()[:12]
        safe_stem = "".join(
            ch if ch.isalnum() or ch in {"-", "_"} else "_"
            for ch in Path(file_name).stem
        ).strip("_") or "receipt"
        return f"{self.generate_user_path(user_id, file_type)}/{safe_stem}_{digest}{ext}"

    def _generate_file_key(
        self,
        file_name: str,
        user_id: Union[str, UUID, int],
        file_type: str,
        checksum: Optional[str] = None,
    ) -> str:
        if not checksum:
            return self._generate_unique_file_key(file_name, user_id, file_type)

        return f"{self.generate_user_path(user_id, file_type)}/{checksum[:2]}/{checksum}"
