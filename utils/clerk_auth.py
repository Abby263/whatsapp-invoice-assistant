"""Clerk authentication helpers shared by the Flask UIs.

The repository serves a plain Flask UI, so it cannot use Clerk's Next.js
middleware. Instead, API requests send Clerk session tokens in the
Authorization header and the backend verifies them against the Clerk JWKS.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional


class ClerkAuthError(Exception):
    """Raised when a Clerk session token is missing or invalid."""


@dataclass(frozen=True)
class ClerkAuthContext:
    """Authenticated Clerk user context extracted from a verified JWT."""

    clerk_user_id: str
    session_id: Optional[str]
    issuer: Optional[str]
    claims: Dict[str, Any]


def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_clerk_publishable_key() -> Optional[str]:
    """Return the configured Clerk publishable key for the browser."""

    return (
        os.getenv("CLERK_PUBLISHABLE_KEY")
        or os.getenv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY")
    )


def get_clerk_secret_key() -> Optional[str]:
    """Return the configured Clerk secret key, if available."""

    return os.getenv("CLERK_SECRET_KEY")


def is_clerk_enabled() -> bool:
    """Whether Clerk auth should be enabled in the UI."""

    return bool(get_clerk_publishable_key())


def is_auth_required() -> bool:
    """Whether authenticated API access is required."""

    configured = os.getenv("CLERK_REQUIRE_AUTH")
    if configured is not None:
        return _truthy(configured)
    return is_clerk_enabled()


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

    return os.getenv("CLERK_JWT_ISSUER") or derive_clerk_issuer_from_publishable_key()


def get_clerk_jwks_url(issuer: Optional[str] = None) -> Optional[str]:
    """Return the JWKS URL used to verify Clerk session tokens."""

    configured = os.getenv("CLERK_JWKS_URL")
    if configured:
        return configured
    issuer = issuer or get_clerk_issuer()
    if not issuer:
        return None
    return f"{issuer.rstrip('/')}/.well-known/jwks.json"


def get_authorized_parties() -> Iterable[str]:
    """Return optional allowed `azp` values for Clerk tokens."""

    parties = os.getenv("CLERK_AUTHORIZED_PARTIES", "")
    return [party.strip() for party in parties.split(",") if party.strip()]


def get_auth_config() -> Dict[str, Any]:
    """Return public auth configuration for the frontend."""

    publishable_key = get_clerk_publishable_key()
    return {
        "provider": "clerk",
        "enabled": bool(publishable_key),
        "required": is_auth_required(),
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
