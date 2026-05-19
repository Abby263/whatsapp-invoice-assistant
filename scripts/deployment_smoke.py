"""Post-deploy smoke checks for the hosted Flask application."""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict

import httpx

from config.settings import get_settings


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


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=settings.deployment_smoke_base_url)
    parser.add_argument(
        "--timeout", type=float, default=settings.deployment_smoke_timeout_seconds
    )
    args = parser.parse_args()

    result = run_smoke(args.base_url, args.timeout)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
