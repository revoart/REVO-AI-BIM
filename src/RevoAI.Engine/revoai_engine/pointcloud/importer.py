"""Point cloud import orchestration.

The importer is the only place where source units are converted to metres. It
keeps the source bounds and unit in the metadata so the original coordinate
system can always be audited, and it writes a chunked store instead of handing
millions of points back over JSON.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from revoai_geometry.units import METERS_PER_UNIT, UnitSystem, parse_unit

from .. import __version__
from .errors import file_not_found, invalid_cloud, invalid_unit, processing_failed
from .models import ImportOptions, PointData
from .preprocess import remove_statistical_outliers, voxel_downsample
from .readers import detect_format, read_points
from .store import write_store


def import_point_cloud(params) -> dict:
    started = time.perf_counter()
    source_path = Path(params.path).expanduser()
    if not source_path.is_absolute():
        source_path = source_path.resolve()

    if not source_path.exists():
        raise file_not_found(str(source_path))
    if not source_path.is_file():
        raise invalid_cloud(f"'{source_path}' is not a file.")

    output_directory = Path(params.output_directory).expanduser()
    if not output_directory.is_absolute():
        output_directory = output_directory.resolve()

    scan_id = params.scan_id or uuid.uuid4().hex
    fmt = detect_format(source_path, params.format)

    requested_unit: UnitSystem | None = None
    if params.unit.strip().lower() != "auto":
        try:
            requested_unit = parse_unit(params.unit)
        except ValueError as exc:
            raise invalid_unit(params.unit) from exc

    options = ImportOptions(
        path=source_path,
        format=fmt,
        unit=requested_unit,
        output_directory=output_directory,
        scan_id=scan_id,
        chunk_size_meters=float(params.chunk_size_meters),
        voxel_size_meters=params.voxel_size_meters,
        remove_outliers=bool(params.remove_outliers),
        outlier_neighbors=int(params.outlier_neighbors),
        outlier_std_ratio=float(params.outlier_std_ratio),
        overwrite=bool(params.overwrite),
    )

    data = read_points(source_path, fmt)
    unit, unit_source, unit_warnings = _resolve_unit(data, options.unit)
    warnings = list(data.warnings)
    warnings.extend(unit_warnings)

    raw_positions = np.asarray(data.positions, dtype=np.float64)
    if raw_positions.shape[0] == 0:
        raise invalid_cloud(f"'{source_path.name}' contains no points.")

    source_bounds = {
        "min": _floats(raw_positions.min(axis=0)),
        "max": _floats(raw_positions.max(axis=0)),
    }

    positions = raw_positions * METERS_PER_UNIT[unit]
    colors = data.colors
    intensity = data.intensity
    classification = data.classification

    valid_count = int(positions.shape[0])
    after_outliers = valid_count
    after_downsampling = valid_count
    preprocessing: dict = {}

    if options.remove_outliers:
        positions, colors, intensity, classification, outlier_report = (
            remove_statistical_outliers(
                positions,
                colors,
                intensity,
                classification,
                neighbors=options.outlier_neighbors,
                std_ratio=options.outlier_std_ratio,
            )
        )
        after_outliers = int(positions.shape[0])
        preprocessing["outlierRemoval"] = outlier_report
        if outlier_report["removed"]:
            warnings.append(
                f"Removed {outlier_report['removed']} statistical outlier(s)."
            )
    else:
        preprocessing["outlierRemoval"] = {"applied": False}

    if options.voxel_size_meters is not None:
        positions, colors, intensity, classification, voxel_report = voxel_downsample(
            positions,
            colors,
            intensity,
            classification,
            voxel_size_meters=options.voxel_size_meters,
        )
        after_downsampling = int(positions.shape[0])
        preprocessing["voxelDownsample"] = voxel_report
        if voxel_report["removed"]:
            warnings.append(
                f"Voxel downsampling removed {voxel_report['removed']} point(s)."
            )
    else:
        preprocessing["voxelDownsample"] = {"applied": False}

    if positions.shape[0] == 0:
        raise processing_failed(
            "No points remain after preprocessing.",
            data="Reduce outlier removal or the voxel size and retry.",
        )

    attributes: list[str] = []
    if colors is not None:
        attributes.append("colors")
    if intensity is not None:
        attributes.append("intensity")
    if classification is not None:
        attributes.append("classification")

    try:
        source_size = int(source_path.stat().st_size)
        source_hash = _sha256(source_path)
    except OSError as exc:
        raise processing_failed(
            f"Could not re-read the source file '{source_path}'.",
            data=str(exc),
        ) from exc

    metadata = {
        "scanId": scan_id,
        "createdAt": _utc_now(),
        "engineVersion": __version__,
        "source": {
            "path": str(source_path),
            "format": fmt,
            "sizeBytes": source_size,
            "sha256": source_hash,
        },
        "units": {
            "source": unit.value,
            "sourceOrigin": unit_source,
            "canonical": UnitSystem.METERS.value,
            "metersPerSourceUnit": METERS_PER_UNIT[unit],
        },
        "pointCount": {
            "original": int(data.original_count or valid_count),
            "valid": valid_count,
            "afterOutlierRemoval": after_outliers,
            "afterDownsampling": after_downsampling,
            "stored": int(positions.shape[0]),
        },
        "sourceBounds": source_bounds,
        "preprocessing": preprocessing,
        "attributes": attributes,
        "warnings": warnings,
        "coordinateSystem": "source",
    }

    store_path, metadata = write_store(
        options.output_directory,
        options.scan_id,
        positions,
        colors,
        intensity,
        classification,
        chunk_size_meters=options.chunk_size_meters,
        metadata=metadata,
        overwrite=options.overwrite,
    )

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return {
        "scanId": metadata["scanId"],
        "storePath": str(store_path),
        "sourcePath": str(source_path),
        "format": fmt,
        "unit": unit.value,
        "unitSource": unit_source,
        "pointCount": metadata["pointCount"],
        "bounds": metadata["bounds"],
        "sourceBounds": metadata["sourceBounds"],
        "chunkCount": int(metadata["storage"]["chunkCount"]),
        "attributes": attributes,
        "warnings": warnings,
        "elapsedMs": round(elapsed_ms, 3),
        "sourceSha256": metadata["source"]["sha256"],
        "engineVersion": __version__,
    }


def _resolve_unit(
    data: PointData, requested: UnitSystem | None
) -> tuple[UnitSystem, str, list[str]]:
    warnings: list[str] = []

    if requested is not None:
        if data.unit is not None and data.unit != requested:
            warnings.append(
                f"The file reports {data.unit.value}, but {requested.value} was "
                "selected by the user. The selected unit was used."
            )
        return requested, "user", warnings

    if data.unit is not None:
        return data.unit, data.unit_source, warnings

    warnings.append(
        "No reliable unit metadata was found in the file; metres were assumed. "
        "Choose the source unit explicitly if this is wrong."
    )
    return UnitSystem.METERS, "assumed", warnings


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _floats(values: np.ndarray) -> list[float]:
    return [float(value) for value in np.asarray(values).tolist()]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
