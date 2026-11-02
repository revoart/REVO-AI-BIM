"""DeepSeek Go provider for AI scan-to-BIM schedules.

DeepSeek Go is called through an OpenAI-compatible chat completions endpoint.
The model receives measured metadata plus orthographic depth snapshots. Its
response is a schedule that is validated locally before Revit can build it.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from typing import Any

from ..analysis.snapshots import image_data_urls
from .errors import provider_failed

DEFAULT_MODEL = "deepseek-go"
DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
MODEL_ENV = "REVOAI_AI_MODEL"
BASE_URL_ENV = "REVOAI_AI_BASE_URL"
API_KEY_ENVS = ("DEEPSEEK_API_KEY", "REVOAI_AI_API_KEY", "OPENAI_API_KEY")

_SYSTEM_PROMPT = """You are a senior scan-to-BIM surveyor and Revit modeller.
Follow this order exactly:

MEASURE -> WRITE A SCHEDULE -> BUILD FROM THE SCHEDULE -> VERIFY AGAINST THE SCAN.

Hard rules:
- Use metres and the scan's existing coordinate system. Never recentre or rotate.
- Every element must trace to measured evidence or be marked ASSUMED and listed.
- Do not invent interiors, openings or roof geometry the snapshots do not support.
- Wall thickness, floor thickness and roof thickness are ASSUMED unless proven.
- Openings are voids in their host wall. Doors and windows are hosted in those
  openings, never floating objects.
- A level is a storey, not a near-coplanar duplicate. Keep levels at least 2.0 m
  apart for a normal building.
- Use the plan and elevation snapshots. Check the right/up axes before measuring.
- If evidence is weak, still propose the most likely element but set
  `source` to ASSUMED and add its id to `verify`.
- Do not include anything you cannot place in the schedule.

Return one JSON object with this shape:
{
  "units": "m",
  "datum": "...",
  "axes": "...",
  "levels": [{"id":"L1","name":"Level 1","elevationMeters":0.0}],
  "walls": [{"id":"W1","levelId":"L1","start":[x,y,z],"end":[x,y,z],
             "thicknessMeters":0.2,"heightMeters":2.7,
             "source":"MEASURED","verify":false}],
  "floors": [{"id":"F1","levelId":"L1","boundary":[[x,y,z],...],
              "thicknessMeters":0.2,"source":"MEASURED"}],
  "openings": [{"id":"O1","hostWallId":"W1","kind":"door",
                "centerMeters":2.0,"widthMeters":0.9,
                "sillMeters":0.0,"headMeters":2.1,"source":"MEASURED"}],
  "roofs": [{"id":"R1","levelId":"L1","boundary":[[x,y,z],...],
             "pitchDegrees":0.0,"thicknessMeters":0.2,"source":"ASSUMED"}],
  "columns": [{"id":"C1","levelId":"L1","center":[x,y],
               "widthMeters":0.3,"depthMeters":0.3,"heightMeters":2.7,
               "source":"ASSUMED"}],
  "stairs": [],
  "assumptions": ["..."],
  "verify": ["W1"]
}
"""


def _api_key() -> str:
    for name in API_KEY_ENVS:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _model(model: str | None) -> str:
    return (model or os.environ.get(MODEL_ENV) or DEFAULT_MODEL).strip()


def _base_url() -> str:
    return (
        os.environ.get(BASE_URL_ENV)
        or os.environ.get("OPENAI_BASE_URL")
        or DEFAULT_BASE_URL
    ).rstrip("/")


def request_ai_schedule(
    context: dict[str, Any],
    snapshots: dict[str, Any],
    *,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    timeout_seconds: float = 240.0,
) -> dict[str, Any]:
    key = api_key or _api_key()
    if not key:
        raise provider_failed(
            "No DeepSeek Go API key is configured for the engine.",
            data="Set DEEPSEEK_API_KEY (or REVOAI_AI_API_KEY) and restart Revit.",
        )

    base = (base_url or _base_url()).rstrip("/")
    selected_model = _model(model)
    images = image_data_urls(snapshots)
    text = (
        "Create the measured BIM schedule from this scan. "
        "The attached images are orthographic depth snapshots; the metadata gives "
        "their axes and scale. Prefer measured geometry over assumptions.\n\n"
        + json.dumps(
            {
                "scan": context,
                "snapshots": {
                    key: value
                    for key, value in snapshots.items()
                    if key != "images"
                },
            },
            ensure_ascii=False,
            allow_nan=False,
        )
    )

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
        "model": selected_model,
        "temperature": 0.1,
        "max_tokens": 16000,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "response_format": {"type": "json_object"},
    }

    try:
        response = _post(base, key, payload, timeout_seconds)
    except _ImageRejected:
        # Some OpenAI-compatible providers are text-only. Retry with the measured
        # metadata and snapshot dimensions, never with fabricated image content.
        payload["messages"][1]["content"] = (
            text
            + "\n\nThe provider rejected inline images. Use the snapshot metadata "
            "dimensions and the measured segmentation; mark uncertain items ASSUMED."
        )
        response = _post(base, key, payload, timeout_seconds)

    return _parse_schedule(response)


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
        if exc.code == 400 and any(
            term in detail.lower()
            for term in ("image", "vision", "multimodal", "content type")
        ):
            raise _ImageRejected() from exc
        raise provider_failed(
            f"DeepSeek Go request failed with HTTP {exc.code}.",
            data=detail,
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise provider_failed(
            "Could not reach the DeepSeek Go endpoint from the Revo engine.",
            data=str(exc),
        ) from exc


def _parse_schedule(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
        message = payload["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise provider_failed(
            "DeepSeek Go returned an unexpected response shape.",
            data=raw[:2000],
        ) from exc

    if isinstance(message, dict):
        schedule = message
    else:
        if isinstance(message, list):
            message = "".join(
                part.get("text", "")
                for part in message
                if isinstance(part, dict)
            )
        if not isinstance(message, str):
            raise provider_failed("DeepSeek Go returned no text content.")

        text = message.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].lstrip()
        try:
            schedule = json.loads(text)
        except ValueError as exc:
            raise provider_failed(
                "DeepSeek Go did not return valid JSON.",
                data=text[:2000],
            ) from exc

    if not isinstance(schedule, dict):
        raise provider_failed("DeepSeek Go returned JSON that is not an object.")
    return schedule


def _safe_body(error: urllib.error.HTTPError) -> str:
    try:
        return error.read().decode("utf-8", errors="replace")[:4000]
    except Exception:
        return ""
