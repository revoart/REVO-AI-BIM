"""Geometric semantic/instance segmentation baseline.

This phase deliberately does not pretend to run a trained neural network. It
extracts dominant planar instances with RANSAC, classifies them from their
orientation and height, and reports a plane-fit confidence. The method is named
in every result so downstream code cannot mistake it for measured accuracy.

The output is data only. Revit geometry is created in later phases.
"""

from __future__ import annotations

import json
import math
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import open3d as o3d
from scipy.spatial import ConvexHull, QhullError

from .. import __version__
from ..pointcloud import PointCloudStore
from ..pointcloud.preprocess import voxel_downsample
from .errors import AnalysisError, analysis_failed, analysis_not_found

METHOD = "geometric-plane-baseline/1"
METHOD_NOTE = (
    "RANSAC plane extraction with orientation/height classification. Confidence "
    "measures plane fit and sampling quality, not dimensional accuracy."
)
_ANALYSIS_DIR = "analysis"
_RESULT_FILE = "segmentation.json"
_HORIZONTAL_COS = math.cos(math.radians(20.0))
_VERTICAL_COS = math.cos(math.radians(70.0))


def run_segmentation(params) -> dict[str, Any]:
    """Run the baseline segmentation and persist its result beside the store."""

    started = time.perf_counter()
    store = PointCloudStore.open(params.store_path)
    warnings: list[str] = []

    source_points = store.point_count
    if source_points == 0:
        raise analysis_failed("The point cloud store contains no points.")

    sample = store.sample(params.max_points)
    positions = np.asarray(sample["positions"], dtype=np.float64)
    if positions.shape[0] < 3:
        raise analysis_failed(
            "At least three points are required for segmentation.",
            data=f"The store contains {positions.shape[0]} analysable point(s).",
        )

    if sample["count"] > positions.shape[0]:
        warnings.append(
            f"Analysis used {positions.shape[0]:,} of {sample['count']:,} stored points."
        )

    if params.voxel_size_meters > 0:
        before = int(positions.shape[0])
        positions, _, _, _, _ = voxel_downsample(
            positions,
            None,
            None,
            None,
            voxel_size_meters=float(params.voxel_size_meters),
        )
        after = int(positions.shape[0])
        if after < before:
            warnings.append(
                f"Voxel downsampling at {params.voxel_size_meters:g} m reduced "
                f"{before:,} points to {after:,} for analysis."
            )
        if after < 3:
            raise analysis_failed("Too few points remain after voxel downsampling.")

    analyzed_points = int(positions.shape[0])
    z_min = float(positions[:, 2].min())
    z_max = float(positions[:, 2].max())
    z_height = max(z_max - z_min, 1e-9)

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(positions)
    o3d.utility.set_verbosity_level(o3d.utility.VerbosityLevel.Error)
    o3d.utility.random.seed(0)

    remaining = pcd
    elements: list[dict[str, Any]] = []
    kind_counts: dict[str, int] = {}
    min_points = int(params.min_plane_points)

    while len(elements) < int(params.max_planes) and len(remaining.points) >= min_points:
        model, inliers = remaining.segment_plane(
            distance_threshold=float(params.plane_distance_meters),
            ransac_n=3,
            num_iterations=1000,
        )
        if len(inliers) < min_points:
            break

        inlier_points = np.asarray(remaining.points)[inliers]
        element = _build_element(
            model=np.asarray(model, dtype=np.float64).reshape(-1),
            points=inlier_points,
            analyzed_points=analyzed_points,
            z_min=z_min,
            z_max=z_max,
            z_height=z_height,
            min_plane_points=min_points,
            plane_distance=float(params.plane_distance_meters),
            kind_counts=kind_counts,
        )
        if element is not None:
            elements.append(element)

        remaining = remaining.select_by_index(inliers, invert=True)

    if len(elements) >= int(params.max_planes) and len(remaining.points) >= min_points:
        warnings.append(
            f"Stopped after {params.max_planes} planes; {len(remaining.points):,} "
            "point(s) were not segmented."
        )

    assigned_points = int(sum(element["pointCount"] for element in elements))
    coverage = assigned_points / analyzed_points if analyzed_points else 0.0
    if elements and coverage < 0.5:
        warnings.append(
            f"Only {coverage:.0%} of analysed points belong to a detected plane; "
            "clutter, furniture or curved surfaces may be unsegmented."
        )
    if not elements:
        warnings.append("No plane met the minimum point count with the current settings.")

    by_kind = {
        kind: sum(1 for element in elements if element["kind"] == kind)
        for kind in sorted({element["kind"] for element in elements})
    }
    for kind in ("floor", "ceiling", "wall"):
        if elements and by_kind.get(kind, 0) == 0:
            warnings.append(
                f"No {kind} plane was detected. Check the scan coverage and plane settings."
            )

    mean_confidence = (
        float(np.mean([element["confidence"] for element in elements]))
        if elements
        else 0.0
    )
    summary = {
        "sourcePoints": source_points,
        "analyzedPoints": analyzed_points,
        "segments": len(elements),
        "byKind": by_kind,
        "meanConfidence": round(mean_confidence, 3),
        "highConfidenceSegments": sum(
            1
            for element in elements
            if element["confidence"] >= params.confidence_threshold
        ),
        "assignedPoints": assigned_points,
        "coverage": round(coverage, 3),
    }

    result_path = _result_path(store.path)
    result = {
        "scanId": store.metadata.get("scanId", store.path.name),
        "storePath": str(store.path),
        "method": METHOD,
        "methodNote": METHOD_NOTE,
        "parameters": {
            "voxelSizeMeters": float(params.voxel_size_meters),
            "maxPoints": int(params.max_points),
            "planeDistanceMeters": float(params.plane_distance_meters),
            "minPlanePoints": min_points,
            "maxPlanes": int(params.max_planes),
            "confidenceThreshold": float(params.confidence_threshold),
        },
        "summary": summary,
        "elements": elements,
        "warnings": warnings,
        "resultPath": str(result_path),
        "createdAt": _utc_now(),
        "engineVersion": __version__,
        "elapsedMs": round((time.perf_counter() - started) * 1000.0, 3),
    }

    _write_result(store.path, result)
    return result


def load_segmentation(store_path: str) -> dict[str, Any]:
    """Read a previously written segmentation result."""

    store = PointCloudStore.open(store_path)
    path = _result_path(store.path)
    if not path.is_file():
        raise analysis_not_found(str(store.path))

    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError) as exc:
        raise analysis_not_found(str(store.path)) from exc


def _build_element(
    *,
    model: np.ndarray,
    points: np.ndarray,
    analyzed_points: int,
    z_min: float,
    z_max: float,
    z_height: float,
    min_plane_points: int,
    plane_distance: float,
    kind_counts: dict[str, int],
) -> dict[str, Any] | None:
    if points.shape[0] < 3:
        return None

    normal = model[:3].astype(np.float64)
    normal_norm = float(np.linalg.norm(normal))
    if not math.isfinite(normal_norm) or normal_norm < 1e-12:
        return None
    normal /= normal_norm

    centroid = points.mean(axis=0)
    offset = -float(np.dot(normal, centroid))
    residual = np.abs(points @ normal + offset)
    fit_error = float(np.sqrt(np.mean(residual * residual)))

    centered = points - centroid
    covariance = centered.T @ centered / points.shape[0]
    eigenvalues = np.linalg.eigvalsh(covariance)
    eigenvalue_sum = float(eigenvalues.sum())
    planarity = (
        float(1.0 - eigenvalues[0] / eigenvalue_sum)
        if eigenvalue_sum > 1e-18
        else 0.0
    )
    planarity = _clamp(planarity)

    area = _plane_area(centered)
    density = points.shape[0] / max(area, 1e-6)
    inlier_ratio = points.shape[0] / max(analyzed_points, 1)
    coverage = _clamp(points.shape[0] / max(min_plane_points, analyzed_points * 0.005))
    density_score = _clamp(density / 100.0)
    size_score = _clamp(math.sqrt(max(area, 0.0)) / 0.5)
    fit_score = _clamp(1.0 - fit_error / max(plane_distance * 2.0, 1e-6))

    kind = _classify(normal, centroid[2], z_min, z_max, z_height)
    kind_counts[kind] = kind_counts.get(kind, 0) + 1

    confidence = _clamp(
        0.35 * planarity
        + 0.20 * coverage
        + 0.20 * density_score
        + 0.10 * size_score
        + 0.15 * fit_score
    )

    return {
        "id": f"{kind}-{kind_counts[kind]}",
        "kind": kind,
        "pointCount": int(points.shape[0]),
        "confidence": round(confidence, 3),
        "areaM2": round(area, 3),
        "centroid": _floats(centroid),
        "bounds": {
            "min": _floats(points.min(axis=0)),
            "max": _floats(points.max(axis=0)),
        },
        "plane": {
            "normal": _floats(normal),
            "offset": round(offset, 6),
        },
        "signals": {
            "planarity": round(planarity, 3),
            "densityPerSquareMeter": round(density, 3),
            "coverage": round(coverage, 3),
            "size": round(size_score, 3),
            "fitErrorMeters": round(fit_error, 6),
            "inlierRatio": round(inlier_ratio, 3),
        },
    }


def _classify(
    normal: np.ndarray,
    centroid_z: float,
    z_min: float,
    z_max: float,
    z_height: float,
) -> str:
    vertical_component = abs(float(normal[2]))
    if vertical_component >= _HORIZONTAL_COS:
        if centroid_z <= z_min + z_height * 0.30:
            return "floor"
        if centroid_z >= z_max - z_height * 0.30:
            return "ceiling"
        return "horizontal"
    if vertical_component <= _VERTICAL_COS:
        return "wall"
    return "sloped"


def _plane_area(centered: np.ndarray) -> float:
    if centered.shape[0] < 3:
        return 0.0

    try:
        _, _, vh = np.linalg.svd(centered, full_matrices=False)
        projected = centered @ vh[:2].T
        return float(ConvexHull(projected).volume)
    except (QhullError, ValueError):
        extents = centered.max(axis=0) - centered.min(axis=0)
        return float(extents[0] * extents[1])


def _result_path(store_path: Path) -> Path:
    return store_path / _ANALYSIS_DIR / _RESULT_FILE


def _write_result(store_path: Path, result: dict[str, Any]) -> None:
    directory = store_path / _ANALYSIS_DIR
    path = _result_path(store_path)
    temp = directory / f".{_RESULT_FILE}.tmp-{uuid.uuid4().hex}"

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
        raise analysis_failed(
            f"Could not write the segmentation result for '{store_path}'.",
            data=str(exc),
        ) from exc


def _floats(values: np.ndarray) -> list[float]:
    return [round(float(value), 6) for value in np.asarray(values).tolist()]


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
