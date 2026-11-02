"""OpenAI provider for the Revo AI BIM schedule.

The OpenAI key is read only by this module and used only by
`reconstruction.plan` to generate the BIM schedule. It is never logged, stored in
the knowledge DB, or used for any other feature.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from ..analysis.snapshots import image_data_urls
from .deepseek import _SYSTEM_PROMPT as SCHEDULE_PROMPT
from .errors import provider_failed

DEFAULT_MODEL = "gpt-6-astra"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
MODEL_ENV = "REVOAI_OPENAI_MODEL"
BASE_URL_ENV = "REVOAI_OPENAI_BASE_URL"
API_KEY_ENVS = ("OPENAI_API_KEY", "REVOAI_OPENAI_API_KEY")


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


def request_openai_schedule(
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
            "No OpenAI API key is configured for the engine.",
            data="Set OPENAI_API_KEY and restart Revit.",
            remedy="Set OPENAI_API_KEY for the user running Revit and restart Revit.",
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

    images = image_data_urls(snapshots)
    content: Any = text
    if images:
        content = [{"type": "text", "text": text}]
        for image in images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": image["url"]},
                }
            )

    payload = {
        "model": selected,
        "temperature": 0.1,
        "max_tokens": 16000,
        "messages": [
            {"role": "system", "content": SCHEDULE_PROMPT},
            {"role": "user", "content": content},
        ],
        "response_format": {"type": "json_object"},
    }

    try:
        raw = _post(base, key, payload, timeout_seconds)
    except _ImageRejected:
        payload["messages"][1]["content"] = (
            text
            + "\n\nThe provider rejected inline images. Use the snapshot metadata "
            "dimensions and the measured segmentation; mark uncertain items ASSUMED."
        )
        raw = _post(base, key, payload, timeout_seconds)

    schedule = _parse(raw)
    schedule.setdefault("_provider", "openai")
    schedule.setdefault("_model", selected)
    schedule.setdefault("_imageCount", len(images))
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
        f"{base}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
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
            for term in ("image", "vision", "multimodal", "content type")
        ):
            raise _ImageRejected() from exc
        if exc.code in (401, 403):
            raise provider_failed("The OpenAI API rejected the API key.", data=detail) from exc
        raise provider_failed(
            f"OpenAI request failed with HTTP {exc.code}.",
            data=detail,
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise provider_failed(
            "Could not reach the OpenAI API from the Revo engine.",
            data=str(exc),
        ) from exc


def _parse(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
        message = payload["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise provider_failed(
            "OpenAI returned an unexpected response shape.",
            data=raw[:2000],
        ) from exc

    if isinstance(message, dict):
        schedule = message
    else:
        if isinstance(message, list):
            message = "".join(
                part.get("text", "") for part in message if isinstance(part, dict)
            )
        if not isinstance(message, str):
            raise provider_failed("OpenAI returned no text content.")
        text = message.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].lstrip()
        try:
            schedule = json.loads(text)
        except ValueError as exc:
            raise provider_failed(
                "OpenAI did not return valid schedule JSON.",
                data=text[:2000],
            ) from exc

    if not isinstance(schedule, dict):
        raise provider_failed("OpenAI returned JSON that is not an object.")
    return schedule


def _safe_body(error: urllib.error.HTTPError) -> str:
    try:
        return error.read().decode("utf-8", errors="replace")[:4000]
    except Exception:
        return ""
