"""Claude provider for the Revo AI BIM schedule.

The Anthropic key is read only by this module and used only by
`reconstruction.plan` when the AI provider is selected. It is never logged,
stored in the knowledge DB, or used for any other feature.

Claude receives the same measured metadata and orthographic snapshots as the
DeepSeek provider. Its response is validated locally before Revit can build it.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .deepseek import _SYSTEM_PROMPT as SCHEDULE_PROMPT
from .errors import provider_failed

DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
MODEL_ENV = "REVOAI_CLAUDE_MODEL"
BASE_URL_ENV = "REVOAI_CLAUDE_BASE_URL"
API_KEY_ENVS = ("ANTHROPIC_API_KEY", "REVOAI_ANTHROPIC_API_KEY")
ANTHROPIC_VERSION = "2023-06-01"


def api_key() -> str:
    for name in API_KEY_ENVS:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def selected_model(model: str | None = None) -> str:
    return (model or os.environ.get(MODEL_ENV) or DEFAULT_MODEL).strip()


def is_configured() -> bool:
    return bool(api_key())


def request_claude_schedule(
    context: dict[str, Any],
    snapshots: dict[str, Any],
    *,
    model: str | None = None,
    api_key_override: str | None = None,
    base_url: str | None = None,
    timeout_seconds: float = 240.0,
) -> dict[str, Any]:
    key = api_key_override or api_key()
    if not key:
        raise provider_failed(
            "No Claude API key is configured for the engine.",
            data="Set ANTHROPIC_API_KEY and restart Revit.",
        )

    base = (base_url or os.environ.get(BASE_URL_ENV) or DEFAULT_BASE_URL).rstrip("/")
    selected = selected_model(model)
    text = (
        "Create the measured BIM schedule from this scan. The attached images are "
        "orthographic depth snapshots; the metadata gives their axes and scale. "
        "Prefer measured geometry over assumptions.\n\n"
        + json.dumps(
            {
                "scan": context,
                "snapshots": {
                    key: value for key, value in snapshots.items() if key != "images"
                },
            },
            ensure_ascii=False,
            allow_nan=False,
        )
    )

    content: list[dict[str, Any]] = [{"type": "text", "text": text}]
    image_count = 0
    for view in snapshots.get("views", [])[:5]:
        path = Path(view.get("path", ""))
        if not path.is_file():
            continue
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": encoded,
                },
            }
        )
        image_count += 1

    payload: dict[str, Any] = {
        "model": selected,
        "max_tokens": 16000,
        "temperature": 0.1,
        "system": SCHEDULE_PROMPT,
        "messages": [{"role": "user", "content": content}],
    }

    try:
        raw = _post(base, key, payload, timeout_seconds)
    except _ImageRejected:
        payload["messages"][0]["content"] = [
            {
                "type": "text",
                "text": text
                + "\n\nThe provider rejected inline images. Use the snapshot metadata "
                "dimensions and the measured segmentation; mark uncertain items ASSUMED.",
            }
        ]
        raw = _post(base, key, payload, timeout_seconds)

    schedule = _parse(raw)
    schedule.setdefault("_provider", "claude")
    schedule.setdefault("_model", selected)
    schedule.setdefault("_imageCount", image_count)
    return schedule


class _ImageRejected(Exception):
    pass


def _post(
    base: str,
    key: str,
    payload: dict[str, Any],
    timeout_seconds: float,
) -> str:
    request = urllib.request.Request(
        f"{base}/messages",
        data=json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"),
        headers={
            "x-api-key": key,
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = _safe_body(exc)
        if exc.code in (400, 413) and any(
            term in detail.lower()
            for term in ("image", "media", "vision", "content")
        ):
            raise _ImageRejected() from exc
        if exc.code in (401, 403):
            raise provider_failed(
                "The Claude API rejected the API key.",
                data=detail,
            ) from exc
        raise provider_failed(
            f"Claude request failed with HTTP {exc.code}.",
            data=detail,
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise provider_failed(
            "Could not reach the Claude API from the Revo engine.",
            data=str(exc),
        ) from exc


def _parse(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
        blocks = payload["content"]
        text = "".join(
            block.get("text", "")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise provider_failed(
            "Claude returned an unexpected response shape.",
            data=raw[:2000],
        ) from exc

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].lstrip()
    try:
        schedule = json.loads(cleaned)
    except ValueError as exc:
        raise provider_failed(
            "Claude did not return valid schedule JSON.",
            data=cleaned[:2000],
        ) from exc

    if not isinstance(schedule, dict):
        raise provider_failed("Claude returned JSON that is not an object.")
    return schedule


def _safe_body(error: urllib.error.HTTPError) -> str:
    try:
        return error.read().decode("utf-8", errors="replace")[:4000]
    except Exception:
        return ""
