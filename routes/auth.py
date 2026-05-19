"""Authentication and phone-link routes for the hosted app."""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from demo import DEMO_LINKS, DEFAULT_USER

from . import shared


bp = Blueprint("auth", __name__)


@bp.get("/api/auth/config")
def auth_config():
    return jsonify({"status": "success", "auth": shared.get_auth_config()})


@bp.get("/api/auth/me")
def auth_me():
    auth_context = shared._require_demo_auth()
    if shared._is_auth_response(auth_context):
        return auth_context
    if shared._live_backend_enabled():
        try:
            return jsonify(
                {
                    "status": "success",
                    "auth": shared.get_auth_config(),
                    "identity": shared.live_backend.get_auth_identity(auth_context),
                }
            )
        except Exception as exc:
            return shared._live_error(exc)
    return jsonify(
        {
            "status": "success",
            "auth": shared.get_auth_config(),
            "identity": shared._auth_identity_payload(auth_context),
        }
    )


@bp.post("/api/auth/sync")
def auth_sync():
    auth_context = shared._require_demo_auth()
    if shared._is_auth_response(auth_context):
        return auth_context
    if shared._live_backend_enabled():
        try:
            identity = shared.live_backend.sync_auth_identity(auth_context)
            return jsonify(
                {
                    "status": "success",
                    "message": "Phone account synchronized",
                    "identity": identity,
                    "linked_user": identity.get("linked_user") if identity else None,
                }
            )
        except ValueError as exc:
            return jsonify(
                {
                    "status": "error",
                    "message": str(exc),
                    "needs_phone": True,
                    "identity": shared.live_backend.get_auth_identity(auth_context),
                }
            ), 409
        except Exception as exc:
            return shared._live_error(exc)

    data = request.get_json(silent=True) or {}
    linked_user = DEMO_LINKS.get(auth_context.clerk_user_id) if auth_context else None
    return jsonify(
        {
            "status": "success",
            "message": "Clerk session synchronized in demo mode",
            "identity": shared._auth_identity_payload(auth_context),
            "linked_user": linked_user,
            "suggested_whatsapp_number": data.get("whatsapp_number") or None,
        }
    )


@bp.post("/api/auth/link-whatsapp")
def auth_link_whatsapp():
    auth_context = shared._require_demo_auth()
    if shared._is_auth_response(auth_context):
        return auth_context
    if shared._live_backend_enabled():
        if not auth_context:
            return jsonify(
                {
                    "status": "error",
                    "message": "Sign in with a verified phone number before opening the workspace.",
                    "auth_required": True,
                    "needs_phone": True,
                }
            ), 401
        try:
            user = shared.live_backend.link_clerk_to_whatsapp(
                auth_context,
                request.get_json(silent=True) or {},
            )
            return jsonify(
                {
                    "status": "success",
                    "message": "Phone account synchronized",
                    "user": user,
                    "identity": {
                        "clerk_user_id": auth_context.clerk_user_id,
                        "linked_user": user,
                        "needs_link": False,
                    },
                }
            )
        except ValueError as exc:
            return jsonify({"status": "error", "message": str(exc), "needs_phone": True}), 409
        except Exception as exc:
            return shared._live_error(exc)
    if not auth_context:
        return jsonify(
            {
                "status": "success",
                "message": "Auth is not configured; demo user remains active.",
                "user": DEFAULT_USER,
                "degraded": True,
            }
        )

    data = request.get_json(silent=True) or {}
    whatsapp_number = shared.live_backend.normalize_whatsapp_number(
        data.get("whatsapp_number"),
        default="",
    )
    if not whatsapp_number:
        return jsonify({"status": "error", "message": "WhatsApp number is required"}), 400
    linked_user = {
        "id": f"demo-{auth_context.clerk_user_id}",
        "name": data.get("name") or "Authenticated User",
        "email": data.get("email") or "",
        "whatsapp_number": whatsapp_number,
        "clerk_user_id": auth_context.clerk_user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "is_new": False,
    }
    DEMO_LINKS[auth_context.clerk_user_id] = linked_user

    return jsonify(
        {
            "status": "success",
            "message": "Linked Clerk account to WhatsApp number in demo mode",
            "user": linked_user,
            "identity": shared._auth_identity_payload(auth_context),
            "degraded": True,
        }
    )
