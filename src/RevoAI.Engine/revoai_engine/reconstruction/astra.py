"""GPT-6 Astra provider for BIM plan generation.

The model is asked for a structured, scan-bounded floor/wall plan. The response
is not trusted directly: it goes through the same external-plan validation as a
hand-written JSON file before it can reach Revit.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .errors import provider_failed

DEFAULT_MODEL = "gpt-6-astra"
DEFAULT_BASE_URL = "https://api.openai.com/v1"

_SYSTEM_PROMPT = """You are an architectural BIM reconstruction model working from
a laser scan of a building. Return only the requested JSON plan.

Rules:
- Use metres and the scan's existing coordinate system. Never re-centre.
- Use only the supplied scan evidence. Do not invent rooms or elements that the
  evidence does not support.
- Levels must be vertical clusters of floor evidence.
- Floor boundaries must be closed or clearly ordered polygons with at least
  three XYZ points. Keep them simple; do not add holes in this phase.
- Walls must be centrelines with a start, end and height.
- Confidence is a 0-1 fit/evidence score, not a claim of measured accuracy.
- Do not include doors, windows, ceilings, furniture or stairs in this version.
"""

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["method", "levels", "floors", "walls"],
    "properties": {
        "method": {"type": "string"},
        "levels": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "name", "elevationMeters"],
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "elevationMeters": {"type": "number"},
                },
            },
        },
        "floors": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "levelId", "boundary", "confidence"],
                "properties": {
                    "id": {"type": "string"},
                    "levelId": {"type": "string"},
                    "boundary": {
                        "type": "array",
                        "minItems": 3,
                        "items": {
                            "type": "array",
                            "minItems": 3,
                            "maxItems": 3,
                            "items": {"type": "number"},
                        },
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        "walls": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "levelId", "start", "end", "heightMeters", "confidence"],
                "properties": {
                    "id": {"type": "string"},
                    "levelId": {"type": "string"},
                    "start": {
                        "type": "array",
                        "minItems": 3,
                        "maxItems": 3,
                        "items": {"type": "number"},
                    },
                    "end": {
                        "type": "array",
                        "minItems": 3,
                        "maxItems": 3,
                        "items": {"type": "number"},
                    },
                    "heightMeters": {"type": "number", "minimum": 0.5, "maximum": 10},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
    },
}


def request_astra_plan(
    context: dict[str, Any],
    *,
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
    base_url: str | None = None,
    timeout_seconds: float = 180.0,
) -> dict[str, Any]:
    key = api_key or os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise provider_failed(
            "OPENAI_API_KEY is not set for the Revo engine process.",
            data="Set the environment variable and restart Revit so the child process inherits it.",
        )

    base = (base_url or os.environ.get("OPENAI_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    body = {
        "model": model or DEFAULT_MODEL,
        "reasoning_effort": "low",
        "max_completion_tokens": 16000,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Build the floor and wall plan from this scan evidence:\n"
                    + json.dumps(context, ensure_ascii=False, allow_nan=False)
                ),
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "revo_bim_plan",
                "strict": True,
                "schema": _SCHEMA,
            },
        },
    }

    request = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = _safe_body(exc)
        raise provider_failed(
            f"GPT-6 Astra request failed with HTTP {exc.code}.",
            data=detail,
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise provider_failed(
            "Could not reach the OpenAI API from the Revo engine.",
            data=str(exc),
        ) from exc

    try:
        payload = json.loads(raw)
        message = payload["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise provider_failed(
            "GPT-6 Astra returned an unexpected response shape.",
            data=raw[:2000],
        ) from exc

    if isinstance(message, dict):
        return message
    if isinstance(message, list):
        message = "".join(
            part.get("text", "") for part in message if isinstance(part, dict)
        )
    if not isinstance(message, str):
        raise provider_failed("GPT-6 Astra returned no text content.")

    text = message.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].lstrip()

    try:
        plan = json.loads(text)
    except ValueError as exc:
        raise provider_failed(
            "GPT-6 Astra did not return valid JSON.",
            data=text[:2000],
        ) from exc

    if not isinstance(plan, dict):
        raise provider_failed("GPT-6 Astra returned JSON that is not an object.")
    return plan


def _safe_body(error: urllib.error.HTTPError) -> str:
    try:
        return error.read().decode("utf-8", errors="replace")[:2000]
    except Exception:
        return ""
