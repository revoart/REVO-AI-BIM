"""Validate and normalize an AI scan-to-BIM schedule.

The model proposes; this module checks. Nothing reaches Revit unless the schedule
is internally coherent and within the scan bounds.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .errors import plan_invalid


def normalize_schedule(
    payload: dict[str, Any],
    *,
    store_metadata: dict[str, Any],
    source_label: str,
) -> dict[str, Any]:
    bounds = store_metadata.get("bounds") or {}
    minimum = np.asarray(bounds.get("min", [-1e9, -1e9, -1e9]), dtype=np.float64)
    maximum = np.asarray(bounds.get("max", [1e9, 1e9, 1e9]), dtype=np.float64)
    margin = 1.0

    warnings: list[str] = []
    assumptions = [str(item) for item in (payload.get("assumptions") or [])]
    verify = [str(item) for item in (payload.get("verify") or [])]

    levels_raw = payload.get("levels")
    if not isinstance(levels_raw, list) or not levels_raw:
        raise plan_invalid("The AI schedule contains no levels.")

    levels: list[dict[str, Any]] = []
    level_ids: set[str] = set()
    used_names: set[str] = set()
    for index, raw in enumerate(levels_raw, start=1):
        if not isinstance(raw, dict):
            raise plan_invalid(f"Level {index} must be an object.")
        level_id = str(raw.get("id") or f"L{index}")
        if level_id in level_ids:
            raise plan_invalid(f"Duplicate level id '{level_id}'.")
        elevation = _finite(raw.get("elevationMeters"), f"level {level_id} elevation")
        if not minimum[2] - margin <= elevation <= maximum[2] + margin:
            raise plan_invalid(f"Level {level_id} is outside the scan height range.")
        name = str(raw.get("name") or f"Revo Level {index}")
        base_name = name
        suffix = 2
        while name in used_names:
            name = f"{base_name} ({suffix})"
            suffix += 1
        used_names.add(name)
        level_ids.add(level_id)
        levels.append(
            {
                "id": level_id,
                "name": name,
                "elevationMeters": round(elevation, 3),
                "source": str(raw.get("source") or "ASSUMED"),
            }
        )
    levels.sort(key=lambda level: level["elevationMeters"])
    for previous, current in zip(levels, levels[1:]):
        if current["elevationMeters"] - previous["elevationMeters"] < 1.5:
            warnings.append(
                f"Levels '{previous['name']}' and '{current['name']}' are closer than 1.5 m; "
                "verify that they are separate storeys."
            )
    level_by_id = {level["id"]: level for level in levels}

    walls: list[dict[str, Any]] = []
    wall_lengths: dict[str, float] = {}
    for index, raw in enumerate(payload.get("walls") or [], start=1):
        if not isinstance(raw, dict):
            raise plan_invalid(f"Wall {index} must be an object.")
        level_id = str(raw.get("levelId") or "")
        if level_id not in level_by_id:
            raise plan_invalid(f"Wall {index} references unknown level '{level_id}'.")
        start = _point(raw.get("start"), f"wall {index} start", minimum, maximum, margin)
        end = _point(raw.get("end"), f"wall {index} end", minimum, maximum, margin)
        length = float(np.linalg.norm(np.asarray(end[:2]) - np.asarray(start[:2])))
        if length < 0.3:
            raise plan_invalid(f"Wall {index} is shorter than 0.3 m.")
        height = _finite(raw.get("heightMeters"), f"wall {index} height")
        if not 0.5 <= height <= 10.0:
            raise plan_invalid(f"Wall {index} height must be 0.5-10 m.")
        thickness = _finite(raw.get("thicknessMeters", 0.2), f"wall {index} thickness")
        if not 0.05 <= thickness <= 1.0:
            raise plan_invalid(f"Wall {index} thickness must be 0.05-1.0 m.")
        wall_id = str(raw.get("id") or f"W{index}")
        wall_lengths[wall_id] = length
        walls.append(
            {
                "id": wall_id,
                "sourceSegmentId": str(raw.get("sourceSegmentId") or wall_id),
                "levelId": level_id,
                "start": start,
                "end": end,
                "heightMeters": round(height, 3),
                "heightSource": str(raw.get("heightSource") or "ai"),
                "thicknessMeters": round(thickness, 3),
                "confidence": _confidence(raw.get("confidence")),
                "source": str(raw.get("source") or "ASSUMED"),
                "verify": bool(raw.get("verify", False)),
            }
        )

    floors: list[dict[str, Any]] = []
    for index, raw in enumerate(payload.get("floors") or [], start=1):
        if not isinstance(raw, dict):
            raise plan_invalid(f"Floor {index} must be an object.")
        level_id = str(raw.get("levelId") or "")
        if level_id not in level_by_id:
            raise plan_invalid(f"Floor {index} references unknown level '{level_id}'.")
        boundary_raw = raw.get("boundary")
        if not isinstance(boundary_raw, list) or len(boundary_raw) < 3:
            raise plan_invalid(f"Floor {index} boundary needs at least three points.")
        boundary = [
            _point(point, f"floor {index} boundary", minimum, maximum, margin)
            for point in boundary_raw
        ]
        thickness = _finite(raw.get("thicknessMeters", 0.2), f"floor {index} thickness")
        if not 0.05 <= thickness <= 1.0:
            raise plan_invalid(f"Floor {index} thickness must be 0.05-1.0 m.")
        floors.append(
            {
                "id": str(raw.get("id") or f"F{index}"),
                "sourceSegmentId": str(raw.get("sourceSegmentId") or f"ai-floor-{index}"),
                "levelId": level_id,
                "boundary": boundary,
                "areaM2": round(_polygon_area(boundary), 3),
                "thicknessMeters": round(thickness, 3),
                "confidence": _confidence(raw.get("confidence")),
                "source": str(raw.get("source") or "ASSUMED"),
            }
        )

    openings: list[dict[str, Any]] = []
    for index, raw in enumerate(payload.get("openings") or [], start=1):
        if not isinstance(raw, dict):
            raise plan_invalid(f"Opening {index} must be an object.")
        host = str(raw.get("hostWallId") or "")
        if host not in wall_lengths:
            raise plan_invalid(f"Opening {index} references unknown wall '{host}'.")
        kind = str(raw.get("kind") or "window").lower()
        if kind not in {"door", "window"}:
            raise plan_invalid(f"Opening {index} kind must be door or window.")
        width = _finite(raw.get("widthMeters"), f"opening {index} width")
        if not 0.3 <= width <= 8.0:
            raise plan_invalid(f"Opening {index} width must be 0.3-8.0 m.")
        center = _finite(raw.get("centerMeters"), f"opening {index} center")
        if not 0.0 <= center <= wall_lengths[host]:
            raise plan_invalid(f"Opening {index} center lies outside its host wall.")
        sill = _finite(raw.get("sillMeters", 0.0), f"opening {index} sill")
        head = _finite(raw.get("headMeters"), f"opening {index} head")
        if not 0.0 <= sill < head <= 10.0:
            raise plan_invalid(f"Opening {index} sill/head are not valid.")
        openings.append(
            {
                "id": str(raw.get("id") or f"O{index}"),
                "hostWallId": host,
                "kind": kind,
                "centerMeters": round(center, 3),
                "widthMeters": round(width, 3),
                "sillMeters": round(sill, 3),
                "headMeters": round(head, 3),
                "source": str(raw.get("source") or "ASSUMED"),
                "verify": bool(raw.get("verify", False)),
            }
        )

    roofs: list[dict[str, Any]] = []
    for index, raw in enumerate(payload.get("roofs") or [], start=1):
        if not isinstance(raw, dict):
            raise plan_invalid(f"Roof {index} must be an object.")
        level_id = str(raw.get("levelId") or "")
        if level_id not in level_by_id:
            raise plan_invalid(f"Roof {index} references unknown level '{level_id}'.")
        boundary_raw = raw.get("boundary")
        if not isinstance(boundary_raw, list) or len(boundary_raw) < 3:
            raise plan_invalid(f"Roof {index} boundary needs at least three points.")
        boundary = [
            _point(point, f"roof {index} boundary", minimum, maximum, margin)
            for point in boundary_raw
        ]
        pitch = _finite(raw.get("pitchDegrees", 0.0), f"roof {index} pitch")
        if not 0.0 <= pitch <= 60.0:
            raise plan_invalid(f"Roof {index} pitch must be 0-60 degrees.")
        thickness = _finite(raw.get("thicknessMeters", 0.2), f"roof {index} thickness")
        if not 0.05 <= thickness <= 1.0:
            raise plan_invalid(f"Roof {index} thickness must be 0.05-1.0 m.")
        roofs.append(
            {
                "id": str(raw.get("id") or f"R{index}"),
                "levelId": level_id,
                "boundary": boundary,
                "pitchDegrees": round(pitch, 2),
                "thicknessMeters": round(thickness, 3),
                "source": str(raw.get("source") or "ASSUMED"),
                "verify": bool(raw.get("verify", True)),
            }
        )

    columns: list[dict[str, Any]] = []
    for index, raw in enumerate(payload.get("columns") or [], start=1):
        if not isinstance(raw, dict):
            raise plan_invalid(f"Column {index} must be an object.")
        level_id = str(raw.get("levelId") or "")
        if level_id not in level_by_id:
            raise plan_invalid(f"Column {index} references unknown level '{level_id}'.")
        center = raw.get("center")
        if not isinstance(center, list) or len(center) != 2:
            raise plan_invalid(f"Column {index} center must be [x, y].")
        x = _finite(center[0], f"column {index} x")
        y = _finite(center[1], f"column {index} y")
        if not (minimum[0] - margin <= x <= maximum[0] + margin and
                minimum[1] - margin <= y <= maximum[1] + margin):
            raise plan_invalid(f"Column {index} lies outside the scan bounds.")
        width = _finite(raw.get("widthMeters", 0.3), f"column {index} width")
        depth = _finite(raw.get("depthMeters", 0.3), f"column {index} depth")
        height = _finite(raw.get("heightMeters", 2.7), f"column {index} height")
        if not 0.1 <= width <= 2.0 or not 0.1 <= depth <= 2.0:
            raise plan_invalid(f"Column {index} dimensions must be 0.1-2.0 m.")
        if not 0.5 <= height <= 10.0:
            raise plan_invalid(f"Column {index} height must be 0.5-10 m.")
        columns.append(
            {
                "id": str(raw.get("id") or f"C{index}"),
                "levelId": level_id,
                "center": [round(x, 3), round(y, 3)],
                "widthMeters": round(width, 3),
                "depthMeters": round(depth, 3),
                "heightMeters": round(height, 3),
                "source": str(raw.get("source") or "ASSUMED"),
                "verify": bool(raw.get("verify", True)),
            }
        )

    stairs = payload.get("stairs") or []
    if stairs:
        warnings.append("Stairs were present in the AI schedule but are not built yet.")

    units = store_metadata.get("units", {}) or {}
    unit_source = str(units.get("sourceOrigin", "unknown")).lower()
    blocking: list[str] = []
    if unit_source in {"assumed", "unknown"}:
        blocking.append(
            "The scan unit is assumed, not confirmed. Set the source unit and re-import before building."
        )
    if not floors:
        blocking.append("The AI schedule contains no floor slabs.")
    if not walls:
        blocking.append("The AI schedule contains no walls.")
    if len(floors) > max(6, len(levels) * 2):
        blocking.append("The floor/level count is incoherent; review the schedule.")

    measured = [wall["id"] for wall in walls if wall["source"] == "MEASURED"]
    report = {
        "units": "m",
        "sourceUnits": units,
        "datum": str(payload.get("datum") or "scan coordinates unchanged"),
        "axes": str(payload.get("axes") or "scan X/Y/Z"),
        "corrections": {"tilt": "not applied", "yaw": "not applied"},
        "source": source_label,
        "measured": measured,
        "assumed": assumptions,
        "verify": verify,
        "buildable": not blocking,
        "blockingIssues": blocking,
        "capabilities": {
            "levels": bool(levels),
            "floors": bool(floors),
            "walls": bool(walls),
            "openings": bool(openings),
            "doors": any(item["kind"] == "door" for item in openings),
            "windows": any(item["kind"] == "window" for item in openings),
            "ceilings": False,
            "roofs": bool(roofs),
            "columns": bool(columns),
            "stairs": False,
        },
        "verification": {
            "cloudToModelDistance": "not measured in this build",
            "note": "No dimensional accuracy claim is made.",
        },
    }

    return {
        "method": "ai-schedule/1",
        "levels": levels,
        "floors": floors,
        "walls": walls,
        "openings": openings,
        "roofs": roofs,
        "columns": columns,
        "stairs": stairs,
        "warnings": warnings,
        "report": report,
        "schedule": payload,
    }


def _finite(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise plan_invalid(f"{label} must be numeric.") from exc
    if not np.isfinite(number):
        raise plan_invalid(f"{label} must be finite.")
    return number


def _point(
    value: Any,
    label: str,
    minimum: np.ndarray,
    maximum: np.ndarray,
    margin: float,
) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise plan_invalid(f"{label} must be [x, y, z].")
    point = np.asarray([_finite(item, label) for item in value], dtype=np.float64)
    if np.any(point < minimum - margin) or np.any(point > maximum + margin):
        raise plan_invalid(f"{label} lies outside the scan bounds.")
    return [round(float(item), 6) for item in point]


def _confidence(value: Any) -> float:
    if value is None:
        return 0.0
    number = _finite(value, "confidence")
    if not 0.0 <= number <= 1.0:
        raise plan_invalid("Confidence must be between 0 and 1.")
    return round(number, 3)


def _polygon_area(boundary: list[list[float]]) -> float:
    points = np.asarray(boundary, dtype=np.float64)
    if points.shape[0] < 3:
        return 0.0
    x = points[:, 0]
    y = points[:, 1]
    return abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0)
