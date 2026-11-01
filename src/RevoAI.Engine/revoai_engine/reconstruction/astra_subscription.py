"""Revo-managed GPT-6 Astra gateway client.

This is the paid-subscription path: the add-in never holds the OpenAI key. The
Revo backend authenticates the subscriber, applies quota/billing, calls Astra and
returns the same BIM plan JSON used by the file/external validator.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .errors import provider_failed, subscription_quota_exceeded, subscription_required

GATEWAY_URL_ENV = "REVOAI_ASTRA_GATEWAY_URL"
TOKEN_ENV = "REVOAI_SUBSCRIPTION_TOKEN"


def request_subscription_plan(
    context: dict[str, Any],
    *,
    timeout_seconds: float = 240.0,
) -> dict[str, Any]:
    base_url = os.environ.get(GATEWAY_URL_ENV, "").strip().rstrip("/")
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not base_url:
        raise provider_failed(
            "The Revo Astra subscription gateway URL is not configured.",
            data=f"Set {GATEWAY_URL_ENV} to the Revo service endpoint.",
        )
    if not token:
        raise subscription_required(
            "No Revo subscription token is available to the engine.",
            data=f"Set {TOKEN_ENV} after signing in to the subscription.",
        )

    body = {
        "context": context,
        "client": "RevoAI.Revit",
        "capability": "bim-plan",
    }
    request = urllib.request.Request(
        f"{base_url}/v1/astra/plan",
        data=json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = _safe_body(exc)
        if exc.code in (401, 403):
            raise subscription_required(
                "The Revo subscription rejected the session.",
                data=detail,
            ) from exc
        if exc.code in (402, 429):
            raise subscription_quota_exceeded(
                "The Revo subscription quota or billing limit was reached.",
                data=detail,
            ) from exc
        raise provider_failed(
            f"The Revo Astra gateway returned HTTP {exc.code}.",
            data=detail,
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise provider_failed(
            "Could not reach the Revo Astra subscription gateway.",
            data=str(exc),
        ) from exc

    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise provider_failed(
            "The Revo Astra gateway returned invalid JSON.",
            data=raw[:2000],
        ) from exc

    if not isinstance(payload, dict):
        raise provider_failed("The Revo Astra gateway returned a non-object response.")

    plan = payload.get("plan", payload)
    if not isinstance(plan, dict):
        raise provider_failed("The Revo Astra gateway returned no BIM plan object.")
    return plan


def _safe_body(error: urllib.error.HTTPError) -> str:
    try:
        return error.read().decode("utf-8", errors="replace")[:2000]
    except Exception:
        return ""
