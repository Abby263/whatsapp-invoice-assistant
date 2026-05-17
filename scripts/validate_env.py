"""Validate runtime environment variables without printing secret values."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
from urllib.parse import urlparse


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key] = value.strip().strip("'").strip('"')
    return values


def _first(values: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = values.get(key) or os.getenv(key)
        if value:
            return value
    return ""


def _is_placeholder(value: str) -> bool:
    if not value:
        return True
    lowered = value.lower()
    without_common_prefix = lowered.removeprefix("ac")
    return (
        len(value) <= 8
        or "your_" in lowered
        or "your-" in lowered
        or "<" in value
        or "placeholder" in lowered
        or (bool(without_common_prefix) and set(without_common_prefix) <= {"x"})
    )


def _project_ref_from_url(url: str) -> str:
    host = urlparse(url).hostname or ""
    if host.endswith(".supabase.co"):
        return host.split(".")[0]
    return ""


def _project_ref_from_jwt(jwt_value: str) -> str:
    if not jwt_value.startswith("eyJ"):
        return ""
    try:
        payload = jwt_value.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode()))
    except Exception:
        return ""
    return str(data.get("ref") or "")


def _status(ok: bool, message: str) -> str:
    return f"{'OK' if ok else 'MISSING'} {message}"


def validate(values: dict[str, str]) -> list[tuple[bool, str]]:
    checks: list[tuple[bool, str]] = []

    supabase_url = _first(values, "NEXT_PUBLIC_SUPABASE_URL", "SUPABASE_URL")
    supabase_ref = _project_ref_from_url(supabase_url)
    checks.append((bool(supabase_ref), "Supabase URL points to a Supabase project"))

    publishable = _first(
        values,
        "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
        "SUPABASE_PUBLISHABLE_KEY",
        "SUPABASE_KEY",
        "SUPABASE_ANON_KEY",
        "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    )
    checks.append((not _is_placeholder(publishable), "Supabase publishable key is set"))

    server_key = _first(values, "SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY")
    server_key_ref = _project_ref_from_jwt(server_key)
    key_matches = not server_key_ref or server_key_ref == supabase_ref
    checks.append(
        (
            not _is_placeholder(server_key) and key_matches,
            "Supabase server key is set for the configured project",
        )
    )

    database_url = _first(values, "DATABASE_URL", "SUPABASE_DATABASE_URL")
    database_host = urlparse(database_url).hostname or ""
    db_matches = not supabase_ref or supabase_ref in database_host
    checks.append(
        (
            not _is_placeholder(database_url) and db_matches,
            "Supabase database URL is set for the configured project",
        )
    )

    direct_url = _first(values, "DIRECT_URL", "SUPABASE_DIRECT_URL")
    direct_host = urlparse(direct_url).hostname or ""
    direct_matches = not supabase_ref or supabase_ref in direct_host
    checks.append(
        (
            not _is_placeholder(direct_url) and direct_matches,
            "Supabase direct/session URL is set for migrations",
        )
    )

    storage_bucket = _first(values, "SUPABASE_STORAGE_BUCKET", "SUPABASE_RECEIPTS_BUCKET")
    checks.append((storage_bucket == "receipts" or bool(storage_bucket), "Supabase storage bucket is set"))

    openai_key = _first(values, "OPENAI_API_KEY")
    checks.append((not _is_placeholder(openai_key) and openai_key.startswith("sk-"), "OpenAI API key is set"))

    openai_model = _first(values, "OPENAI_API_MODEL")
    checks.append((openai_model == "gpt-5.4-mini", "OpenAI model is gpt-5.4-mini"))

    twilio_sid = _first(values, "TWILIO_ACCOUNT_SID")
    checks.append(
        (
            not _is_placeholder(twilio_sid) and twilio_sid.startswith("AC") and len(twilio_sid) >= 34,
            "Twilio Account SID is set",
        )
    )

    twilio_token = _first(values, "TWILIO_AUTH_TOKEN")
    checks.append((not _is_placeholder(twilio_token) and len(twilio_token) >= 16, "Twilio Auth Token is set"))

    twilio_phone = _first(values, "TWILIO_PHONE_NUMBER")
    checks.append(
        (
            not _is_placeholder(twilio_phone) and twilio_phone.startswith("whatsapp:+") and len(twilio_phone) >= 13,
            "Twilio WhatsApp sender uses whatsapp:+ format",
        )
    )

    clerk_publishable = _first(values, "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "CLERK_PUBLISHABLE_KEY")
    checks.append(
        (
            not _is_placeholder(clerk_publishable) and clerk_publishable.startswith("pk_"),
            "Clerk publishable key is set",
        )
    )

    clerk_secret = _first(values, "CLERK_SECRET_KEY")
    checks.append((not _is_placeholder(clerk_secret) and clerk_secret.startswith("sk_"), "Clerk secret key is set"))

    auth_required = _first(values, "CLERK_REQUIRE_AUTH").lower()
    checks.append((auth_required == "true", "Clerk auth is required in production"))

    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env", help="Env file to validate")
    args = parser.parse_args()

    values = _load_env_file(Path(args.env_file))
    checks = validate(values)
    for ok, message in checks:
        print(_status(ok, message))

    return 0 if all(ok for ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
