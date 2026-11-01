"""Chunked point cloud storage and spatial queries.

Points are stored in chunks addressed by a regular 3D grid. Each chunk keeps a
float64 origin plus float32 offsets, which preserves the scan coordinate frame
while keeping the on-disk size close to 12 bytes per point. The grid index is
written into ``metadata.json`` so a query only opens chunks that can contain a
result.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from .errors import invalid_cloud, processing_failed, store_not_found

SCHEMA_VERSION = 1
_SCAN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


@dataclass(frozen=True)
class ChunkRef:
    index: int
    cell: tuple[int, int, int]
    origin: np.ndarray
    count: int
    file: str
    bounds_min: np.ndarray
    bounds_max: np.ndarray


def write_store(
    output_directory: Path,
    scan_id: str,
    positions: np.ndarray,
    colors: np.ndarray | None,
    intensity: np.ndarray | None,
    classification: np.ndarray | None,
    *,
    chunk_size_meters: float,
    metadata: dict,
    overwrite: bool,
) -> tuple[Path, dict]:
    if not _SCAN_ID_PATTERN.fullmatch(scan_id):
        raise processing_failed(
            "The scan id is not a safe folder name.",
            data="Use 1-64 letters, digits, '.', '_' or '-'.",
        )
    if chunk_size_meters <= 0:
        raise processing_failed("Chunk size must be greater than zero.")
    if positions.shape[0] == 0:
        raise invalid_cloud("Cannot store an empty point cloud.")

    try:
        output_directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise processing_failed(
            f"Could not create the point cloud output directory '{output_directory}'.",
            data=str(exc),
        ) from exc

    final_path = output_directory / scan_id

    if final_path.exists():
        if not overwrite:
            raise processing_failed(
                f"A scan store already exists at '{final_path}'.",
                data="Choose another scan id or enable overwrite.",
            )
        try:
            shutil.rmtree(final_path)
        except OSError as exc:
            raise processing_failed(
                f"Could not replace the existing scan store '{final_path}'.",
                data=str(exc),
            ) from exc

    temp_path = output_directory / f".{scan_id}.tmp-{uuid.uuid4().hex}"
    try:
        temp_path.mkdir(parents=True, exist_ok=False)
        chunks_path = temp_path / "chunks"
        chunks_path.mkdir()
    except OSError as exc:
        shutil.rmtree(temp_path, ignore_errors=True)
        raise processing_failed(
            f"Could not create a temporary scan store in '{output_directory}'.",
            data=str(exc),
        ) from exc

    try:
        minimum = positions.min(axis=0)
        maximum = positions.max(axis=0)
        cells = np.floor((positions - minimum) / chunk_size_meters).astype(np.int64)
        order = np.lexsort((cells[:, 2], cells[:, 1], cells[:, 0]))

        sorted_positions = positions[order]
        sorted_cells = cells[order]
        sorted_colors = colors[order] if colors is not None else None
        sorted_intensity = intensity[order] if intensity is not None else None
        sorted_classification = classification[order] if classification is not None else None

        unique_cells, first_indices = np.unique(
            sorted_cells, axis=0, return_index=True
        )
        starts = [int(value) for value in first_indices]
        starts.append(int(sorted_positions.shape[0]))

        chunk_records: list[dict] = []
        grid: dict[str, int] = {}

        for index, cell in enumerate(unique_cells):
            start = starts[index]
            end = starts[index + 1]
            chunk_positions = sorted_positions[start:end]
            origin = minimum + cell.astype(np.float64) * chunk_size_meters
            offsets = (chunk_positions - origin).astype(np.float32)

            arrays: dict[str, np.ndarray] = {
                "origin": origin.astype(np.float64),
                "positions": offsets,
            }
            if sorted_colors is not None:
                arrays["colors"] = sorted_colors[start:end]
            if sorted_intensity is not None:
                arrays["intensity"] = sorted_intensity[start:end]
            if sorted_classification is not None:
                arrays["classification"] = sorted_classification[start:end]

            relative_file = f"chunks/chunk_{index:05d}.npz"
            chunk_file = temp_path / relative_file
            with chunk_file.open("wb") as stream:
                np.savez(stream, **arrays)

            cell_tuple = (int(cell[0]), int(cell[1]), int(cell[2]))
            grid[f"{cell_tuple[0]},{cell_tuple[1]},{cell_tuple[2]}"] = index
            chunk_records.append(
                {
                    "index": index,
                    "cell": list(cell_tuple),
                    "origin": _floats(origin),
                    "count": int(chunk_positions.shape[0]),
                    "file": relative_file,
                    "bounds": {
                        "min": _floats(chunk_positions.min(axis=0)),
                        "max": _floats(chunk_positions.max(axis=0)),
                    },
                }
            )

        metadata = dict(metadata)
        metadata["schemaVersion"] = SCHEMA_VERSION
        metadata["bounds"] = {"min": _floats(minimum), "max": _floats(maximum)}
        point_count = dict(metadata.get("pointCount", {}))
        point_count["stored"] = int(positions.shape[0])
        metadata["pointCount"] = point_count
        metadata["storage"] = {
            "chunkSizeMeters": float(chunk_size_meters),
            "chunkCount": len(chunk_records),
            "chunks": chunk_records,
            "grid": grid,
        }

        with (temp_path / "metadata.json").open("w", encoding="utf-8") as stream:
            json.dump(metadata, stream, indent=2, allow_nan=False)

        os.replace(temp_path, final_path)
        return final_path, metadata
    except OSError as exc:
        shutil.rmtree(temp_path, ignore_errors=True)
        raise processing_failed(
            f"Could not write the point cloud store '{final_path}'.",
            data=str(exc),
        ) from exc
    except Exception:
        shutil.rmtree(temp_path, ignore_errors=True)
        raise


class PointCloudStore:
    """Read-only access to a store produced by :func:`write_store`."""

    def __init__(self, path: Path, metadata: dict, chunks: list[ChunkRef]) -> None:
        self.path = path
        self.metadata = metadata
        self.chunks = chunks
        self.chunk_size_meters = float(metadata["storage"]["chunkSizeMeters"])
        self._grid: dict[str, int] = dict(metadata["storage"]["grid"])
        self._cache: OrderedDict[int, dict] = OrderedDict()
        self._cache_limit = 8

        bounds = metadata["bounds"]
        self.minimum = np.asarray(bounds["min"], dtype=np.float64)
        self.maximum = np.asarray(bounds["max"], dtype=np.float64)

    @classmethod
    def open(cls, path: str | Path) -> "PointCloudStore":
        store_path = Path(path).expanduser().resolve()
        metadata_path = store_path / "metadata.json"
        if not metadata_path.is_file():
            raise store_not_found(str(store_path))

        try:
            with metadata_path.open("r", encoding="utf-8") as stream:
                metadata = json.load(stream)
        except (OSError, ValueError) as exc:
            raise store_not_found(str(store_path)) from exc

        if metadata.get("schemaVersion") != SCHEMA_VERSION:
            raise processing_failed(
                "The point cloud store uses an unsupported schema version.",
                data=f"Found {metadata.get('schemaVersion')!r}, expected {SCHEMA_VERSION}.",
            )

        storage = metadata.get("storage")
        if not isinstance(storage, dict) or "chunkSizeMeters" not in storage:
            raise store_not_found(str(store_path))

        chunk_records = storage.get("chunks")
        if not isinstance(chunk_records, list):
            raise store_not_found(str(store_path))

        chunks: list[ChunkRef] = []
        try:
            for record in chunk_records:
                cell = tuple(int(value) for value in record["cell"])
                if len(cell) != 3:
                    raise ValueError("Chunk cell must have three components.")
                chunks.append(
                    ChunkRef(
                        index=int(record["index"]),
                        cell=cell,
                        origin=np.asarray(record["origin"], dtype=np.float64),
                        count=int(record["count"]),
                        file=str(record["file"]),
                        bounds_min=np.asarray(record["bounds"]["min"], dtype=np.float64),
                        bounds_max=np.asarray(record["bounds"]["max"], dtype=np.float64),
                    )
                )

            bounds = metadata["bounds"]
            if (
                np.asarray(bounds["min"], dtype=np.float64).shape != (3,)
                or np.asarray(bounds["max"], dtype=np.float64).shape != (3,)
            ):
                raise ValueError("Store bounds must have three components.")
        except (KeyError, TypeError, ValueError) as exc:
            raise store_not_found(str(store_path)) from exc

        return cls(store_path, metadata, chunks)

    @property
    def point_count(self) -> int:
        return int(self.metadata.get("pointCount", {}).get("stored", 0))

    def info(self) -> dict:
        return self.metadata

    def _load_chunk(self, index: int) -> dict:
        cached = self._cache.get(index)
        if cached is not None:
            self._cache.move_to_end(index)
            return cached

        ref = self.chunks[index]
        chunk_path = (self.path / ref.file).resolve()
        if self.path not in chunk_path.parents:
            raise store_not_found(str(chunk_path))

        try:
            with np.load(chunk_path, allow_pickle=False) as data:
                origin = np.asarray(data["origin"], dtype=np.float64)
                positions = origin + np.asarray(data["positions"], dtype=np.float64)
                chunk = {
                    "positions": positions,
                    "colors": np.asarray(data["colors"]) if "colors" in data else None,
                    "intensity": (
                        np.asarray(data["intensity"]) if "intensity" in data else None
                    ),
                    "classification": (
                        np.asarray(data["classification"])
                        if "classification" in data
                        else None
                    ),
                }
        except (OSError, ValueError) as exc:
            raise store_not_found(str(chunk_path)) from exc

        self._cache[index] = chunk
        if len(self._cache) > self._cache_limit:
            self._cache.popitem(last=False)
        return chunk

    def query_bounds(
        self,
        minimum: Iterable[float],
        maximum: Iterable[float],
        *,
        max_points: int,
        include_colors: bool = False,
        include_intensity: bool = False,
    ) -> dict:
        min_array = np.asarray(list(minimum), dtype=np.float64)
        max_array = np.asarray(list(maximum), dtype=np.float64)
        if min_array.shape != (3,) or max_array.shape != (3,):
            raise invalid_cloud("Bounds must contain three minimum and three maximum values.")
        if not np.isfinite(min_array).all() or not np.isfinite(max_array).all():
            raise invalid_cloud("Bounds must contain finite values.")
        if np.any(min_array > max_array):
            raise invalid_cloud("Bounds minimum must not exceed bounds maximum.")

        indices = self._indices_for_cells(
            self._cell_range(min_array, max_array)
        )

        def predicate(points: np.ndarray) -> np.ndarray:
            return (
                (points[:, 0] >= min_array[0])
                & (points[:, 0] <= max_array[0])
                & (points[:, 1] >= min_array[1])
                & (points[:, 1] <= max_array[1])
                & (points[:, 2] >= min_array[2])
                & (points[:, 2] <= max_array[2])
            )

        return self._collect(
            indices,
            predicate,
            max_points=max_points,
            include_colors=include_colors,
            include_intensity=include_intensity,
        )

    def query_radius(
        self,
        center: Iterable[float],
        radius: float,
        *,
        max_points: int,
        include_colors: bool = False,
        include_intensity: bool = False,
    ) -> dict:
        center_array = np.asarray(list(center), dtype=np.float64)
        if center_array.shape != (3,):
            raise invalid_cloud("Query center must contain three values.")
        if not np.isfinite(center_array).all():
            raise invalid_cloud("Query center must contain finite values.")
        if not math.isfinite(radius) or radius <= 0:
            raise invalid_cloud("Query radius must be a finite value greater than zero.")

        indices = self._indices_for_cells(
            self._cell_range(center_array - radius, center_array + radius)
        )
        radius_squared = radius * radius

        def predicate(points: np.ndarray) -> np.ndarray:
            delta = points - center_array
            return np.einsum("ij,ij->i", delta, delta) <= radius_squared

        return self._collect(
            indices,
            predicate,
            max_points=max_points,
            include_colors=include_colors,
            include_intensity=include_intensity,
        )

    def sample(
        self,
        max_points: int,
        *,
        include_colors: bool = False,
        include_intensity: bool = False,
    ) -> dict:
        if max_points <= 0:
            raise invalid_cloud("maxPoints must be greater than zero.")

        total = self.point_count
        if total == 0:
            return _empty_result()

        step = max(1, math.ceil(total / max_points))
        position_parts: list[np.ndarray] = []
        color_parts: list[np.ndarray] = []
        intensity_parts: list[np.ndarray] = []
        offset = 0
        returned = 0

        for index in range(len(self.chunks)):
            chunk = self._load_chunk(index)
            points = chunk["positions"]
            local_start = (-offset) % step
            remaining = max_points - returned
            selected = points[local_start::step][:remaining]
            if selected.shape[0]:
                position_parts.append(selected)
                returned += int(selected.shape[0])
                if include_colors and chunk["colors"] is not None:
                    color_parts.append(chunk["colors"][local_start::step][:remaining])
                if include_intensity and chunk["intensity"] is not None:
                    intensity_parts.append(
                        chunk["intensity"][local_start::step][:remaining]
                    )
            offset += int(points.shape[0])
            if returned >= max_points:
                break

        result = {
            "positions": np.concatenate(position_parts, axis=0) if position_parts else np.empty((0, 3)),
            "count": total,
            "returned": returned,
            "truncated": False,
            "colors": np.concatenate(color_parts, axis=0) if color_parts else None,
            "intensity": (
                np.concatenate(intensity_parts, axis=0) if intensity_parts else None
            ),
        }
        return result

    def nearest(self, center: Iterable[float], k: int) -> dict:
        center_array = np.asarray(list(center), dtype=np.float64)
        if center_array.shape != (3,):
            raise invalid_cloud("Query center must contain three values.")
        if not np.isfinite(center_array).all():
            raise invalid_cloud("Query center must contain finite values.")
        if k <= 0:
            raise invalid_cloud("k must be greater than zero.")
        if not self.chunks:
            return _empty_result()

        ordered = sorted(
            (
                (_aabb_distance(center_array, ref.bounds_min, ref.bounds_max), ref.index)
                for ref in self.chunks
            ),
            key=lambda item: item[0],
        )

        best_positions = np.empty((0, 3), dtype=np.float64)
        best_distances = np.empty((0,), dtype=np.float64)

        for position, (lower_bound, index) in enumerate(ordered):
            chunk = self._load_chunk(index)
            points = chunk["positions"]
            distances = np.linalg.norm(points - center_array, axis=1)
            best_positions = np.concatenate([best_positions, points], axis=0)
            best_distances = np.concatenate([best_distances, distances], axis=0)

            if best_distances.shape[0] > k:
                keep = np.argpartition(best_distances, k - 1)[:k]
                best_positions = best_positions[keep]
                best_distances = best_distances[keep]

            if best_distances.shape[0] >= k:
                kth = float(np.partition(best_distances, k - 1)[k - 1])
                next_lower = (
                    ordered[position + 1][0]
                    if position + 1 < len(ordered)
                    else math.inf
                )
                if kth <= next_lower:
                    break

        if best_distances.shape[0] == 0:
            return _empty_result()

        order = np.argsort(best_distances)[:k]
        return {
            "positions": best_positions[order],
            "count": int(best_distances.shape[0]),
            "returned": int(order.shape[0]),
            "truncated": False,
            "colors": None,
            "intensity": None,
        }

    def _collect(
        self,
        indices: list[int],
        predicate,
        *,
        max_points: int,
        include_colors: bool,
        include_intensity: bool,
    ) -> dict:
        position_parts: list[np.ndarray] = []
        color_parts: list[np.ndarray] = []
        intensity_parts: list[np.ndarray] = []
        total = 0

        for index in indices:
            chunk = self._load_chunk(index)
            points = chunk["positions"]
            mask = predicate(points)
            count = int(mask.sum())
            if count == 0:
                continue
            total += count
            position_parts.append(points[mask])
            if include_colors and chunk["colors"] is not None:
                color_parts.append(chunk["colors"][mask])
            if include_intensity and chunk["intensity"] is not None:
                intensity_parts.append(chunk["intensity"][mask])

        if not position_parts:
            return _empty_result()

        positions = np.concatenate(position_parts, axis=0)
        colors = np.concatenate(color_parts, axis=0) if color_parts else None
        intensity = np.concatenate(intensity_parts, axis=0) if intensity_parts else None

        truncated = positions.shape[0] > max_points
        if truncated:
            selection = np.linspace(
                0, positions.shape[0] - 1, num=max_points, dtype=np.int64
            )
            positions = positions[selection]
            colors = colors[selection] if colors is not None else None
            intensity = intensity[selection] if intensity is not None else None

        return {
            "positions": positions,
            "count": total,
            "returned": int(positions.shape[0]),
            "truncated": truncated,
            "colors": colors,
            "intensity": intensity,
        }

    def _cell_range(
        self, minimum: np.ndarray, maximum: np.ndarray
    ) -> tuple[range, range, range]:
        low = np.floor((minimum - self.minimum) / self.chunk_size_meters).astype(np.int64)
        high = np.floor((maximum - self.minimum) / self.chunk_size_meters).astype(np.int64)
        high_cells = np.floor((self.maximum - self.minimum) / self.chunk_size_meters).astype(np.int64)
        low = np.maximum(low, 0)
        high = np.minimum(high, high_cells)
        if np.any(low > high):
            return range(0), range(0), range(0)
        return (
            range(int(low[0]), int(high[0]) + 1),
            range(int(low[1]), int(high[1]) + 1),
            range(int(low[2]), int(high[2]) + 1),
        )

    def _indices_for_cells(self, cell_range: tuple[range, range, range]) -> list[int]:
        """Return chunks whose grid cell is inside the requested cell range.

        Iterating the chunk list rather than every cell in the range keeps a
        huge query bounds from turning into billions of empty grid lookups.
        """

        x_range, y_range, z_range = cell_range
        if not x_range or not y_range or not z_range:
            return []

        return sorted(
            ref.index
            for ref in self.chunks
            if ref.cell[0] in x_range
            and ref.cell[1] in y_range
            and ref.cell[2] in z_range
        )


def _aabb_distance(center: np.ndarray, minimum: np.ndarray, maximum: np.ndarray) -> float:
    delta = np.maximum(np.maximum(minimum - center, 0.0), center - maximum)
    return float(np.linalg.norm(delta))


def _floats(values: np.ndarray) -> list[float]:
    return [float(value) for value in np.asarray(values).tolist()]


def _empty_result() -> dict:
    return {
        "positions": np.empty((0, 3), dtype=np.float64),
        "count": 0,
        "returned": 0,
        "truncated": False,
        "colors": None,
        "intensity": None,
    }
