from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from revoai_engine.analysis import AnalysisError, load_segmentation, run_segmentation
from revoai_engine.pointcloud import import_point_cloud
from revoai_engine.protocol import (
    ErrorCode,
    PointCloudImportParams,
    RpcRequest,
    SegmentationInfoParams,
    SegmentationRunParams,
)
from revoai_engine.service import EngineState, dispatch


def _initialize_params() -> dict:
    return {
        "clientName": "pytest",
        "clientVersion": "0.4.0",
        "protocolVersion": "1.0",
    }


def _request(method: str, params: dict | None = None, request_id: str = "1") -> RpcRequest:
    return RpcRequest(id=request_id, method=method, params=params)


def _room_points() -> np.ndarray:
    xs = np.linspace(0.1, 3.9, 20)
    ys = np.linspace(0.1, 2.9, 15)
    zs = np.linspace(0.05, 2.65, 15)
    grid = np.meshgrid(xs, ys, zs, indexing="ij")
    x, y, z = grid

    def surface(values: np.ndarray) -> np.ndarray:
        return np.column_stack([values[0].ravel(), values[1].ravel(), values[2].ravel()])

    floor = surface((x, y, np.zeros_like(z)))
    ceiling = surface((x, y, np.full_like(z, 2.70)))
    west = surface((np.zeros_like(x), y, z))
    east = surface((np.full_like(x, 4.0), y, z))
    south = surface((x, np.zeros_like(y), z))
    north = surface((x, np.full_like(y, 3.0), z))

    rng = np.random.default_rng(11)
    points = np.vstack([floor, ceiling, west, east, south, north])
    return points + rng.normal(0.0, 0.0015, points.shape)


def _import_room(tmp_path: Path, name: str = "room") -> dict:
    source = tmp_path / f"{name}.xyz"
    np.savetxt(source, _room_points(), fmt="%.6f")
    return import_point_cloud(
        PointCloudImportParams(
            path=str(source),
            unit="meters",
            output_directory=str(tmp_path / "stores"),
            scan_id=name,
            chunk_size_meters=5.0,
        )
    )


def test_segmentation_detects_room_planes_and_persists_result(tmp_path: Path) -> None:
    imported = _import_room(tmp_path)

    result = run_segmentation(
        SegmentationRunParams(
            store_path=imported["storePath"],
            voxel_size_meters=0.0,
            max_points=10_000,
            plane_distance_meters=0.01,
            min_plane_points=100,
            max_planes=20,
        )
    )

    summary = result["summary"]
    assert summary["segments"] >= 6
    assert summary["byKind"]["floor"] >= 1
    assert summary["byKind"]["ceiling"] >= 1
    assert summary["byKind"]["wall"] >= 4
    assert summary["meanConfidence"] > 0.80
    assert summary["highConfidenceSegments"] >= 6
    assert result["method"] == "geometric-plane-baseline/1"
    assert "not dimensional accuracy" in result["methodNote"]

    for element in result["elements"]:
        assert 0.0 <= element["confidence"] <= 1.0
        assert element["pointCount"] >= 100
        assert len(element["plane"]["normal"]) == 3
        assert len(element["bounds"]["min"]) == 3
        assert element["signals"]["planarity"] > 0.9

    stored = load_segmentation(imported["storePath"])
    assert stored["scanId"] == imported["scanId"]
    assert stored["summary"] == result["summary"]
    assert Path(result["resultPath"]).is_file()


def test_segmentation_info_is_available_over_protocol(tmp_path: Path) -> None:
    imported = _import_room(tmp_path, name="protocol-room")
    state = EngineState()
    initialized = dispatch(state, _request("initialize", _initialize_params()))
    assert initialized is not None and initialized.error is None

    run = dispatch(
        state,
        _request(
            "segmentation.run",
            {
                "storePath": imported["storePath"],
                "voxelSizeMeters": 0.0,
                "maxPoints": 10_000,
                "planeDistanceMeters": 0.01,
                "minPlanePoints": 100,
                "maxPlanes": 20,
            },
            "run",
        ),
    )
    assert run is not None and run.error is None
    assert run.result["summary"]["segments"] >= 6

    info = dispatch(
        state,
        _request(
            "segmentation.info",
            {"storePath": imported["storePath"]},
            "info",
        ),
    )
    assert info is not None and info.error is None
    assert info.result["scanId"] == imported["scanId"]
    assert info.result["summary"] == run.result["summary"]


def test_segmentation_not_found_is_typed(tmp_path: Path) -> None:
    imported = _import_room(tmp_path, name="no-analysis")

    with pytest.raises(AnalysisError) as error:
        load_segmentation(imported["storePath"])
    assert error.value.code == ErrorCode.ANALYSIS_NOT_FOUND

    state = EngineState()
    dispatch(state, _request("initialize", _initialize_params()))
    response = dispatch(
        state,
        _request(
            "segmentation.info",
            SegmentationInfoParams(store_path=imported["storePath"]).model_dump(
                by_alias=True
            ),
            "missing-analysis",
        ),
    )
    assert response is not None and response.error is not None
    assert response.error.code == ErrorCode.ANALYSIS_NOT_FOUND
