from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from revoai_engine.protocol import ErrorCode, RpcRequest
from revoai_engine.service import EngineState, dispatch, handle_line

REPO_ROOT = Path(__file__).resolve().parents[2]


def make_request(method: str, params: dict | None = None, request_id: str = "1") -> RpcRequest:
    return RpcRequest(id=request_id, method=method, params=params)


def initialize_params() -> dict:
    return {
        "clientName": "pytest",
        "clientVersion": "0.1.0",
        "protocolVersion": "1.0",
    }


def test_ping_works_before_initialize() -> None:
    state = EngineState()
    response = dispatch(state, make_request("ping", {"message": "hi"}))

    assert response is not None
    assert response.error is None
    assert response.result["message"] == "hi"
    assert response.result["serverTimeUtc"].endswith("Z")


def test_processing_methods_require_initialize() -> None:
    state = EngineState()
    response = dispatch(state, make_request("detect.walls"))

    assert response is not None
    assert response.error is not None
    assert response.error.code == ErrorCode.NOT_INITIALIZED


def test_initialize_returns_honest_capabilities() -> None:
    state = EngineState()
    response = dispatch(state, make_request("initialize", initialize_params()))

    assert response is not None
    assert response.error is None
    assert state.initialized is True
    assert response.result["protocolVersion"] == "1.0"
    assert response.result["capabilities"] == [
        "initialize",
        "ping",
        "shutdown",
        "pointcloud.import",
        "pointcloud.info",
        "pointcloud.query",
        "segmentation.run",
        "segmentation.info",
    ]


def test_incompatible_protocol_is_rejected() -> None:
    state = EngineState()
    params = initialize_params() | {"protocolVersion": "2.0"}
    response = dispatch(state, make_request("initialize", params))

    assert response is not None
    assert response.error is not None
    assert response.error.code == ErrorCode.PROTOCOL_VERSION_MISMATCH
    assert response.error.remedy


def test_unknown_method_after_initialize() -> None:
    state = EngineState()
    dispatch(state, make_request("initialize", initialize_params()))
    response = dispatch(state, make_request("reconstruct.everything"))

    assert response is not None
    assert response.error is not None
    assert response.error.code == ErrorCode.METHOD_NOT_FOUND


def test_shutdown_sets_flag() -> None:
    state = EngineState()
    response = dispatch(state, make_request("shutdown"))

    assert response is not None
    assert response.result == {"ok": True}
    assert state.shutdown_requested is True


def test_invalid_json_returns_parse_error() -> None:
    state = EngineState()
    response = handle_line(state, "{not json")

    assert response is not None
    assert response.error is not None
    assert response.error.code == ErrorCode.PARSE_ERROR
    assert response.id is None


def test_invalid_request_shape_is_rejected() -> None:
    state = EngineState()
    response = handle_line(state, json.dumps({"id": "1"}))

    assert response is not None
    assert response.error is not None
    assert response.error.code == ErrorCode.INVALID_REQUEST


def test_service_process_round_trip() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [
            str(REPO_ROOT / "src" / "RevoAI.Engine"),
            str(REPO_ROOT / "src" / "RevoAI.Geometry"),
        ]
    )
    env["PYTHONUTF8"] = "1"

    requests = [
        {"jsonRpc": "2.0", "id": "1", "method": "initialize", "params": initialize_params()},
        {"jsonRpc": "2.0", "id": "2", "method": "ping", "params": {"message": "pong-test"}},
        {"jsonRpc": "2.0", "id": "3", "method": "shutdown"},
    ]
    payload = "".join(json.dumps(item) + "\n" for item in requests)

    completed = subprocess.run(
        [sys.executable, "-m", "revoai_engine.service"],
        input=payload,
        text=True,
        capture_output=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    assert len(lines) == 3

    responses = [json.loads(line) for line in lines]
    assert [item["id"] for item in responses] == ["1", "2", "3"]
    assert responses[0]["result"]["protocolVersion"] == "1.0"
    assert responses[1]["result"]["message"] == "pong-test"
    assert responses[2]["result"] == {"ok": True}
    assert "ready" in completed.stderr.lower()
