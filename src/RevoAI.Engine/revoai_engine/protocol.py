"""Wire protocol shared with the C# add-in.

The wire format is newline-delimited JSON-RPC 2.0 with camelCase field names.
It is deliberately small and versioned: the add-in and engine must agree on the
major version before any processing request is accepted.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

PROTOCOL_VERSION = "1.0"

METHOD_INITIALIZE = "initialize"
METHOD_PING = "ping"
METHOD_SHUTDOWN = "shutdown"

CAPABILITIES = (METHOD_INITIALIZE, METHOD_PING, METHOD_SHUTDOWN)


class ErrorCode(IntEnum):
    """JSON-RPC standard codes plus Revo AI BIM specific codes."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    PROTOCOL_VERSION_MISMATCH = -32010
    NOT_INITIALIZED = -32011
    ENGINE_UNAVAILABLE = -32012
    OPERATION_CANCELLED = -32013


class RpcError(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    code: int
    message: str
    data: str | None = None
    remedy: str | None = None


class RpcRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    json_rpc: Literal["2.0"] = Field(default="2.0", alias="jsonRpc")
    id: str
    method: str
    params: dict[str, Any] | None = None


class RpcResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    json_rpc: Literal["2.0"] = Field(default="2.0", alias="jsonRpc")
    id: str | None = None
    result: dict[str, Any] | None = None
    error: RpcError | None = None

    def to_wire(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore",
    )


class InitializeParams(CamelModel):
    client_name: str
    client_version: str
    protocol_version: str
    log_directory: str | None = None


class InitializeResult(CamelModel):
    server_version: str
    protocol_version: str
    python_version: str
    platform: str
    capabilities: list[str]


class PingParams(CamelModel):
    message: str | None = None


class PingResult(CamelModel):
    message: str
    server_time_utc: str
    engine_version: str
    python_version: str


class ShutdownResult(CamelModel):
    ok: bool


def is_compatible(version: str | None) -> bool:
    """Return True when ``version`` has the same major component as ours."""
    if not version:
        return False
    try:
        major = int(str(version).split(".", 1)[0])
    except (TypeError, ValueError):
        return False
    return major == int(PROTOCOL_VERSION.split(".", 1)[0])


def error_response(
    request_id: str | None,
    code: int,
    message: str,
    *,
    data: str | None = None,
    remedy: str | None = None,
) -> RpcResponse:
    return RpcResponse(
        id=request_id,
        error=RpcError(code=int(code), message=message, data=data, remedy=remedy),
    )
