from __future__ import annotations

import json
from pathlib import Path

import laspy
import numpy as np
import pye57
import pytest
from pydantic import ValidationError

from revoai_engine.pointcloud import PointCloudStore, import_point_cloud
from revoai_engine.pointcloud.errors import PointCloudError
from revoai_engine.pointcloud.readers import detect_format, read_points
from revoai_engine.protocol import (
    ErrorCode,
    PointCloudImportParams,
    RpcRequest,
)
from revoai_engine.service import EngineState, dispatch


def _write_xyz(path: Path, rows: list[list[float]]) -> Path:
    path.write_text(
        "\n".join(" ".join(f"{value:.9g}" for value in row) for row in rows) + "\n",
        encoding="utf-8",
    )
    return path


def _initialize_params() -> dict:
    return {
        "clientName": "pytest",
        "clientVersion": "0.3.0",
        "protocolVersion": "1.0",
    }


def _request(method: str, params: dict | None = None, request_id: str = "1") -> RpcRequest:
    return RpcRequest(id=request_id, method=method, params=params)


def _import_xyz(
    tmp_path: Path,
    rows: list[list[float]],
    *,
    unit: str = "meters",
    chunk_size: float = 1.0,
    **kwargs,
):
    source = _write_xyz(tmp_path / "scan.xyz", rows)
    params = PointCloudImportParams(
        path=str(source),
        unit=unit,
        output_directory=str(tmp_path / "store"),
        scan_id="test-scan",
        chunk_size_meters=chunk_size,
        **kwargs,
    )
    return import_point_cloud(params)


def test_xyz_reader_reads_coordinates_colours_and_intensity(tmp_path: Path) -> None:
    source = _write_xyz(
        tmp_path / "scan.xyz",
        [
            [1.0, 2.0, 3.0, 255.0, 0.0, 0.0, 10.0],
            [-1.0, 0.5, 2.0, 0.0, 255.0, 0.0, 20.0],
        ],
    )

    data = read_points(source, detect_format(source))

    assert data.positions.tolist() == [[1.0, 2.0, 3.0], [-1.0, 0.5, 2.0]]
    assert data.colors is not None
    assert data.colors.tolist() == [[255, 0, 0], [0, 255, 0]]
    assert data.intensity is not None
    assert data.intensity.tolist() == [10.0, 20.0]
    assert data.unit is None
    assert data.unit_source == "assumed"


def test_ply_ascii_and_binary_readers(tmp_path: Path) -> None:
    ascii_path = tmp_path / "scan.ply"
    ascii_path.write_text(
        "ply\n"
        "format ascii 1.0\n"
        "element vertex 2\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "property uchar red\n"
        "property uchar green\n"
        "property uchar blue\n"
        "end_header\n"
        "0 0 0 255 0 0\n"
        "1 2 3 0 255 0\n",
        encoding="utf-8",
    )

    data = read_points(ascii_path, "ply")
    assert data.positions.tolist() == [[0.0, 0.0, 0.0], [1.0, 2.0, 3.0]]
    assert data.colors is not None
    assert data.colors.tolist() == [[255, 0, 0], [0, 255, 0]]

    binary_path = tmp_path / "binary.ply"
    header = (
        b"ply\n"
        b"format binary_little_endian 1.0\n"
        b"element vertex 2\n"
        b"property float x\n"
        b"property float y\n"
        b"property float z\n"
        b"property uchar red\n"
        b"property uchar green\n"
        b"property uchar blue\n"
        b"end_header\n"
    )
    dtype = np.dtype(
        [
            ("x", "<f4"),
            ("y", "<f4"),
            ("z", "<f4"),
            ("red", "u1"),
            ("green", "u1"),
            ("blue", "u1"),
        ]
    )
    vertices = np.array(
        [(1, 2, 3, 10, 20, 30), (4, 5, 6, 40, 50, 60)], dtype=dtype
    )
    binary_path.write_bytes(header + vertices.tobytes())

    data = read_points(binary_path, "ply")
    assert data.positions.tolist() == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
    assert data.colors is not None
    assert data.colors.tolist() == [[10, 20, 30], [40, 50, 60]]


def test_las_reader_reads_colours_intensity_and_wkt_unit(tmp_path: Path) -> None:
    path = tmp_path / "scan.las"
    header = laspy.LasHeader(point_format=3, version="1.4")
    wkt = (
        'PROJCS["test",GEOGCS["g",DATUM["d",SPHEROID["s",6378137,298.257223563]],'
        'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],'
        'PROJECTION["Transverse_Mercator"],PARAMETER["false_easting",0],'
        'UNIT["metre",1]]'
    )
    header.vlrs.append(
        laspy.VLR(
            user_id="LASF_Projection",
            record_id=2112,
            description="WKT",
            record_data=wkt.encode("utf-8"),
        )
    )
    las = laspy.LasData(header)
    las.x = [1.0, 2.0, 3.0]
    las.y = [4.0, 5.0, 6.0]
    las.z = [7.0, 8.0, 9.0]
    las.intensity = [100, 200, 300]
    las.red = [65535, 0, 1000]
    las.green = [0, 65535, 2000]
    las.blue = [0, 0, 3000]
    las.write(path)

    data = read_points(path, "las")

    assert data.positions.tolist() == [[1.0, 4.0, 7.0], [2.0, 5.0, 8.0], [3.0, 6.0, 9.0]]
    assert data.intensity is not None
    assert data.intensity.tolist() == [100.0, 200.0, 300.0]
    assert data.colors is not None
    assert data.colors.tolist() == [[255, 0, 0], [0, 255, 0], [4, 8, 12]]
    assert data.unit is not None
    assert data.unit.value == "meters"
    assert data.unit_source == "header"


@pytest.mark.parametrize(
    ("unit_name", "expected"),
    [
        ("millimetre", "millimeters"),
        ("US survey foot", "usSurveyFeet"),
        ("foot", "feet"),
    ],
)
def test_las_wkt_unit_names_are_preserved(
    tmp_path: Path, unit_name: str, expected: str
) -> None:
    path = tmp_path / f"unit-{expected}.las"
    header = laspy.LasHeader(point_format=0, version="1.4")
    wkt = (
        'PROJCS["test",GEOGCS["g",DATUM["d",SPHEROID["s",6378137,298.257223563]],'
        'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],'
        'PROJECTION["Transverse_Mercator"],PARAMETER["false_easting",0],'
        f'UNIT["{unit_name}",1]]'
    )
    header.vlrs.append(
        laspy.VLR(
            user_id="LASF_Projection",
            record_id=2112,
            description="WKT",
            record_data=wkt.encode("utf-8"),
        )
    )
    las = laspy.LasData(header)
    las.x = [1.0]
    las.y = [2.0]
    las.z = [3.0]
    las.write(path)

    data = read_points(path, "las")

    assert data.unit is not None
    assert data.unit.value == expected
    assert data.unit_source == "header"


def test_e57_reader_merges_transformed_scans(tmp_path: Path) -> None:
    path = tmp_path / "scan.e57"
    points = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=np.float64)
    scan = {
        "cartesianX": points[:, 0],
        "cartesianY": points[:, 1],
        "cartesianZ": points[:, 2],
        "intensity": np.array([10.0, 20.0]),
        "colorRed": np.array([255, 0], dtype=np.uint8),
        "colorGreen": np.array([0, 255], dtype=np.uint8),
        "colorBlue": np.array([0, 0], dtype=np.uint8),
    }

    writer = pye57.E57(str(path), mode="w")
    writer.write_scan_raw(scan, name="scan-a")
    writer.write_scan_raw(scan, name="scan-b", translation=np.array([10.0, 0.0, 0.0]))
    writer.close()

    data = read_points(path, "e57")

    assert data.positions.tolist() == [
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [10.0, 0.0, 0.0],
        [11.0, 0.0, 0.0],
    ]
    assert data.colors is not None
    assert data.colors.shape == (4, 3)
    assert data.intensity is not None
    assert data.intensity.tolist() == [10.0, 20.0, 10.0, 20.0]
    assert data.unit is not None
    assert data.unit.value == "meters"
    assert data.unit_source == "format"


def test_import_converts_millimetres_and_preserves_source_bounds(tmp_path: Path) -> None:
    result = _import_xyz(
        tmp_path,
        [
            [1000.0, 2000.0, 3000.0],
            [2000.0, 3000.0, 4000.0],
            [1500.0, 2500.0, 3500.0],
        ],
        unit="millimeters",
        chunk_size=1.0,
    )

    assert result["unit"] == "millimeters"
    assert result["unitSource"] == "user"
    assert result["bounds"] == {"min": [1.0, 2.0, 3.0], "max": [2.0, 3.0, 4.0]}
    assert result["sourceBounds"] == {
        "min": [1000.0, 2000.0, 3000.0],
        "max": [2000.0, 3000.0, 4000.0],
    }
    assert result["pointCount"]["stored"] == 3
    assert result["chunkCount"] >= 1

    store = PointCloudStore.open(result["storePath"])
    metadata = store.info()
    assert metadata["units"]["source"] == "millimeters"
    assert metadata["units"]["metersPerSourceUnit"] == 0.001
    assert metadata["coordinateSystem"] == "source"


def test_import_preprocessing_records_counts_and_warnings(tmp_path: Path) -> None:
    rng = np.random.default_rng(7)
    normal = rng.uniform(0.0, 1.0, size=(200, 3)).tolist()
    outlier = [[100.0, 100.0, 100.0]]
    result = _import_xyz(
        tmp_path,
        normal + outlier,
        remove_outliers=True,
        outlier_neighbors=10,
        outlier_std_ratio=1.0,
        voxel_size_meters=0.05,
    )

    counts = result["pointCount"]
    assert counts["original"] == 201
    assert counts["valid"] == 201
    assert counts["afterOutlierRemoval"] < counts["valid"]
    assert counts["afterDownsampling"] < counts["afterOutlierRemoval"]
    assert counts["stored"] == counts["afterDownsampling"]
    assert any("outlier" in warning.lower() for warning in result["warnings"])
    assert any("voxel" in warning.lower() for warning in result["warnings"])

    metadata = PointCloudStore.open(result["storePath"]).info()
    assert metadata["preprocessing"]["outlierRemoval"]["applied"] is True
    assert metadata["preprocessing"]["voxelDownsample"]["applied"] is True


def test_store_queries_bounds_radius_nearest_and_sample(tmp_path: Path) -> None:
    rows = [
        [0.1 * x, 0.1 * y, 0.1 * z, 10, 20, 30]
        for x in range(5)
        for y in range(5)
        for z in range(5)
    ]
    result = _import_xyz(tmp_path, rows, chunk_size=0.25)
    store = PointCloudStore.open(result["storePath"])

    bounds = store.query_bounds(
        [0.0, 0.0, 0.0],
        [0.2, 0.2, 0.2],
        max_points=100,
        include_colors=True,
    )
    assert bounds["count"] == 8
    assert bounds["returned"] == 8
    assert bounds["colors"] is not None
    assert bounds["colors"].tolist() == [[10, 20, 30]] * 8

    radius = store.query_radius([0.2, 0.2, 0.2], 0.01, max_points=100)
    assert radius["count"] == 1
    assert radius["positions"][0].tolist() == pytest.approx([0.2, 0.2, 0.2])

    nearest = store.nearest([0.19, 0.19, 0.19], 3)
    assert nearest["returned"] == 3
    assert nearest["positions"][0].tolist() == pytest.approx([0.2, 0.2, 0.2])

    sample = store.sample(10)
    assert sample["returned"] <= 10
    assert sample["count"] == 125
    assert sample["truncated"] is False

    huge = store.query_bounds([-1e9, -1e9, -1e9], [1e9, 1e9, 1e9], max_points=7)
    assert huge["count"] == 125
    assert huge["returned"] == 7
    assert huge["truncated"] is True


def test_store_rejects_malformed_metadata(tmp_path: Path) -> None:
    store_path = tmp_path / "bad-store"
    store_path.mkdir()
    (store_path / "metadata.json").write_text(
        json.dumps({"schemaVersion": 1, "scanId": "bad"}),
        encoding="utf-8",
    )

    with pytest.raises(PointCloudError) as error:
        PointCloudStore.open(store_path)

    assert error.value.code == ErrorCode.STORE_NOT_FOUND


def test_import_supports_e57_las_laz_ply_and_xyz(tmp_path: Path) -> None:
    e57_path = tmp_path / "scan.e57"
    e57_points = np.array([[0.0, 0.0, 0.0], [1.0, 2.0, 3.0]])
    writer = pye57.E57(str(e57_path), mode="w")
    writer.write_scan_raw(
        {
            "cartesianX": e57_points[:, 0],
            "cartesianY": e57_points[:, 1],
            "cartesianZ": e57_points[:, 2],
        }
    )
    writer.close()

    las_path = tmp_path / "scan.las"
    laz_path = tmp_path / "scan.laz"
    for path in (las_path, laz_path):
        header = laspy.LasHeader(point_format=3, version="1.2")
        las = laspy.LasData(header)
        las.x = [0.0, 1.0]
        las.y = [0.0, 2.0]
        las.z = [0.0, 3.0]
        las.write(path)

    ply_path = tmp_path / "scan.ply"
    ply_path.write_text(
        "ply\nformat ascii 1.0\nelement vertex 2\n"
        "property float x\nproperty float y\nproperty float z\n"
        "end_header\n0 0 0\n1 2 3\n",
        encoding="utf-8",
    )
    xyz_path = _write_xyz(tmp_path / "scan.xyz", [[0.0, 0.0, 0.0], [1.0, 2.0, 3.0]])

    cases = [
        (e57_path, "e57", "format"),
        (las_path, "las", "assumed"),
        (laz_path, "laz", "assumed"),
        (ply_path, "ply", "assumed"),
        (xyz_path, "xyz", "assumed"),
    ]

    for index, (path, expected_format, expected_unit_source) in enumerate(cases):
        result = import_point_cloud(
            PointCloudImportParams(
                path=str(path),
                output_directory=str(tmp_path / f"store-{index}"),
                scan_id=f"format-{index}",
                chunk_size_meters=2.0,
            )
        )
        assert result["format"] == expected_format
        assert result["pointCount"]["stored"] == 2
        assert result["unitSource"] == expected_unit_source
        assert Path(result["storePath"], "metadata.json").is_file()


def test_sample_never_exceeds_requested_limit(tmp_path: Path) -> None:
    result = _import_xyz(
        tmp_path,
        [[0.1 * i, 0.0, 0.0] for i in range(100)],
        chunk_size=100.0,
    )
    store = PointCloudStore.open(result["storePath"])
    sample = store.sample(7)
    assert sample["returned"] == 7
    assert len(sample["positions"]) == 7


def test_import_rejects_missing_file_and_unknown_unit(tmp_path: Path) -> None:
    with pytest.raises(PointCloudError) as missing:
        import_point_cloud(
            PointCloudImportParams(
                path=str(tmp_path / "missing.xyz"),
                output_directory=str(tmp_path / "store"),
            )
        )
    assert missing.value.code == ErrorCode.FILE_NOT_FOUND

    source = _write_xyz(tmp_path / "scan.xyz", [[0.0, 0.0, 0.0]])
    with pytest.raises(ValidationError):
        PointCloudImportParams(
            path=str(source),
            unit="furlongs",
            output_directory=str(tmp_path / "store"),
        )

    state = EngineState()
    dispatch(state, _request("initialize", _initialize_params()))
    rejected = dispatch(
        state,
        _request(
            "pointcloud.import",
            {
                "path": str(source),
                "unit": "furlongs",
                "outputDirectory": str(tmp_path / "store"),
            },
        ),
    )
    assert rejected is not None
    assert rejected.error is not None
    assert rejected.error.code == ErrorCode.INVALID_PARAMS


def test_service_pointcloud_round_trip(tmp_path: Path) -> None:
    state = EngineState()
    initialized = dispatch(state, _request("initialize", _initialize_params()))
    assert initialized is not None and initialized.error is None

    source = _write_xyz(
        tmp_path / "scan.xyz",
        [[0.0, 0.0, 0.0], [1.0, 2.0, 3.0], [2.0, 4.0, 6.0]],
    )
    imported = dispatch(
        state,
        _request(
            "pointcloud.import",
            {
                "path": str(source),
                "unit": "meters",
                "outputDirectory": str(tmp_path / "store"),
                "scanId": "service-scan",
                "chunkSizeMeters": 2.0,
            },
            "import",
        ),
    )
    assert imported is not None and imported.error is None
    assert imported.result["scanId"] == "service-scan"
    assert imported.result["pointCount"]["stored"] == 3

    info = dispatch(
        state,
        _request("pointcloud.info", {"storePath": imported.result["storePath"]}, "info"),
    )
    assert info is not None and info.error is None
    assert info.result["scanId"] == "service-scan"
    assert info.result["chunkCount"] == imported.result["chunkCount"]

    queried = dispatch(
        state,
        _request(
            "pointcloud.query",
            {
                "storePath": imported.result["storePath"],
                "bounds": {"min": [-1.0, -1.0, -1.0], "max": [1.5, 3.5, 5.0]},
                "maxPoints": 10,
                "includeColors": True,
            },
            "query",
        ),
    )
    assert queried is not None and queried.error is None
    assert queried.result["count"] == 2
    assert queried.result["returned"] == 2
    assert queried.result["positions"] == [[0.0, 0.0, 0.0], [1.0, 2.0, 3.0]]


def test_pointcloud_import_requires_initialize(tmp_path: Path) -> None:
    source = _write_xyz(tmp_path / "scan.xyz", [[0.0, 0.0, 0.0]])
    response = dispatch(
        EngineState(),
        _request(
            "pointcloud.import",
            {
                "path": str(source),
                "outputDirectory": str(tmp_path / "store"),
            },
        ),
    )
    assert response is not None
    assert response.error is not None
    assert response.error.code == ErrorCode.NOT_INITIALIZED


def test_store_metadata_is_valid_json(tmp_path: Path) -> None:
    result = _import_xyz(tmp_path, [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]])
    metadata_path = Path(result["storePath"]) / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["schemaVersion"] == 1
    assert metadata["scanId"] == "test-scan"
    assert metadata["storage"]["chunkCount"] == len(metadata["storage"]["chunks"])
    assert metadata["storage"]["grid"]
