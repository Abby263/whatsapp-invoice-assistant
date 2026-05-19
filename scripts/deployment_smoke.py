"""Post-deploy smoke checks for the hosted Flask application."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _get_json(client: httpx.Client, path: str) -> Dict[str, Any]:
    response = client.get(path)
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def run_smoke(base_url: str, timeout: float) -> Dict[str, Any]:
    checks = []
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout) as client:
        health = _get_json(client, "/health")
        checks.append(
            {
                "name": "health",
                "ok": health.get("status") == "ok" and "backend_enabled" in health,
                "details": {
                    "runtime": health.get("runtime"),
                    "backend_enabled": health.get("backend_enabled"),
                },
            }
        )

        auth_config = _get_json(client, "/api/auth/config")
        auth = (
            auth_config.get("auth") if isinstance(auth_config.get("auth"), dict) else {}
        )
        checks.append(
            {
                "name": "auth_config",
                "ok": auth_config.get("status") == "success"
                and auth.get("provider") == "clerk",
                "details": {
                    "enabled": auth.get("enabled"),
                    "required": auth.get("required"),
                    "phone_auth_required": auth.get("phone_auth_required"),
                },
            }
        )

    return {
        "status": "success" if all(check["ok"] for check in checks) else "error",
        "base_url": base_url,
        "checks": checks,
    }


def _default_options() -> Tuple[str, float]:
    try:
        from config.settings import get_settings

        settings = get_settings()
        return (
            settings.deployment_smoke_base_url,
            settings.deployment_smoke_timeout_seconds,
        )
    except Exception:
        base_url = os.environ.get(
            "DEPLOYMENT_SMOKE_BASE_URL",
            "https://whatsapp-invoice-assistant.vercel.app",
        )
        timeout = float(os.environ.get("DEPLOYMENT_SMOKE_TIMEOUT_SECONDS", "10"))
        return base_url, timeout


def main() -> int:
    default_base_url, default_timeout = _default_options()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=default_base_url)
    parser.add_argument("--timeout", type=float, default=default_timeout)
    args = parser.parse_args()

    result = run_smoke(args.base_url, args.timeout)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
