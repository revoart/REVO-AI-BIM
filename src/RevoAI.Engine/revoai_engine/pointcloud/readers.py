"""Point cloud readers for the formats supported in Phase 3.

Each reader returns :class:`PointData` in the file's own coordinate system and
reports the unit it could prove. It never recentres, rotates or rescales points;
unit conversion is a separate, explicit step in the importer.
"""

from __future__ import annotations

import re
from pathlib import Path

import laspy
import numpy as np
import pye57

from revoai_geometry.units import UnitSystem

from .errors import invalid_cloud, processing_failed, unsupported_format
from .models import PointData

SUPPORTED_FORMATS = ("e57", "las", "laz", "ply", "xyz")

_FORMAT_ALIASES = {
    "e57": "e57",
    "las": "las",
    "laz": "laz",
    "ply": "ply",
    "xyz": "xyz",
    "txt": "xyz",
    "asc": "xyz",
    "pts": "xyz",
}

_PLY_TYPES = {
    "char": "i1",
    "int8": "i1",
    "uchar": "u1",
    "uint8": "u1",
    "short": "i2",
    "int16": "i2",
    "ushort": "u2",
    "uint16": "u2",
    "int": "i4",
    "int32": "i4",
    "uint": "u4",
    "uint32": "u4",
    "float": "f4",
    "float32": "f4",
    "double": "f8",
    "float64": "f8",
}


def detect_format(path: Path, explicit: str | None = None) -> str:
    if explicit and explicit.strip():
        key = explicit.strip().lower().lstrip(".")
        if key not in _FORMAT_ALIASES:
            raise unsupported_format(str(path), f"Unknown format '{explicit}'.")
        return _FORMAT_ALIASES[key]

    suffix = path.suffix.lower().lstrip(".")
    if suffix in _FORMAT_ALIASES:
        return _FORMAT_ALIASES[suffix]

    raise unsupported_format(str(path), f"Unknown extension '.{suffix}'.")


def read_points(path: Path, fmt: str) -> PointData:
    if fmt == "e57":
        return _read_e57(path)
    if fmt == "las" or fmt == "laz":
        return _read_las(path)
    if fmt == "ply":
        return _read_ply(path)
    if fmt == "xyz":
        return _read_xyz(path)
    raise unsupported_format(str(path), f"Reader '{fmt}' is not implemented.")


# ---------------------------------------------------------------------------
# XYZ / TXT
# ---------------------------------------------------------------------------


def _read_xyz(path: Path) -> PointData:
    warnings: list[str] = []
    rows: list[list[float]] = []
    delimiter: str | None = None
    column_count: int | None = None
    skipped = 0

    try:
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            for raw_line in stream:
                line = raw_line.strip()
                if not line or line.startswith("#") or line.startswith("//"):
                    continue

                if delimiter is None:
                    if "," in line:
                        delimiter = ","
                    elif ";" in line:
                        delimiter = ";"

                parts = line.split(delimiter) if delimiter else line.split()
                try:
                    values = [float(part.strip()) for part in parts if part.strip()]
                except ValueError:
                    skipped += 1
                    continue

                if len(values) < 3:
                    skipped += 1
                    continue

                if column_count is None:
                    column_count = len(values)

                if len(values) < column_count:
                    skipped += 1
                    continue

                rows.append(values[:column_count])
    except OSError as exc:
        raise processing_failed(f"Could not read '{path}': {exc}") from exc

    if not rows or column_count is None:
        raise invalid_cloud(
            f"'{path.name}' does not contain any parseable XYZ rows.",
            data=f"Skipped {skipped} non-numeric or short lines.",
        )

    if skipped:
        warnings.append(f"Skipped {skipped} non-numeric or short line(s) in the XYZ file.")

    array = np.asarray(rows, dtype=np.float64)
    original_count = int(array.shape[0])
    finite = np.isfinite(array[:, :3]).all(axis=1)

    if not finite.all():
        dropped = int((~finite).sum())
        warnings.append(f"Dropped {dropped} point(s) with non-finite coordinates.")
        array = array[finite]

    if array.shape[0] == 0:
        raise invalid_cloud(f"'{path.name}' contains no finite XYZ points.")

    positions = array[:, :3].copy()
    colors: np.ndarray | None = None
    intensity: np.ndarray | None = None

    if column_count == 4 or column_count == 5:
        intensity = _as_intensity(array[:, 3], warnings)
    elif column_count == 6:
        colors = _normalize_colors(array[:, 3:6], warnings)
    elif column_count >= 7:
        colors = _normalize_colors(array[:, 3:6], warnings)
        intensity = _as_intensity(array[:, 6], warnings)

    return PointData(
        positions=positions,
        colors=colors,
        intensity=intensity,
        unit=None,
        unit_source="assumed",
        original_count=original_count,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# PLY
# ---------------------------------------------------------------------------


def _read_ply(path: Path) -> PointData:
    warnings: list[str] = []

    try:
        with path.open("rb") as stream:
            if stream.readline().strip() != b"ply":
                raise invalid_cloud(f"'{path.name}' is not a PLY file (missing 'ply' header).")

            file_format: str | None = None
            elements: list[dict] = []

            while True:
                raw = stream.readline()
                if not raw:
                    raise invalid_cloud(f"'{path.name}' ended before 'end_header'.")

                line = raw.strip()
                if not line:
                    continue

                parts = line.split()
                keyword = parts[0]

                if keyword in (b"comment", b"obj_info"):
                    continue
                if keyword == b"format":
                    if len(parts) < 3:
                        raise invalid_cloud(f"'{path.name}' has a malformed PLY format line.")
                    file_format = parts[1].decode("ascii", errors="replace").lower()
                elif keyword == b"element":
                    if len(parts) < 3:
                        raise invalid_cloud(f"'{path.name}' has a malformed PLY element line.")
                    try:
                        element_count = int(parts[2])
                    except ValueError as exc:
                        raise invalid_cloud(
                            f"'{path.name}' has a non-numeric PLY element count."
                        ) from exc
                    if element_count < 0:
                        raise invalid_cloud(
                            f"'{path.name}' has a negative PLY element count."
                        )
                    elements.append(
                        {
                            "name": parts[1].decode("ascii", errors="replace"),
                            "count": element_count,
                            "properties": [],
                        }
                    )
                elif keyword == b"property":
                    if not elements:
                        raise invalid_cloud(f"'{path.name}' declares a property before any element.")
                    if len(parts) == 5 and parts[1] == b"list":
                        elements[-1]["properties"].append(
                            {
                                "name": parts[4].decode("ascii", errors="replace"),
                                "type": "list",
                                "count_type": parts[2].decode("ascii", errors="replace"),
                                "item_type": parts[3].decode("ascii", errors="replace"),
                            }
                        )
                    elif len(parts) == 3:
                        elements[-1]["properties"].append(
                            {
                                "name": parts[2].decode("ascii", errors="replace"),
                                "type": parts[1].decode("ascii", errors="replace"),
                            }
                        )
                    else:
                        raise invalid_cloud(f"'{path.name}' has a malformed PLY property line.")
                elif keyword == b"end_header":
                    break

            if file_format not in ("ascii", "binary_little_endian", "binary_big_endian"):
                raise unsupported_format(str(path), f"PLY format '{file_format}' is not supported.")

            vertex_index = next(
                (index for index, element in enumerate(elements) if element["name"] == "vertex"),
                None,
            )
            if vertex_index is None:
                raise invalid_cloud(f"'{path.name}' has no PLY vertex element.")

            # Skip any elements declared before the vertex element.
            for element in elements[:vertex_index]:
                _skip_ply_element(stream, element, file_format)

            vertex = elements[vertex_index]
            positions, colors, intensity = _read_ply_vertex(stream, vertex, file_format, warnings)
    except OSError as exc:
        raise processing_failed(f"Could not read '{path}': {exc}") from exc

    finite = np.isfinite(positions).all(axis=1)
    original_count = int(positions.shape[0])
    if not finite.all():
        dropped = int((~finite).sum())
        warnings.append(f"Dropped {dropped} point(s) with non-finite coordinates.")
        positions = positions[finite]
        if colors is not None:
            colors = colors[finite]
        if intensity is not None:
            intensity = intensity[finite]

    if positions.shape[0] == 0:
        raise invalid_cloud(f"'{path.name}' contains no finite vertex positions.")

    return PointData(
        positions=positions,
        colors=colors,
        intensity=intensity,
        unit=None,
        unit_source="assumed",
        original_count=original_count,
        warnings=warnings,
    )


def _skip_ply_element(stream, element: dict, file_format: str) -> None:
    properties = element["properties"]
    if any(prop["type"] == "list" for prop in properties):
        raise invalid_cloud(
            "PLY elements with list properties before the vertex element are not supported."
        )

    if file_format == "ascii":
        for _ in range(int(element["count"])):
            if not stream.readline():
                raise invalid_cloud("PLY file ended while skipping an element.")
        return

    endian = "<" if file_format == "binary_little_endian" else ">"
    dtype = np.dtype(
        [
            (prop["name"], _ply_type(prop["type"], endian))
            for prop in properties
        ]
    )
    stream.seek(dtype.itemsize * int(element["count"]), 1)


def _ply_type(type_name: str, endian: str) -> str:
    try:
        return endian + _PLY_TYPES[type_name]
    except KeyError as exc:
        raise invalid_cloud(f"Unsupported PLY property type '{type_name}'.") from exc


def _read_ply_vertex(
    stream,
    element: dict,
    file_format: str,
    warnings: list[str],
) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None]:
    properties = element["properties"]
    if any(prop["type"] == "list" for prop in properties):
        raise invalid_cloud("PLY vertex elements with list properties are not supported.")

    names = [prop["name"] for prop in properties]
    if not {"x", "y", "z"}.issubset(names):
        raise invalid_cloud("PLY vertex element must contain x, y and z properties.")

    count = int(element["count"])

    if file_format == "ascii":
        rows: list[list[float]] = []
        while len(rows) < count:
            raw = stream.readline()
            if not raw:
                break
            line = raw.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) != len(properties):
                raise invalid_cloud(
                    f"PLY ASCII vertex line has {len(parts)} values, expected {len(properties)}."
                )
            try:
                rows.append([float(part) for part in parts])
            except ValueError as exc:
                raise invalid_cloud(f"PLY ASCII vertex contains a non-numeric value: {exc}") from exc

        if len(rows) != count:
            raise invalid_cloud(f"PLY file declared {count} vertices but contained {len(rows)}.")

        array = np.asarray(rows, dtype=np.float64)
        columns = {name: array[:, index] for index, name in enumerate(names)}
    else:
        endian = "<" if file_format == "binary_little_endian" else ">"
        dtype = np.dtype(
            [
                (prop["name"], _ply_type(prop["type"], endian))
                for prop in properties
            ]
        )
        payload = stream.read(dtype.itemsize * count)
        if len(payload) != dtype.itemsize * count:
            raise invalid_cloud(f"PLY file ended before all {count} vertices were read.")
        array = np.frombuffer(payload, dtype=dtype, count=count)
        columns = {name: array[name] for name in names}

    positions = np.column_stack(
        [
            np.asarray(columns["x"], dtype=np.float64),
            np.asarray(columns["y"], dtype=np.float64),
            np.asarray(columns["z"], dtype=np.float64),
        ]
    )

    colors = None
    if {"red", "green", "blue"}.issubset(columns):
        colors = _normalize_colors(
            np.column_stack([columns["red"], columns["green"], columns["blue"]]),
            warnings,
        )

    intensity = None
    for name in ("intensity", "scalar_intensity", "scalar_Intensity"):
        if name in columns:
            intensity = _as_intensity(np.asarray(columns[name], dtype=np.float64), warnings)
            break

    return positions, colors, intensity


# ---------------------------------------------------------------------------
# LAS / LAZ
# ---------------------------------------------------------------------------


def _read_las(path: Path) -> PointData:
    warnings: list[str] = []

    try:
        las = laspy.read(str(path))
    except Exception as exc:  # laspy raises several backend-specific exceptions
        raise invalid_cloud(
            f"Could not read LAS/LAZ file '{path.name}': {exc}",
        ) from exc

    positions = np.column_stack(
        [
            np.asarray(las.x, dtype=np.float64),
            np.asarray(las.y, dtype=np.float64),
            np.asarray(las.z, dtype=np.float64),
        ]
    )
    original_count = int(positions.shape[0])

    finite = np.isfinite(positions).all(axis=1)
    if not finite.all():
        dropped = int((~finite).sum())
        warnings.append(f"Dropped {dropped} point(s) with non-finite coordinates.")
        positions = positions[finite]

    if positions.shape[0] == 0:
        raise invalid_cloud(f"'{path.name}' contains no finite LAS points.")

    dimensions = set(las.point_format.dimension_names)

    colors = None
    if {"red", "green", "blue"}.issubset(dimensions):
        colors = _normalize_colors(
            np.column_stack([las.red, las.green, las.blue]),
            warnings,
        )
        if colors is not None and not finite.all():
            colors = colors[finite]

    intensity = None
    if "intensity" in dimensions:
        intensity = _as_intensity(np.asarray(las.intensity, dtype=np.float64), warnings)
        if not finite.all():
            intensity = intensity[finite]

    classification = None
    if "classification" in dimensions:
        classification = np.asarray(las.classification, dtype=np.uint8)
        if not finite.all():
            classification = classification[finite]

    unit = _detect_las_unit(las)
    return PointData(
        positions=positions,
        colors=colors,
        intensity=intensity,
        classification=classification,
        unit=unit,
        unit_source="header" if unit is not None else "assumed",
        original_count=original_count,
        warnings=warnings,
    )


def _detect_las_unit(las) -> UnitSystem | None:
    """Read a length unit from a WKT CRS VLR when one is present.

    LAS has no dedicated unit field. Many files carry a WKT CRS (record id
    2112); when it names a length unit we use it. Otherwise the importer
    reports that metres were assumed.
    """

    for vlr in getattr(las.header, "vlrs", []):
        if getattr(vlr, "record_id", None) != 2112:
            continue

        raw = getattr(vlr, "record_data", None)
        if raw is None:
            raw = getattr(vlr, "record_data_bytes", None)
        if callable(raw):
            try:
                raw = raw()
            except Exception:
                raw = None
        if raw is None:
            raw = getattr(vlr, "string", None)
        if raw is None:
            continue

        try:
            text = raw.decode("utf-8", errors="ignore") if isinstance(raw, bytes) else str(raw)
        except Exception:
            continue

        # WKT2 uses LENGTHUNIT; WKT1 uses UNIT. A WKT1 geographic CRS also
        # contains UNIT["degree", ...], so ignore angular units.
        for match in re.finditer(
            r'(?:LENGTHUNIT|UNIT)\s*\[\s*"([^"]+)"', text, flags=re.IGNORECASE
        ):
            name = match.group(1).strip().lower()
            if "millimet" in name:
                return UnitSystem.MILLIMETERS
            if "centimet" in name:
                return UnitSystem.CENTIMETERS
            if "metre" in name or "meter" in name:
                return UnitSystem.METERS
            if "inch" in name:
                return UnitSystem.INCHES
            if "survey" in name and ("foot" in name or "feet" in name):
                return UnitSystem.US_SURVEY_FEET
            if "ftus" in name or "usft" in name:
                return UnitSystem.US_SURVEY_FEET
            if "foot" in name or "feet" in name:
                return UnitSystem.FEET

    return None


# ---------------------------------------------------------------------------
# E57
# ---------------------------------------------------------------------------


def _read_e57(path: Path) -> PointData:
    warnings: list[str] = []
    position_parts: list[np.ndarray] = []
    color_parts: list[np.ndarray] = []
    intensity_parts: list[np.ndarray] = []
    original_count = 0
    scans_with_color = 0
    scans_with_intensity = 0

    try:
        reader = pye57.E57(str(path))
    except Exception as exc:
        raise invalid_cloud(f"Could not open E57 file '{path.name}': {exc}") from exc

    try:
        if reader.scan_count == 0:
            raise invalid_cloud(f"'{path.name}' contains no E57 scans.")

        for index in range(reader.scan_count):
            try:
                data = reader.read_scan(
                    index,
                    intensity=True,
                    colors=True,
                    transform=True,
                    ignore_missing_fields=True,
                )
            except Exception as exc:
                warnings.append(f"Skipped E57 scan {index}: {exc}")
                continue

            if not {"cartesianX", "cartesianY", "cartesianZ"}.issubset(data):
                warnings.append(f"Skipped E57 scan {index}: missing Cartesian coordinates.")
                continue

            x = np.asarray(data["cartesianX"], dtype=np.float64)
            y = np.asarray(data["cartesianY"], dtype=np.float64)
            z = np.asarray(data["cartesianZ"], dtype=np.float64)
            original_count += int(x.shape[0])

            valid = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
            if "cartesianInvalidState" in data:
                valid &= np.asarray(data["cartesianInvalidState"]) == 0

            if not valid.any():
                warnings.append(f"E57 scan {index} contains no valid points.")
                continue

            positions = np.column_stack([x[valid], y[valid], z[valid]])
            position_parts.append(positions)

            if all(key in data for key in ("colorRed", "colorGreen", "colorBlue")):
                colors = np.column_stack(
                    [data["colorRed"], data["colorGreen"], data["colorBlue"]]
                ).astype(np.uint8)
                if "isColorInvalid" in data:
                    invalid_colors = np.asarray(data["isColorInvalid"]).astype(bool)
                    colors[invalid_colors] = 0
                color_parts.append(colors[valid])
                scans_with_color += 1

            if "intensity" in data:
                intensity = np.asarray(data["intensity"], dtype=np.float32)
                if "isIntensityInvalid" in data:
                    invalid_intensity = np.asarray(data["isIntensityInvalid"]).astype(bool)
                    intensity[invalid_intensity] = 0.0
                intensity_parts.append(intensity[valid])
                scans_with_intensity += 1
    finally:
        try:
            reader.close()
        except Exception:
            pass

    if not position_parts:
        raise invalid_cloud(f"'{path.name}' contains no valid E57 points.")

    positions = np.concatenate(position_parts, axis=0)
    colors = np.concatenate(color_parts, axis=0) if len(color_parts) == len(position_parts) else None
    intensity = (
        np.concatenate(intensity_parts, axis=0)
        if len(intensity_parts) == len(position_parts)
        else None
    )

    if scans_with_color not in (0, len(position_parts)):
        warnings.append("Some E57 scans had no colour; colour was omitted for consistency.")
    if scans_with_intensity not in (0, len(position_parts)):
        warnings.append("Some E57 scans had no intensity; intensity was omitted for consistency.")

    return PointData(
        positions=positions,
        colors=colors,
        intensity=intensity,
        unit=UnitSystem.METERS,
        unit_source="format",
        original_count=original_count,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Shared attribute helpers
# ---------------------------------------------------------------------------


def _normalize_colors(values: np.ndarray, warnings: list[str]) -> np.ndarray:
    array = np.asarray(values)
    if array.ndim != 2 or array.shape[1] != 3:
        raise invalid_cloud("Colour data must have three channels.")

    if array.dtype.kind in "ui":
        maximum = int(array.max()) if array.size else 0
        if maximum <= 255:
            return array.astype(np.uint8)
        if maximum <= 65535:
            return np.clip(np.rint(array.astype(np.float64) / 257.0), 0, 255).astype(np.uint8)

        warnings.append("Colour values exceeded 16 bits and were clipped to 0-255.")
        return np.clip(np.rint(array.astype(np.float64) / 257.0), 0, 255).astype(np.uint8)

    floating = np.nan_to_num(array.astype(np.float64), nan=0.0, posinf=255.0, neginf=0.0)
    if floating.size and float(floating.max()) <= 1.0:
        floating = floating * 255.0

    return np.clip(np.rint(floating), 0, 255).astype(np.uint8)


def _as_intensity(values: np.ndarray, warnings: list[str]) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if not np.isfinite(array).all():
        warnings.append("Non-finite intensity values were replaced with 0.")
        array = np.nan_to_num(array, nan=0.0, posinf=0.0, neginf=0.0)
    return array.astype(np.float32)
