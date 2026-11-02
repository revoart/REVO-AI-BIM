"""Orthographic depth snapshots for AI-assisted scan-to-BIM.

The AI never gets raw points. It gets measured metadata plus depth-buffered plan
and elevation images with explicit axes and scale. The images are generated
locally with numpy and a small PNG writer, so there is no plotting dependency and
no upload unless the user explicitly runs an AI provider.
"""

from __future__ import annotations

import base64
import json
import struct
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from ..pointcloud import PointCloudStore

METHOD = "orthographic-depth/1"
SNAPSHOT_DIR = "snapshots"
DEFAULT_SIZE = 640
MAX_POINTS = 300_000

# name, up axis, right axis, closeness axis/sign, view direction
_VIEWS = (
    ("plan", "Y", "X", ("Z", 1.0), "+Z"),
    ("south", "Z", "X", ("Y", -1.0), "-Y"),
    ("north", "Z", "X", ("Y", 1.0), "+Y"),
    ("west", "Z", "Y", ("X", -1.0), "-X"),
    ("east", "Z", "Y", ("X", 1.0), "+X"),
)


def _png_bytes(rgb: np.ndarray) -> bytes:
    height, width, _ = rgb.shape
    rows = b"".join(b"\x00" + rgb[y].tobytes() for y in range(height))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(
        b"IDAT", zlib.compress(rows, 6)
    ) + chunk(b"IEND", b"")


def _render(
    positions: np.ndarray,
    size: int,
    up_axis: str,
    right_axis: str,
    closeness_axis: str,
    closeness_sign: float,
) -> tuple[np.ndarray, dict[str, float]]:
    axes = {"X": 0, "Y": 1, "Z": 2}
    right = positions[:, axes[right_axis]]
    up = positions[:, axes[up_axis]]
    closeness = positions[:, axes[closeness_axis]] * closeness_sign

    right_min, right_max = float(np.min(right)), float(np.max(right))
    up_min, up_max = float(np.min(up)), float(np.max(up))
    right_span = max(right_max - right_min, 1e-6)
    up_span = max(up_max - up_min, 1e-6)

    # Keep the aspect ratio so the image is not distorted.
    span = max(right_span, up_span)
    right_scale = size / span
    up_scale = size / span
    u = ((right - right_min) * right_scale).astype(np.int32)
    v = ((up_max - up) * up_scale).astype(np.int32)
    u = np.clip(u, 0, size - 1)
    v = np.clip(v, 0, size - 1)

    depth = np.full((size, size), -np.inf, dtype=np.float64)
    flat = v * size + u
    np.maximum.at(depth.reshape(-1), flat, closeness)

    valid = np.isfinite(depth)
    if not np.any(valid):
        raise ValueError("The scan sample produced an empty snapshot.")

    values = depth[valid]
    low = float(np.percentile(values, 2.0))
    high = float(np.percentile(values, 98.0))
    if high <= low:
        high = low + 1e-6

    normalized = np.clip((depth - low) / (high - low), 0.0, 1.0)
    gray = (normalized * 235.0 + 15.0).astype(np.uint8)
    gray[~valid] = 8

    rgb = np.stack([gray, gray, gray], axis=-1).copy()
    # A light grid every 50 px helps the model judge scale without labels.
    for index in range(50, size, 50):
        rgb[index, :, :] = np.minimum(rgb[index, :, :] + 28, 255)
        rgb[:, index, :] = np.minimum(rgb[:, index, :] + 28, 255)

    metadata = {
        "width": size,
        "height": size,
        "metersPerPixel": span / size,
        "rightAxis": right_axis,
        "upAxis": up_axis,
        "rightMin": right_min,
        "rightMax": right_max,
        "upMin": up_min,
        "upMax": up_max,
        "closenessMin": low,
        "closenessMax": high,
    }
    return rgb, metadata


def generate_snapshots(
    store_path: str,
    *,
    max_points: int = MAX_POINTS,
    size: int = DEFAULT_SIZE,
) -> dict[str, Any]:
    store = PointCloudStore.open(store_path)
    raw = store.sample(int(max_points))
    positions = np.asarray(raw["positions"], dtype=np.float64)
    if positions.size == 0:
        raise ValueError("The scan store contains no points to snapshot.")

    folder = Path(store.path) / "analysis" / SNAPSHOT_DIR
    folder.mkdir(parents=True, exist_ok=True)
    views: list[dict[str, Any]] = []

    for name, up_axis, right_axis, (closeness_axis, sign), direction in _VIEWS:
        rgb, metadata = _render(
            positions, size, up_axis, right_axis, closeness_axis, sign
        )
        path = folder / f"{name}.png"
        path.write_bytes(_png_bytes(rgb))
        views.append(
            {
                "name": name,
                "viewDirection": direction,
                "path": str(path),
                **metadata,
            }
        )

    result = {
        "method": METHOD,
        "scanId": store.metadata.get("scanId", store.path.name),
        "storePath": str(store.path),
        "units": "m",
        "sourceUnits": store.metadata.get("units", {}),
        "bounds": store.metadata.get("bounds", {}),
        "pointCount": store.metadata.get("pointCount", {}),
        "samplePoints": int(positions.shape[0]),
        "views": views,
        "folder": str(folder),
        "createdAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    }
    (folder / "snapshots.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return result


def image_data_urls(snapshots: dict[str, Any], limit: int = 5) -> list[dict[str, str]]:
    """Return OpenAI-compatible image payloads for a multimodal model."""
    payloads: list[dict[str, str]] = []
    for view in snapshots.get("views", [])[:limit]:
        path = Path(view["path"])
        if not path.is_file():
            continue
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        payloads.append(
            {
                "name": view["name"],
                "url": f"data:image/png;base64,{encoded}",
            }
        )
    return payloads
