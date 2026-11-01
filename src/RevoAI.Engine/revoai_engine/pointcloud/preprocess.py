"""Deterministic point cloud preprocessing.

Preprocessing is optional and explicit. It never recentres the cloud: the voxel
grid is anchored at the cloud's own minimum so the output remains in the same
coordinate frame as the source scan.
"""

from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from .errors import processing_failed


def remove_statistical_outliers(
    positions: np.ndarray,
    colors: np.ndarray | None,
    intensity: np.ndarray | None,
    classification: np.ndarray | None,
    *,
    neighbors: int,
    std_ratio: float,
) -> tuple[
    np.ndarray,
    np.ndarray | None,
    np.ndarray | None,
    np.ndarray | None,
    dict,
]:
    count = int(positions.shape[0])
    if count <= neighbors:
        return positions, colors, intensity, classification, {
            "applied": False,
            "reason": "Not enough points for the requested neighbour count.",
            "neighbors": neighbors,
            "stdRatio": std_ratio,
            "removed": 0,
            "remaining": count,
        }

    tree = cKDTree(positions)
    distances, _ = tree.query(positions, k=neighbors + 1, workers=-1)
    mean_distances = distances[:, 1:].mean(axis=1)
    global_mean = float(mean_distances.mean())
    global_std = float(mean_distances.std())
    threshold = global_mean + std_ratio * global_std
    keep = mean_distances <= threshold

    if not keep.any():
        raise processing_failed(
            "Statistical outlier removal would remove every point.",
            data=f"Threshold {threshold:.6g} m; mean {global_mean:.6g} m.",
        )

    removed = int((~keep).sum())
    report = {
        "applied": True,
        "neighbors": neighbors,
        "stdRatio": std_ratio,
        "meanDistanceMeters": global_mean,
        "stdDistanceMeters": global_std,
        "thresholdMeters": threshold,
        "removed": removed,
        "remaining": int(keep.sum()),
    }

    return (
        positions[keep],
        colors[keep] if colors is not None else None,
        intensity[keep] if intensity is not None else None,
        classification[keep] if classification is not None else None,
        report,
    )


def voxel_downsample(
    positions: np.ndarray,
    colors: np.ndarray | None,
    intensity: np.ndarray | None,
    classification: np.ndarray | None,
    *,
    voxel_size_meters: float,
) -> tuple[
    np.ndarray,
    np.ndarray | None,
    np.ndarray | None,
    np.ndarray | None,
    dict,
]:
    if voxel_size_meters <= 0:
        raise processing_failed("Voxel size must be greater than zero.")

    count = int(positions.shape[0])
    origin = positions.min(axis=0)
    keys = np.floor((positions - origin) / voxel_size_meters).astype(np.int64)
    unique_keys, inverse, counts = np.unique(
        keys, axis=0, return_inverse=True, return_counts=True
    )
    unique_count = int(unique_keys.shape[0])

    if unique_count == count:
        return positions, colors, intensity, classification, {
            "applied": True,
            "voxelSizeMeters": voxel_size_meters,
            "before": count,
            "after": count,
            "removed": 0,
        }

    sums = np.zeros((unique_count, 3), dtype=np.float64)
    np.add.at(sums, inverse, positions)
    downsampled = sums / counts[:, None]

    down_colors = None
    if colors is not None:
        color_sums = np.zeros((unique_count, 3), dtype=np.float64)
        np.add.at(color_sums, inverse, colors.astype(np.float64))
        down_colors = np.clip(
            np.rint(color_sums / counts[:, None]), 0, 255
        ).astype(np.uint8)

    down_intensity = None
    if intensity is not None:
        intensity_sums = np.zeros(unique_count, dtype=np.float64)
        np.add.at(intensity_sums, inverse, intensity.astype(np.float64))
        down_intensity = (intensity_sums / counts).astype(np.float32)

    down_classification = None
    if classification is not None:
        # Keep the first classification in each voxel; it is a discrete label,
        # so averaging it would invent a class that was never observed.
        first_indices = np.zeros(unique_count, dtype=np.int64)
        first_indices[inverse[::-1]] = np.arange(count - 1, -1, -1)
        down_classification = classification[first_indices]

    return downsampled, down_colors, down_intensity, down_classification, {
        "applied": True,
        "voxelSizeMeters": voxel_size_meters,
        "before": count,
        "after": unique_count,
        "removed": count - unique_count,
    }
