from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from revoai_engine.analysis.snapshots import generate_snapshots
from revoai_engine.analysis import run_segmentation
from revoai_engine.pointcloud import import_point_cloud
from revoai_engine.protocol import (
    ErrorCode,
    PointCloudImportParams,
    ReconstructionPlanParams,
    SegmentationRunParams,
)
from revoai_engine.reconstruction import create_plan
from revoai_engine.reconstruction.deepseek import request_ai_schedule
from revoai_engine.reconstruction import claude
from revoai_engine.reconstruction.claude import request_claude_schedule
from revoai_engine.reconstruction.errors import PlanError
from revoai_engine.reconstruction.schedule import normalize_schedule


def _import_room(tmp_path: Path) -> dict:
    source = tmp_path / "room.xyz"
    points = []
    for x in np.linspace(0.2, 3.8, 15):
        for y in np.linspace(0.2, 2.8, 12):
            points.append((x, y, 0.0))
            points.append((x, y, 2.7))
    for x in np.linspace(0.2, 3.8, 15):
        for z in np.linspace(0.2, 2.5, 10):
            points.append((x, 0.0, z))
            points.append((x, 3.0, z))
    for y in np.linspace(0.2, 2.8, 12):
        for z in np.linspace(0.2, 2.5, 10):
            points.append((0.0, y, z))
            points.append((4.0, y, z))
    np.savetxt(source, np.asarray(points), fmt="%.6f")
    return import_point_cloud(
        PointCloudImportParams(
            path=str(source),
            unit="meters",
            output_directory=str(tmp_path / "stores"),
            scan_id="ai-room",
            chunk_size_meters=5.0,
        )
    )


def test_snapshots_generate_plan_and_four_elevations(tmp_path: Path) -> None:
    imported = _import_room(tmp_path)
    snapshots = generate_snapshots(imported["storePath"], max_points=50_000, size=320)

    assert snapshots["method"] == "orthographic-depth/1"
    assert len(snapshots["views"]) == 5
    names = {view["name"] for view in snapshots["views"]}
    assert names == {"plan", "south", "north", "west", "east"}

    for view in snapshots["views"]:
        path = Path(view["path"])
        assert path.is_file()
        assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert view["width"] == 320
        assert view["height"] == 320
        assert view["metersPerPixel"] > 0
        assert view["rightAxis"] in {"X", "Y"}
        assert view["upAxis"] in {"Y", "Z"}

    assert (Path(snapshots["folder"]) / "snapshots.json").is_file()


def test_schedule_normalizes_walls_openings_and_roof() -> None:
    metadata = {
        "bounds": {"min": [0, 0, 0], "max": [5, 4, 3]},
        "units": {"source": "meters", "sourceOrigin": "explicit"},
    }
    payload = {
        "units": "m",
        "levels": [{"id": "L1", "name": "Level 1", "elevationMeters": 0.0}],
        "walls": [
            {
                "id": "W1",
                "levelId": "L1",
                "start": [0, 0, 0],
                "end": [4, 0, 0],
                "thicknessMeters": 0.2,
                "heightMeters": 2.7,
                "source": "MEASURED",
            }
        ],
        "floors": [
            {
                "id": "F1",
                "levelId": "L1",
                "boundary": [[0, 0, 0], [4, 0, 0], [4, 3, 0], [0, 3, 0]],
                "thicknessMeters": 0.2,
                "source": "MEASURED",
            }
        ],
        "openings": [
            {
                "id": "O1",
                "hostWallId": "W1",
                "kind": "window",
                "centerMeters": 2.0,
                "widthMeters": 1.2,
                "sillMeters": 0.9,
                "headMeters": 2.1,
                "source": "MEASURED",
            }
        ],
        "roofs": [
            {
                "id": "R1",
                "levelId": "L1",
                "boundary": [[0, 0, 2.7], [4, 0, 2.7], [4, 3, 2.7], [0, 3, 2.7]],
                "pitchDegrees": 0,
                "thicknessMeters": 0.2,
                "source": "ASSUMED",
            }
        ],
        "assumptions": ["Roof structure assumed."],
        "verify": ["R1"],
    }

    normalized = normalize_schedule(payload, store_metadata=metadata, source_label="test")

    assert normalized["report"]["buildable"] is True
    assert normalized["report"]["capabilities"]["openings"] is True
    assert normalized["report"]["capabilities"]["roofs"] is True
    assert normalized["openings"][0]["headMeters"] == 2.1
    assert normalized["roofs"][0]["id"] == "R1"
    assert normalized["floors"][0]["areaM2"] > 10


def test_schedule_rejects_opening_outside_host_wall() -> None:
    metadata = {
        "bounds": {"min": [0, 0, 0], "max": [5, 4, 3]},
        "units": {"source": "meters", "sourceOrigin": "explicit"},
    }
    payload = {
        "levels": [{"id": "L1", "elevationMeters": 0.0}],
        "walls": [
            {
                "id": "W1",
                "levelId": "L1",
                "start": [0, 0, 0],
                "end": [4, 0, 0],
                "heightMeters": 2.7,
            }
        ],
        "floors": [
            {
                "id": "F1",
                "levelId": "L1",
                "boundary": [[0, 0, 0], [4, 0, 0], [4, 3, 0], [0, 3, 0]],
            }
        ],
        "openings": [
            {
                "id": "O1",
                "hostWallId": "W1",
                "kind": "door",
                "centerMeters": 9.0,
                "widthMeters": 0.9,
                "sillMeters": 0.0,
                "headMeters": 2.1,
            }
        ],
    }

    with pytest.raises(PlanError):
        normalize_schedule(payload, store_metadata=metadata, source_label="test")


def test_ai_provider_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DEEPSEEK_API_KEY", "REVOAI_AI_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(PlanError) as error:
        request_ai_schedule({"scanId": "test"}, {"views": []})
    assert error.value.code == ErrorCode.AI_PROVIDER_FAILED


def test_claude_provider_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ANTHROPIC_API_KEY", "REVOAI_ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(PlanError) as error:
        request_claude_schedule({"scanId": "test"}, {"views": []})
    assert error.value.code == ErrorCode.AI_PROVIDER_FAILED


def test_claude_provider_parses_schedule_json(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "units": "m",
        "levels": [{"id": "L1", "name": "Level 1", "elevationMeters": 0}],
        "walls": [],
        "floors": [],
    }
    monkeypatch.setattr(
        "revoai_engine.reconstruction.claude._post",
        lambda base, key, body, timeout: json.dumps(
            {"content": [{"type": "text", "text": json.dumps(payload)}]}
        ),
    )

    result = request_claude_schedule(
        {"scanId": "test"},
        {"views": []},
        api_key_override="test-key",
        model="claude-test",
    )

    assert result["levels"][0]["id"] == "L1"
    assert result["_provider"] == "claude"
    assert result["_model"] == "claude-test"


def test_ai_plan_prefers_claude_when_key_is_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    imported = _import_room(tmp_path)
    run_segmentation(
        SegmentationRunParams(
            store_path=imported["storePath"],
            voxel_size_meters=0.0,
            max_points=20_000,
            plane_distance_meters=0.01,
            min_plane_points=100,
            max_planes=20,
        )
    )

    payload = {
        "units": "m",
        "levels": [{"id": "L1", "name": "Level 1", "elevationMeters": 0.0}],
        "walls": [
            {
                "id": "W1",
                "levelId": "L1",
                "start": [0, 0, 0],
                "end": [4, 0, 0],
                "thicknessMeters": 0.2,
                "heightMeters": 2.7,
                "source": "MEASURED",
            }
        ],
        "floors": [
            {
                "id": "F1",
                "levelId": "L1",
                "boundary": [[0, 0, 0], [4, 0, 0], [4, 3, 0], [0, 3, 0]],
                "thicknessMeters": 0.2,
                "source": "MEASURED",
            }
        ],
    }

    monkeypatch.setattr(
        "revoai_engine.reconstruction.plan.claude.is_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        "revoai_engine.reconstruction.plan.claude.request_claude_schedule",
        lambda context, snapshots: payload,
    )
    monkeypatch.setattr(
        "revoai_engine.reconstruction.plan.claude.selected_model",
        lambda model=None: "claude-sonnet-5-5",
    )

    plan = create_plan(
        ReconstructionPlanParams(store_path=imported["storePath"], provider="ai")
    )

    assert plan["parameters"]["provider"] == "claude"
    assert plan["parameters"]["model"] == "claude-sonnet-5-5"
    assert plan["report"]["source"] == "claude:claude-sonnet-5-5"


def test_ai_plan_branch_uses_validated_schedule(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    imported = _import_room(tmp_path)
    run_segmentation(
        SegmentationRunParams(
            store_path=imported["storePath"],
            voxel_size_meters=0.0,
            max_points=20_000,
            plane_distance_meters=0.01,
            min_plane_points=100,
            max_planes=20,
        )
    )

    payload = {
        "units": "m",
        "levels": [{"id": "L1", "name": "Level 1", "elevationMeters": 0.0}],
        "walls": [
            {
                "id": "W1",
                "levelId": "L1",
                "start": [0, 0, 0],
                "end": [4, 0, 0],
                "thicknessMeters": 0.2,
                "heightMeters": 2.7,
                "source": "MEASURED",
            }
        ],
        "floors": [
            {
                "id": "F1",
                "levelId": "L1",
                "boundary": [[0, 0, 0], [4, 0, 0], [4, 3, 0], [0, 3, 0]],
                "thicknessMeters": 0.2,
                "source": "MEASURED",
            }
        ],
        "openings": [
            {
                "id": "O1",
                "hostWallId": "W1",
                "kind": "door",
                "centerMeters": 2.0,
                "widthMeters": 0.9,
                "sillMeters": 0.0,
                "headMeters": 2.1,
                "source": "MEASURED",
            }
        ],
        "roofs": [
            {
                "id": "R1",
                "levelId": "L1",
                "boundary": [[0, 0, 2.7], [4, 0, 2.7], [4, 3, 2.7], [0, 3, 2.7]],
                "pitchDegrees": 0,
                "thicknessMeters": 0.2,
                "source": "MEASURED",
            }
        ],
    }

    monkeypatch.setattr(
        "revoai_engine.reconstruction.plan.request_ai_schedule",
        lambda context, snapshots, model: payload,
    )

    plan = create_plan(
        ReconstructionPlanParams(
            store_path=imported["storePath"],
            provider="ai",
            astra_model="deepseek-go",
        )
    )

    assert plan["method"] == "ai-schedule/1"
    assert plan["report"]["source"] == "deepseek:deepseek-go"
    assert plan["openings"][0]["kind"] == "door"
    assert plan["roofs"][0]["id"] == "R1"
    assert plan["report"]["snapshots"]["views"]
    assert len(plan["report"]["snapshots"]["views"]) == 5
