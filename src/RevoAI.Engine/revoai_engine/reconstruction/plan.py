"""Convert segmentation instances into a native Revit reconstruction plan.

The plan is deliberately simple and auditable: floors become closed boundary
polygons on a level, walls become line segments with a base level and height.
It creates no Revit objects; the C# side owns the transaction.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .. import __version__
from ..analysis import load_segmentation
from ..pointcloud import PointCloudStore
from .errors import plan_failed, plan_invalid

LOG = logging.getLogger("revoai.reconstruction")

METHOD = "geometric-floor-wall-plan/1"
EXTERNAL_METHOD = "external-bim-plan/1"
_ANALYSIS_DIR = "analysis"
_PLAN_FILE = "reconstruction-plan.json"


def create_plan(params) -> dict[str, Any]:
    started = time.perf_counter()
    if params.provider == "astra":
        return _create_astra_plan(params, started)
    if params.provider == "astra_subscription":
        return _create_astra_subscription_plan(params, started)
    if params.external_plan_path:
        return _create_external_plan(params, started)

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


def _create_external_plan(params, started: float) -> dict[str, Any]:
    """Validate a plan produced by an external AI tool and normalize it.

    The external tool is responsible for architectural reasoning. This function
    only enforces the contract and coordinate bounds; it does not invent floors
    or walls that the external plan did not provide.
    """

    store = PointCloudStore.open(params.store_path)
    source = Path(params.external_plan_path).expanduser()
    if not source.is_absolute():
        source = source.resolve()
    if not source.is_file():
        raise plan_invalid(f"External plan file does not exist: '{source}'.")

    try:
        with source.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
    except (OSError, ValueError) as exc:
        raise plan_invalid(
            f"Could not read external plan '{source}'.",
            data=str(exc),
        ) from exc

    if not isinstance(payload, dict):
        raise plan_invalid("External plan must be a JSON object.")

    return _normalize_external_plan(
        payload,
        store,
        params,
        started,
        source_label=str(source),
        source_parameters={"externalPlanPath": str(source)},
    )


def _create_astra_plan(params, started: float) -> dict[str, Any]:
    """Ask GPT-6 Astra for a plan, then run it through the same validator."""

    from .astra import request_astra_plan

    store, segmentation, context, element_count = _build_astra_context(
        params.store_path
    )
    knowledge = _build_knowledge_context(segmentation)
    if knowledge is not None:
        context["approvedKnowledge"] = {
            "text": knowledge["text"],
            "citations": knowledge["citations"],
        }
    payload = request_astra_plan(context, model=params.astra_model)
    result = _normalize_external_plan(
        payload,
        store,
        params,
        started,
        source_label=f"openai:{params.astra_model}",
        source_parameters={
            "astraModel": params.astra_model,
            "astraElementCount": element_count,
        },
    )
    return _attach_knowledge(
        result,
        knowledge,
        model=params.astra_model,
        provider="openai",
    )


def _create_astra_subscription_plan(params, started: float) -> dict[str, Any]:
    """Use the Revo-managed Astra gateway; no OpenAI key reaches the add-in."""

    from .astra_subscription import request_subscription_plan

    store, segmentation, context, element_count = _build_astra_context(
        params.store_path
    )
    knowledge = _build_knowledge_context(segmentation)
    if knowledge is not None:
        context["approvedKnowledge"] = {
            "text": knowledge["text"],
            "citations": knowledge["citations"],
        }
    payload = request_subscription_plan(context)
    result = _normalize_external_plan(
        payload,
        store,
        params,
        started,
        source_label="revo-subscription:gpt-6-astra",
        source_parameters={
            "astraModel": params.astra_model,
            "astraElementCount": element_count,
            "billing": "revo-subscription",
        },
    )
    return _attach_knowledge(
        result,
        knowledge,
        model=params.astra_model,
        provider="revo-subscription",
    )


def _build_knowledge_context(segmentation: dict[str, Any]) -> dict[str, Any] | None:
    """Retrieve approved local knowledge, but never block plan generation."""
    try:
        from ..knowledge import KnowledgeStore

        kinds = sorted(
            {
                str(element.get("kind"))
                for element in segmentation.get("elements", [])
                if element.get("kind")
            }
        )
        store = KnowledgeStore()
        context = store.context(element_kinds=kinds, limit=6)
        if not context.get("records"):
            return None
        context["store"] = store
        return context
    except Exception as exc:  # pragma: no cover - defensive local storage path
        LOG.warning("Approved knowledge could not be retrieved: %s", exc)
        return None


def _attach_knowledge(
    result: dict[str, Any],
    knowledge: dict[str, Any] | None,
    *,
    model: str,
    provider: str,
) -> dict[str, Any]:
    if knowledge is None:
        return result

    citations = knowledge.get("citations", [])
    result.setdefault("parameters", {})["knowledgeCitations"] = citations
    result["parameters"]["knowledgeRecordCount"] = len(knowledge.get("records", []))

    try:
        store = knowledge["store"]
        store.add_decision(
            task="reconstruction.plan",
            model=model,
            retrieved_ids=[item["recordId"] for item in citations],
            plan={
                "levels": len(result.get("levels", [])),
                "floors": len(result.get("floors", [])),
                "walls": len(result.get("walls", [])),
                "provider": provider,
            },
            outcome="generated",
        )
    except Exception as exc:  # pragma: no cover - decision logging is best effort
        LOG.warning("Could not record the knowledge retrieval decision: %s", exc)

    return result


def _build_astra_context(
    store_path: str,
) -> tuple[PointCloudStore, dict[str, Any], dict[str, Any], int]:
    store = PointCloudStore.open(store_path)
    segmentation = load_segmentation(store_path)
    elements = []
    for element in segmentation.get("elements", []):
        if float(element.get("confidence", 0.0)) < 0.3:
            continue
        elements.append(
            {
                "id": element.get("id"),
                "kind": element.get("kind"),
                "centroid": element.get("centroid"),
                "bounds": element.get("bounds"),
                "areaM2": element.get("areaM2"),
                "confidence": element.get("confidence"),
                "boundary": element.get("boundary"),
            }
        )
        if len(elements) >= 80:
            break

    context = {
        "scanId": store.metadata.get("scanId", store.path.name),
        "units": store.metadata.get("units", {}),
        "bounds": store.metadata.get("bounds", {}),
        "sourceBounds": store.metadata.get("sourceBounds", {}),
        "pointCount": store.metadata.get("pointCount", {}),
        "segmentation": {
            "method": segmentation.get("method"),
            "summary": segmentation.get("summary"),
            "elements": elements,
        },
    }
    return store, segmentation, context, len(elements)


def _normalize_external_plan(
    payload: dict[str, Any],
    store: PointCloudStore,
    params,
    started: float,
    *,
    source_label: str,
    source_parameters: dict[str, Any],
) -> dict[str, Any]:
    warnings: list[str] = []
    for unsupported in ("rooms", "openings", "ceilings"):
        if payload.get(unsupported):
            warnings.append(
                f"Ignored external '{unsupported}'; this phase creates floors and walls only."
            )

    levels_raw = payload.get("levels")
    floors_raw = payload.get("floors")
    walls_raw = payload.get("walls")
    if not isinstance(levels_raw, list) or not levels_raw:
        raise plan_invalid("External plan must contain a non-empty 'levels' array.")
    if not isinstance(floors_raw, list):
        raise plan_invalid("External plan 'floors' must be an array.")
    if not isinstance(walls_raw, list):
        raise plan_invalid("External plan 'walls' must be an array.")

    bounds = store.metadata.get("bounds", {})
    minimum = np.asarray(bounds.get("min", [0.0, 0.0, 0.0]), dtype=np.float64)
    maximum = np.asarray(bounds.get("max", [0.0, 0.0, 0.0]), dtype=np.float64)
    extent = np.maximum(maximum - minimum, 0.0)
    margin = max(5.0, float(np.max(extent)) * 0.05)

    levels: list[dict[str, Any]] = []
    level_ids: set[str] = set()
    used_names: set[str] = set()
    for index, raw in enumerate(levels_raw, start=1):
        if not isinstance(raw, dict):
            raise plan_invalid(f"Level {index} must be a JSON object.")
        level_id = str(raw.get("id") or f"level-{index}")
        if level_id in level_ids:
            raise plan_invalid(f"Duplicate level id '{level_id}'.")
        level_ids.add(level_id)
        elevation = _finite_float(raw.get("elevationMeters"), f"level {level_id} elevation")
        if not minimum[2] - margin <= elevation <= maximum[2] + margin:
            raise plan_invalid(
                f"Level {level_id} elevation {elevation:g} m is outside the scan z range."
            )
        name = str(raw.get("name") or f"Revo Level {index}")
        base_name = name
        suffix = 2
        while name in used_names:
            name = f"{base_name} ({suffix})"
            suffix += 1
        used_names.add(name)
        levels.append(
            {
                "id": level_id,
                "name": name,
                "elevationMeters": round(elevation, 6),
            }
        )

    floors: list[dict[str, Any]] = []
    for index, raw in enumerate(floors_raw, start=1):
        if not isinstance(raw, dict):
            raise plan_invalid(f"Floor {index} must be a JSON object.")
        level_id = str(raw.get("levelId") or "")
        if level_id not in level_ids:
            raise plan_invalid(f"Floor {index} references unknown level '{level_id}'.")
        boundary_raw = raw.get("boundary")
        if not isinstance(boundary_raw, list) or len(boundary_raw) < 3:
            raise plan_invalid(f"Floor {index} boundary must contain at least three points.")
        boundary = [
            _validate_point(point, f"floor {index} boundary", minimum, maximum, margin)
            for point in boundary_raw
        ]
        confidence, supplied = _confidence(raw.get("confidence"), warnings, f"floor {index}")
        if not supplied:
            warnings.append(f"Floor {index} has no confidence; 0 was recorded.")
        area = float(raw.get("areaM2") or _polygon_area(boundary))
        floors.append(
            {
                "id": str(raw.get("id") or f"floor-plan-{index}"),
                "sourceSegmentId": str(raw.get("sourceSegmentId") or f"external-floor-{index}"),
                "levelId": level_id,
                "boundary": boundary,
                "areaM2": round(area, 3),
                "confidence": confidence,
            }
        )

    walls: list[dict[str, Any]] = []
    fallback_height = float(params.fallback_wall_height_meters)
    for index, raw in enumerate(walls_raw, start=1):
        if not isinstance(raw, dict):
            raise plan_invalid(f"Wall {index} must be a JSON object.")
        level_id = str(raw.get("levelId") or "")
        if level_id not in level_ids:
            raise plan_invalid(f"Wall {index} references unknown level '{level_id}'.")
        start = _validate_point(raw.get("start"), f"wall {index} start", minimum, maximum, margin)
        end = _validate_point(raw.get("end"), f"wall {index} end", minimum, maximum, margin)
        length = float(np.linalg.norm(np.asarray(end[:2]) - np.asarray(start[:2])))
        if length < 0.3:
            raise plan_invalid(f"Wall {index} is shorter than 0.3 m.")
        height_raw = raw.get("heightMeters")
        if height_raw is None:
            height = fallback_height
            height_source = "fallback"
            warnings.append(f"Wall {index} has no height; fallback height was used.")
        else:
            height = _finite_float(height_raw, f"wall {index} height")
            height_source = str(raw.get("heightSource") or "external")
        if not 0.5 <= height <= 10.0:
            raise plan_invalid(f"Wall {index} height must be between 0.5 and 10 m.")
        confidence, supplied = _confidence(raw.get("confidence"), warnings, f"wall {index}")
        if not supplied:
            warnings.append(f"Wall {index} has no confidence; 0 was recorded.")
        walls.append(
            {
                "id": str(raw.get("id") or f"wall-plan-{index}"),
                "sourceSegmentId": str(raw.get("sourceSegmentId") or f"external-wall-{index}"),
                "levelId": level_id,
                "start": start,
                "end": end,
                "heightMeters": round(height, 3),
                "heightSource": height_source,
                "confidence": confidence,
            }
        )

    max_elements = int(params.max_elements)
    total = len(floors) + len(walls)
    if total > max_elements:
        warnings.append(
            f"Plan was limited to {max_elements} elements; {total - max_elements} were omitted."
        )
        floors = floors[:max_elements]
        walls = walls[: max(0, max_elements - len(floors))]

    result_path = store.path / _ANALYSIS_DIR / _PLAN_FILE
    parameters = {
        **source_parameters,
        "sourceLabel": source_label,
        "externalMethod": payload.get("method"),
        "fallbackWallHeightMeters": fallback_height,
        "maxElements": max_elements,
    }
    result = {
        "scanId": store.metadata.get("scanId", store.path.name),
        "storePath": str(store.path),
        "method": EXTERNAL_METHOD,
        "parameters": parameters,
        "levels": levels,
        "floors": floors,
        "walls": walls,
        "warnings": warnings,
        "resultPath": str(result_path),
        "createdAt": _utc_now(),
        "engineVersion": __version__,
        "elapsedMs": round((time.perf_counter() - started) * 1000.0, 3),
    }
    _write_result(store.path, result)
    return result


def _validate_point(
    value: Any,
    label: str,
    minimum: np.ndarray,
    maximum: np.ndarray,
    margin: float,
) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise plan_invalid(f"{label} must be an [x, y, z] array.")
    point = np.asarray([_finite_float(component, label) for component in value], dtype=np.float64)
    if np.any(point < minimum - margin) or np.any(point > maximum + margin):
        raise plan_invalid(f"{label} lies outside the scan bounds.")
    return [round(float(component), 6) for component in point]


def _finite_float(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise plan_invalid(f"{label} must be numeric.") from exc
    if not np.isfinite(number):
        raise plan_invalid(f"{label} must be finite.")
    return number


def _confidence(
    value: Any,
    warnings: list[str],
    label: str,
) -> tuple[float, bool]:
    if value is None:
        return 0.0, False
    confidence = _finite_float(value, f"{label} confidence")
    if not 0.0 <= confidence <= 1.0:
        raise plan_invalid(f"{label} confidence must be between 0 and 1.")
    return round(confidence, 3), True


def _polygon_area(boundary: list[list[float]]) -> float:
    points = np.asarray(boundary, dtype=np.float64)
    if points.shape[0] < 3:
        return 0.0
    x = points[:, 0]
    y = points[:, 1]
    return abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0)


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
