"""Clerk authentication helpers shared by the Flask UIs.

The repository serves a plain Flask UI, so it cannot use Clerk's Next.js
middleware. Instead, API requests send Clerk session tokens in the
Authorization header and the backend verifies them against the Clerk JWKS.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from config.settings import get_settings
from utils.phone_numbers import normalize_whatsapp_number


logger = logging.getLogger(__name__)


class ClerkAuthError(Exception):
    """Raised when a Clerk session token is missing or invalid."""


@dataclass(frozen=True)
class ClerkAuthContext:
    """Authenticated Clerk user context extracted from a verified JWT."""

    clerk_user_id: str
    session_id: Optional[str]
    issuer: Optional[str]
    claims: Dict[str, Any]


@dataclass(frozen=True)
class ClerkVerifiedPhoneProfile:
    """Verified Clerk profile details used to create the app user."""

    clerk_user_id: str
    phone_number: str
    name: Optional[str]
    email: Optional[str]


def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_clerk_publishable_key() -> Optional[str]:
    """Return the configured Clerk publishable key for the browser."""

    return get_settings().effective_clerk_publishable_key


def get_clerk_secret_key() -> Optional[str]:
    """Return the configured Clerk secret key, if available."""

    return get_settings().clerk_secret_key


def is_clerk_enabled() -> bool:
    """Whether Clerk auth should be enabled in the UI."""

    return bool(get_clerk_publishable_key())


def is_auth_required() -> bool:
    """Whether authenticated API access is required."""

    configured = get_settings().clerk_require_auth
    if configured is not None:
        return bool(configured)
    return is_clerk_enabled()


def is_verified_phone_required() -> bool:
    """Whether web accounts must have a verified Clerk phone number."""

    configured = get_settings().clerk_require_verified_phone
    if configured is not None:
        return bool(configured)
    return is_auth_required()


def derive_clerk_issuer_from_publishable_key(
    publishable_key: Optional[str] = None,
) -> Optional[str]:
    """Derive the Clerk Frontend API issuer from a publishable key.

    Clerk publishable keys encode the Frontend API domain in their third
    underscore-delimited segment. The decoded value ends with a "$" delimiter.
    """

    publishable_key = publishable_key or get_clerk_publishable_key()
    if not publishable_key:
        return None

    try:
        encoded_domain = publishable_key.split("_", 2)[2]
        padding = "=" * (-len(encoded_domain) % 4)
        decoded = base64.urlsafe_b64decode(encoded_domain + padding).decode()
        domain = decoded.rstrip("$")
        if not domain:
            return None
        return domain if domain.startswith("http") else f"https://{domain}"
    except Exception:
        return None


def get_clerk_issuer() -> Optional[str]:
    """Return the allowed Clerk issuer for JWT verification."""

    return get_settings().clerk_jwt_issuer or derive_clerk_issuer_from_publishable_key()


def get_clerk_jwks_url(issuer: Optional[str] = None) -> Optional[str]:
    """Return the JWKS URL used to verify Clerk session tokens."""

    configured = get_settings().clerk_jwks_url
    if configured:
        return configured
    issuer = issuer or get_clerk_issuer()
    if not issuer:
        return None
    return f"{issuer.rstrip('/')}/.well-known/jwks.json"


def get_authorized_parties() -> Iterable[str]:
    """Return optional allowed `azp` values for Clerk tokens."""

    parties = get_settings().clerk_authorized_parties
    return [party.strip() for party in parties.split(",") if party.strip()]


def get_auth_config() -> Dict[str, Any]:
    """Return public auth configuration for the frontend."""

    publishable_key = get_clerk_publishable_key()
    return {
        "provider": "clerk",
        "enabled": bool(publishable_key),
        "required": is_auth_required(),
        "phone_auth_required": is_verified_phone_required(),
        "publishable_key": publishable_key,
        "issuer": get_clerk_issuer(),
    }


def extract_session_token(flask_request: Any) -> Optional[str]:
    """Extract a Clerk session token from Authorization or __session cookie."""

    auth_header = flask_request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return flask_request.cookies.get("__session")


def verify_clerk_token(token: str) -> ClerkAuthContext:
    """Verify a Clerk JWT and return the authenticated user context."""

    try:
        import jwt
        from jwt import PyJWKClient
    except ImportError as exc:
        raise ClerkAuthError(
            "PyJWT with crypto support is required for Clerk token verification"
        ) from exc

    issuer = get_clerk_issuer()
    if not issuer:
        raise ClerkAuthError("Clerk issuer is not configured")

    jwks_url = get_clerk_jwks_url(issuer)
    if not jwks_url:
        raise ClerkAuthError("Clerk JWKS URL is not configured")

    try:
        unverified_claims = jwt.decode(token, options={"verify_signature": False})
    except Exception as exc:
        raise ClerkAuthError("Could not decode Clerk token") from exc

    token_issuer = unverified_claims.get("iss")
    if token_issuer != issuer:
        raise ClerkAuthError("Clerk token issuer does not match this application")

    jwk_client = PyJWKClient(jwks_url)
    try:
        signing_key = jwk_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"require": ["exp", "iat", "nbf", "sub"]},
        )
    except Exception as exc:
        raise ClerkAuthError("Invalid Clerk session token") from exc

    authorized_parties = set(get_authorized_parties())
    token_party = claims.get("azp")
    if authorized_parties and token_party not in authorized_parties:
        raise ClerkAuthError("Clerk token is not authorized for this origin")

    clerk_user_id = claims.get("sub")
    if not clerk_user_id:
        raise ClerkAuthError("Clerk token does not include a user id")

    return ClerkAuthContext(
        clerk_user_id=clerk_user_id,
        session_id=claims.get("sid"),
        issuer=claims.get("iss"),
        claims=claims,
    )


def verify_clerk_request(flask_request: Any) -> ClerkAuthContext:
    """Verify the Clerk session attached to a Flask request."""

    token = extract_session_token(flask_request)
    if not token:
        raise ClerkAuthError("Missing Clerk session token")
    return verify_clerk_token(token)


def _clerk_api_base_url() -> str:
    return get_settings().clerk_api_url.rstrip("/")


def require_fresh_session(
    auth_context: ClerkAuthContext,
    *,
    max_age_seconds: Optional[int] = None,
) -> None:
    """Require a recently issued Clerk session token for sensitive actions."""

    max_age_seconds = (
        get_settings().clerk_step_up_max_age_seconds
        if max_age_seconds is None
        else int(max_age_seconds)
    )
    if max_age_seconds <= 0:
        return

    issued_at = auth_context.claims.get("auth_time") or auth_context.claims.get("iat")
    try:
        issued_timestamp = int(issued_at)
    except (TypeError, ValueError) as exc:
        raise ClerkAuthError("Refresh your sign-in session before approving this upload.") from exc

    now_timestamp = int(datetime.now(timezone.utc).timestamp())
    if now_timestamp - issued_timestamp > max_age_seconds:
        raise ClerkAuthError("Refresh your sign-in session before approving this upload.")


def fetch_clerk_user(clerk_user_id: str) -> Dict[str, Any]:
    """Fetch the canonical Clerk user profile from the Backend API."""

    secret_key = get_clerk_secret_key()
    if not secret_key:
        raise ClerkAuthError("Clerk secret key is required to verify phone ownership")

    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - project dependency guard
        raise ClerkAuthError("httpx is required to fetch Clerk user profiles") from exc

    url = f"{_clerk_api_base_url()}/users/{clerk_user_id}"
    try:
        response = httpx.get(
            url,
            headers={"Authorization": f"Bearer {secret_key}"},
            timeout=10,
        )
    except Exception as exc:
        raise ClerkAuthError("Could not contact Clerk to verify the phone number") from exc

    if response.status_code == 404:
        raise ClerkAuthError("Clerk user was not found")
    if response.status_code >= 400:
        logger.warning("Clerk user lookup failed status=%s body=%s", response.status_code, response.text[:300])
        raise ClerkAuthError("Could not verify this Clerk phone number")

    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _value(data: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data:
            return data[key]
    return None


def _is_verified_phone(phone_record: Dict[str, Any]) -> bool:
    if phone_record.get("verified") is True:
        return True
    verification = phone_record.get("verification")
    if isinstance(verification, dict):
        status = str(_value(verification, "status", "state") or "").lower()
        return status == "verified"
    return False


def _primary_or_first_verified_phone(user_payload: Dict[str, Any]) -> Optional[str]:
    phone_numbers = _value(user_payload, "phone_numbers", "phoneNumbers")
    if not isinstance(phone_numbers, list):
        return None

    primary_id = _value(user_payload, "primary_phone_number_id", "primaryPhoneNumberId")
    verified_records = [
        phone for phone in phone_numbers
        if isinstance(phone, dict) and _is_verified_phone(phone)
    ]
    if not verified_records:
        return None

    primary_record = next(
        (
            phone for phone in verified_records
            if primary_id and _value(phone, "id") == primary_id
        ),
        verified_records[0],
    )
    phone_value = _value(primary_record, "phone_number", "phoneNumber", "phone")
    return normalize_whatsapp_number(phone_value, default="") or None


def _primary_email(user_payload: Dict[str, Any]) -> Optional[str]:
    email_addresses = _value(user_payload, "email_addresses", "emailAddresses")
    if not isinstance(email_addresses, list):
        return None
    primary_id = _value(user_payload, "primary_email_address_id", "primaryEmailAddressId")
    email_record = next(
        (
            email for email in email_addresses
            if isinstance(email, dict) and primary_id and _value(email, "id") == primary_id
        ),
        None,
    )
    if not email_record:
        email_record = next((email for email in email_addresses if isinstance(email, dict)), None)
    if not email_record:
        return None
    email = _value(email_record, "email_address", "emailAddress", "email")
    return str(email).strip() or None


def verified_phone_profile_from_clerk(
    auth_context: ClerkAuthContext,
) -> ClerkVerifiedPhoneProfile:
    """Return the verified Clerk phone profile, or raise a user-safe error."""

    user_payload = fetch_clerk_user(auth_context.clerk_user_id)
    phone_number = _primary_or_first_verified_phone(user_payload)
    if not phone_number:
        raise ClerkAuthError(
            "Sign in with a verified phone number before opening the workspace."
        )

    first_name = str(_value(user_payload, "first_name", "firstName") or "").strip()
    last_name = str(_value(user_payload, "last_name", "lastName") or "").strip()
    full_name = " ".join(value for value in [first_name, last_name] if value).strip() or None

    return ClerkVerifiedPhoneProfile(
        clerk_user_id=auth_context.clerk_user_id,
        phone_number=phone_number,
        name=full_name,
        email=_primary_email(user_payload),
    )
