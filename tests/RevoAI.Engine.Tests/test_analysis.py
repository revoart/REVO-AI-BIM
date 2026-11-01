from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from revoai_engine.analysis import AnalysisError, load_segmentation, run_segmentation
from revoai_engine.pointcloud import import_point_cloud
from revoai_engine.protocol import (
    ErrorCode,
    PointCloudImportParams,
    ReconstructionPlanParams,
    RpcRequest,
    SegmentationInfoParams,
    SegmentationRunParams,
)
from revoai_engine.reconstruction import PlanError, create_plan
from revoai_engine.reconstruction.astra import request_astra_plan
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
        assert len(element["boundary"]) >= 3
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


def test_reconstruction_plan_creates_levels_floors_and_walls(tmp_path: Path) -> None:
    imported = _import_room(tmp_path, name="plan-room")
    run_segmentation(
        SegmentationRunParams(
            store_path=imported["storePath"],
            voxel_size_meters=0.0,
            max_points=10_000,
            plane_distance_meters=0.01,
            min_plane_points=100,
            max_planes=20,
        )
    )

    plan = create_plan(
        ReconstructionPlanParams(
            store_path=imported["storePath"],
            confidence_threshold=0.5,
            fallback_wall_height_meters=2.7,
            level_tolerance_meters=0.25,
            max_elements=20,
        )
    )

    assert plan["method"] == "geometric-floor-wall-plan/1"
    assert len(plan["levels"]) == 1
    assert len(plan["floors"]) == 1
    assert len(plan["walls"]) == 4
    assert Path(plan["resultPath"]).is_file()
    assert plan["levels"][0]["elevationMeters"] == pytest.approx(0.0, abs=0.02)

    for wall in plan["walls"]:
        assert len(wall["start"]) == 3
        assert len(wall["end"]) == 3
        assert wall["heightMeters"] == pytest.approx(2.7, abs=0.05)
        assert wall["heightSource"] == "ceiling"
        assert wall["start"][2] == pytest.approx(0.0, abs=0.02)
        assert wall["end"][2] == pytest.approx(0.0, abs=0.02)

    floor = plan["floors"][0]
    assert len(floor["boundary"]) >= 3
    assert floor["areaM2"] > 10.0


def test_reconstruction_plan_over_protocol(tmp_path: Path) -> None:
    imported = _import_room(tmp_path, name="plan-protocol-room")
    state = EngineState()
    dispatch(state, _request("initialize", _initialize_params()))
    dispatch(
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
        ),
    )

    response = dispatch(
        state,
        _request(
            "reconstruction.plan",
            {
                "storePath": imported["storePath"],
                "confidenceThreshold": 0.5,
                "maxElements": 20,
            },
            "plan",
        ),
    )
    assert response is not None and response.error is None
    assert len(response.result["levels"]) == 1
    assert len(response.result["floors"]) == 1
    assert len(response.result["walls"]) == 4


def test_external_ai_plan_is_validated_and_normalized(tmp_path: Path) -> None:
    imported = _import_room(tmp_path, name="external-room")
    plan_path = tmp_path / "external-plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "method": "external-ai/room-v1",
                "levels": [
                    {"id": "L1", "name": "Level 1", "elevationMeters": 0.0}
                ],
                "floors": [
                    {
                        "id": "F1",
                        "levelId": "L1",
                        "boundary": [
                            [0.0, 0.0, 0.0],
                            [4.0, 0.0, 0.0],
                            [4.0, 3.0, 0.0],
                            [0.0, 3.0, 0.0],
                        ],
                        "confidence": 0.91,
                    }
                ],
                "walls": [
                    {
                        "id": "W1",
                        "levelId": "L1",
                        "start": [0.0, 0.0, 0.0],
                        "end": [4.0, 0.0, 0.0],
                        "heightMeters": 2.7,
                        "confidence": 0.88,
                    },
                    {
                        "id": "W2",
                        "levelId": "L1",
                        "start": [4.0, 0.0, 0.0],
                        "end": [4.0, 3.0, 0.0],
                        "heightMeters": 2.7,
                        "confidence": 0.86,
                    },
                ],
                "rooms": [{"id": "ignored"}],
            }
        ),
        encoding="utf-8",
    )

    result = create_plan(
        ReconstructionPlanParams(
            store_path=imported["storePath"],
            external_plan_path=str(plan_path),
            max_elements=20,
        )
    )

    assert result["method"] == "external-bim-plan/1"
    assert len(result["levels"]) == 1
    assert len(result["floors"]) == 1
    assert len(result["walls"]) == 2
    assert result["floors"][0]["areaM2"] == pytest.approx(12.0)
    assert any("rooms" in warning for warning in result["warnings"])
    assert Path(result["resultPath"]).is_file()


def test_external_ai_plan_rejects_invalid_geometry(tmp_path: Path) -> None:
    imported = _import_room(tmp_path, name="external-invalid")
    plan_path = tmp_path / "invalid-plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "levels": [{"id": "L1", "elevationMeters": 0.0}],
                "floors": [
                    {
                        "levelId": "L1",
                        "boundary": [[0, 0, 0], [4, 0, 0], [4, 3, 0]],
                    }
                ],
                "walls": [
                    {
                        "levelId": "L1",
                        "start": [0, 0, 0],
                        "end": [0, 0, 0],
                        "heightMeters": 2.7,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(PlanError) as error:
        create_plan(
            ReconstructionPlanParams(
                store_path=imported["storePath"],
                external_plan_path=str(plan_path),
            )
        )

    assert error.value.code == ErrorCode.PLAN_INVALID


def test_astra_provider_plan_is_validated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    imported = _import_room(tmp_path, name="astra-room")
    run_segmentation(
        SegmentationRunParams(
            store_path=imported["storePath"],
            voxel_size_meters=0.0,
            max_points=10_000,
            plane_distance_meters=0.01,
            min_plane_points=100,
            max_planes=20,
        )
    )

    def fake_request(context, *, model, **kwargs):
        assert context["scanId"] == imported["scanId"]
        assert model == "gpt-6-astra"
        return {
            "method": "astra-test",
            "levels": [{"id": "L1", "name": "Level 1", "elevationMeters": 0.0}],
            "floors": [
                {
                    "id": "F1",
                    "levelId": "L1",
                    "boundary": [[0, 0, 0], [4, 0, 0], [4, 3, 0], [0, 3, 0]],
                    "confidence": 0.9,
                }
            ],
            "walls": [
                {
                    "id": "W1",
                    "levelId": "L1",
                    "start": [0, 0, 0],
                    "end": [4, 0, 0],
                    "heightMeters": 2.7,
                    "confidence": 0.85,
                }
            ],
        }

    monkeypatch.setattr(
        "revoai_engine.reconstruction.astra.request_astra_plan",
        fake_request,
    )

    result = create_plan(
        ReconstructionPlanParams(
            store_path=imported["storePath"],
            provider="astra",
            astra_model="gpt-6-astra",
        )
    )

    assert result["method"] == "external-bim-plan/1"
    assert result["parameters"]["sourceLabel"] == "openai:gpt-6-astra"
    assert len(result["levels"]) == 1
    assert len(result["floors"]) == 1
    assert len(result["walls"]) == 1


def test_astra_provider_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(PlanError) as error:
        request_astra_plan({"scanId": "test"})
    assert error.value.code == ErrorCode.AI_PROVIDER_FAILED


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
