"""Convert segmentation instances into a native Revit reconstruction plan.

The plan is deliberately simple and auditable: floors become closed boundary
polygons on a level, walls become line segments with a base level and height.
It creates no Revit objects; the C# side owns the transaction.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .. import __version__
from ..analysis import load_segmentation
from .errors import plan_failed

METHOD = "geometric-floor-wall-plan/1"
_ANALYSIS_DIR = "analysis"
_PLAN_FILE = "reconstruction-plan.json"


def create_plan(params) -> dict[str, Any]:
    started = time.perf_counter()
    segmentation = load_segmentation(params.store_path)
    warnings: list[str] = []
    elements = segmentation.get("elements", [])
    store_path = Path(segmentation["storePath"]).resolve()

    threshold = float(params.confidence_threshold)
    floor_elements: list[dict[str, Any]] = []
    wall_elements: list[dict[str, Any]] = []
    ceiling_elements: list[dict[str, Any]] = []
    skipped_confidence = 0
    skipped_boundary = 0

    for element in elements:
        confidence = float(element.get("confidence", 0.0))
        if confidence < threshold:
            skipped_confidence += 1
            continue
        boundary = element.get("boundary") or []
        if len(boundary) < 3:
            skipped_boundary += 1
            continue
        kind = element.get("kind")
        if kind == "floor":
            floor_elements.append(element)
        elif kind == "wall":
            wall_elements.append(element)
        elif kind == "ceiling":
            ceiling_elements.append(element)

    if skipped_confidence:
        warnings.append(
            f"Skipped {skipped_confidence} segment(s) below the confidence threshold."
        )
    if skipped_boundary:
        warnings.append(
            f"Skipped {skipped_boundary} segment(s) without a boundary; rerun Scan Analysis."
        )
    if not floor_elements:
        warnings.append("No floor segment met the threshold; no levels or walls were planned.")

    levels = _build_levels(floor_elements, params.level_tolerance_meters, warnings)
    level_by_id = {level["id"]: level for level in levels}

    floors: list[dict[str, Any]] = []
    for index, element in enumerate(floor_elements, start=1):
        level = _nearest_level(levels, float(element["centroid"][2]))
        boundary = _closed_boundary(element["boundary"])
        if len(boundary) < 3:
            continue
        floors.append(
            {
                "id": f"floor-plan-{index}",
                "sourceSegmentId": element["id"],
                "levelId": level["id"],
                "boundary": boundary,
                "areaM2": round(float(element.get("areaM2", 0.0)), 3),
                "confidence": round(float(element.get("confidence", 0.0)), 3),
            }
        )

    ceiling_zs = sorted(
        float(element["centroid"][2])
        for element in ceiling_elements
        if len(element.get("boundary") or []) >= 3
    )

    walls: list[dict[str, Any]] = []
    fallback_height = float(params.fallback_wall_height_meters)
    fallback_walls = 0
    for index, element in enumerate(wall_elements, start=1):
        level = _base_level_for_wall(levels, float(element["centroid"][2]))
        if level is None:
            warnings.append(f"Skipped {element['id']}: no floor level below the wall.")
            continue

        start, end = _wall_endpoints(element["boundary"])
        if start is None or end is None:
            warnings.append(f"Skipped {element['id']}: wall boundary is degenerate.")
            continue
        length = float(np.linalg.norm(np.asarray(end[:2]) - np.asarray(start[:2])))
        if length < 0.3:
            warnings.append(f"Skipped {element['id']}: wall is shorter than 0.3 m.")
            continue

        base = float(level["elevationMeters"])
        wall_center_z = float(element["centroid"][2])
        higher_ceilings = [z for z in ceiling_zs if z > wall_center_z + 0.2]
        if higher_ceilings:
            height = min(higher_ceilings) - base
            height_source = "ceiling"
        else:
            height = fallback_height
            height_source = "fallback"
            fallback_walls += 1

        if not 0.5 <= height <= 10.0:
            height = fallback_height
            height_source = "fallback"
            fallback_walls += 1

        walls.append(
            {
                "id": f"wall-plan-{index}",
                "sourceSegmentId": element["id"],
                "levelId": level["id"],
                "start": [round(start[0], 6), round(start[1], 6), round(base, 6)],
                "end": [round(end[0], 6), round(end[1], 6), round(base, 6)],
                "heightMeters": round(height, 3),
                "heightSource": height_source,
                "confidence": round(float(element.get("confidence", 0.0)), 3),
            }
        )

    max_elements = int(params.max_elements)
    total = len(floors) + len(walls)
    if total > max_elements:
        warnings.append(
            f"Plan was limited to {max_elements} elements; {total - max_elements} were omitted."
        )
        floors = floors[:max_elements]
        remaining = max_elements - len(floors)
        walls = walls[: max(0, remaining)]

    if fallback_walls:
        warnings.append(
            f"{fallback_walls} wall(s) used the fallback height because no usable ceiling was found."
        )
    if not walls:
        warnings.append("No wall segment met the threshold and produced a valid line.")

    result_path = store_path / _ANALYSIS_DIR / _PLAN_FILE
    result = {
        "scanId": segmentation.get("scanId", store_path.name),
        "storePath": str(store_path),
        "method": METHOD,
        "parameters": {
            "confidenceThreshold": threshold,
            "fallbackWallHeightMeters": fallback_height,
            "levelToleranceMeters": float(params.level_tolerance_meters),
            "maxElements": max_elements,
        },
        "levels": levels,
        "floors": floors,
        "walls": walls,
        "warnings": warnings,
        "resultPath": str(result_path),
        "createdAt": _utc_now(),
        "engineVersion": __version__,
        "elapsedMs": round((time.perf_counter() - started) * 1000.0, 3),
    }
    _write_result(store_path, result)
    return result


def _build_levels(
    floors: list[dict[str, Any]], tolerance: float, warnings: list[str]
) -> list[dict[str, Any]]:
    elevations = sorted(float(element["centroid"][2]) for element in floors)
    clusters: list[list[float]] = []
    for elevation in elevations:
        if not clusters or abs(elevation - float(np.mean(clusters[-1]))) > tolerance:
            clusters.append([elevation])
        else:
            clusters[-1].append(elevation)

    if not clusters:
        return []

    levels = []
    for index, cluster in enumerate(clusters, start=1):
        levels.append(
            {
                "id": f"level-{index}",
                "name": f"Revo Level {index}",
                "elevationMeters": round(float(np.mean(cluster)), 3),
            }
        )
    if len(levels) > 1:
        warnings.append(
            f"Floors were grouped into {len(levels)} levels using a "
            f"{tolerance:g} m tolerance."
        )
    return levels


def _nearest_level(levels: list[dict[str, Any]], z: float) -> dict[str, Any]:
    return min(levels, key=lambda level: abs(float(level["elevationMeters"]) - z))


def _base_level_for_wall(
    levels: list[dict[str, Any]], wall_z: float
) -> dict[str, Any] | None:
    below = [
        level for level in levels if float(level["elevationMeters"]) <= wall_z + 0.05
    ]
    if below:
        return max(below, key=lambda level: float(level["elevationMeters"]))
    return min(levels, key=lambda level: float(level["elevationMeters"])) if levels else None


def _closed_boundary(points: list[list[float]]) -> list[list[float]]:
    cleaned: list[list[float]] = []
    for point in points:
        if len(point) != 3:
            continue
        candidate = [round(float(value), 6) for value in point]
        if not cleaned or candidate != cleaned[-1]:
            cleaned.append(candidate)
    return cleaned


def _wall_endpoints(boundary: list[list[float]]) -> tuple[list[float] | None, list[float] | None]:
    points = np.asarray([point for point in boundary if len(point) == 3], dtype=np.float64)
    if points.shape[0] < 2:
        return None, None

    best_distance = -1.0
    best_pair: tuple[int, int] = (0, 1)
    for first in range(points.shape[0]):
        delta = points - points[first]
        distances = np.einsum("ij,ij->i", delta, delta)
        second = int(np.argmax(distances))
        if distances[second] > best_distance:
            best_distance = float(distances[second])
            best_pair = (first, second)

    return points[best_pair[0]].tolist(), points[best_pair[1]].tolist()


def _write_result(store_path: Path, result: dict[str, Any]) -> None:
    directory = store_path / _ANALYSIS_DIR
    path = directory / _PLAN_FILE
    temp = directory / f".{_PLAN_FILE}.tmp-{uuid.uuid4().hex}"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with temp.open("w", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
        os.replace(temp, path)
    except OSError as exc:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        raise plan_failed(
            f"Could not write the reconstruction plan for '{store_path}'.",
            data=str(exc),
        ) from exc


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
