from __future__ import annotations

import json

import pytest

from revoai_engine.protocol import (
    PROTOCOL_VERSION,
    InitializeParams,
    RpcError,
    RpcRequest,
    RpcResponse,
    error_response,
    is_compatible,
)


def test_protocol_version_is_one_zero() -> None:
    assert PROTOCOL_VERSION == "1.0"


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("1.0", True),
        ("1.9", True),
        ("2.0", False),
        ("0.9", False),
        ("", False),
        (None, False),
        ("not-a-version", False),
    ],
)
def test_compatibility_uses_major_version(version: str | None, expected: bool) -> None:
    assert is_compatible(version) is expected


def test_request_accepts_camel_case_wire_format() -> None:
    request = RpcRequest.model_validate(
        {
            "jsonRpc": "2.0",
            "id": "1",
            "method": "initialize",
            "params": {
                "clientName": "RevoAI.Revit",
                "clientVersion": "0.1.0",
                "protocolVersion": "1.0",
            },
        }
    )

    params = InitializeParams.model_validate(request.params)
    assert params.client_name == "RevoAI.Revit"
    assert params.client_version == "0.1.0"


def test_result_is_serialized_with_camel_case_aliases() -> None:
    response = RpcResponse(
        id="1",
        result={"serverVersion": "0.1.0", "capabilities": ["ping"]},
    )

    wire = response.to_wire()
    assert wire["jsonRpc"] == "2.0"
    assert wire["result"]["serverVersion"] == "0.1.0"
    assert "error" not in wire


def test_error_response_omits_empty_fields() -> None:
    response = error_response("9", -32011, "not initialized")

    wire = response.to_wire()
    assert wire["error"] == {"code": -32011, "message": "not initialized"}
    assert wire["id"] == "9"


def test_rpc_error_supports_remedy() -> None:
    error = RpcError(code=-32010, message="mismatch", remedy="install matching versions")
    assert json.loads(error.model_dump_json(exclude_none=True))["remedy"] == "install matching versions"
