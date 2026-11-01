"""Internal point cloud data structures.

The engine's canonical unit is the metre. Readers report the unit they found
(or ``None`` when the file has no reliable unit metadata); conversion happens
once, in the importer, so no downstream code has to guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from revoai_geometry.units import UnitSystem


@dataclass
class PointData:
    """Points in their source coordinate system and source unit."""

    positions: np.ndarray  # (N, 3) float64, source units
    colors: np.ndarray | None = None  # (N, 3) uint8, 0-255
    intensity: np.ndarray | None = None  # (N,) float32
    classification: np.ndarray | None = None  # (N,) uint8
    unit: UnitSystem | None = None
    unit_source: str = "assumed"
    original_count: int | None = None
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.positions = np.asarray(self.positions, dtype=np.float64)
        if self.positions.ndim != 2 or self.positions.shape[1] != 3:
            raise ValueError("Point positions must have shape (N, 3).")
        if self.original_count is None:
            self.original_count = int(self.positions.shape[0])


@dataclass(frozen=True)
class ImportOptions:
    path: Path
    format: str
    unit: UnitSystem | None
    output_directory: Path
    scan_id: str
    chunk_size_meters: float
    voxel_size_meters: float | None
    remove_outliers: bool
    outlier_neighbors: int
    outlier_std_ratio: float
    overwrite: bool
