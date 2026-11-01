"""Newline-delimited JSON-RPC service process.

The C# add-in starts this module as a child process and exchanges one JSON
object per line over stdin/stdout. Logs go to stderr (and optionally a file) so
stdout stays a clean protocol channel.
"""

from __future__ import annotations

import json
import logging
import os
import platform as platform_module
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from pydantic import ValidationError

from . import __version__
from .analysis import AnalysisError, load_segmentation, run_segmentation
from .pointcloud import PointCloudError, PointCloudStore, import_point_cloud
from .protocol import (
    CAPABILITIES,
    METHOD_INITIALIZE,
    METHOD_PING,
    METHOD_POINTCLOUD_IMPORT,
    METHOD_POINTCLOUD_INFO,
    METHOD_POINTCLOUD_QUERY,
    METHOD_SEGMENTATION_INFO,
    METHOD_SEGMENTATION_RUN,
    METHOD_SHUTDOWN,
    PROTOCOL_VERSION,
    ErrorCode,
    InitializeParams,
    InitializeResult,
    PingParams,
    PingResult,
    PointCloudImportParams,
    PointCloudImportResult,
    PointCloudInfoParams,
    PointCloudInfoResult,
    PointCloudQueryParams,
    PointCloudQueryResult,
    RpcRequest,
    RpcResponse,
    SegmentationInfoParams,
    SegmentationResult,
    SegmentationRunParams,
    ShutdownResult,
    error_response,
    is_compatible,
)

LOG = logging.getLogger("revoai.engine")
_FILE_HANDLER: logging.Handler | None = None


class EngineState:
    """Per-process state. One engine process serves exactly one add-in session."""

    def __init__(self) -> None:
        self.initialized = False
        self.shutdown_requested = False
        self.client_name: str | None = None
        self.client_version: str | None = None
        self.log_directory: str | None = None

    def initialize(self, params: InitializeParams) -> InitializeResult:
        self.initialized = True
        self.client_name = params.client_name
        self.client_version = params.client_version
        self.log_directory = params.log_directory

        if params.log_directory:
            _configure_file_logging(params.log_directory)

        LOG.info(
            "Initialized by %s %s (protocol %s)",
            params.client_name,
            params.client_version,
            params.protocol_version,
        )

        return InitializeResult(
            server_version=__version__,
            protocol_version=PROTOCOL_VERSION,
            python_version=platform_module.python_version(),
            platform=platform_module.platform(),
            capabilities=list(CAPABILITIES),
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _configure_file_logging(directory: str) -> None:
    global _FILE_HANDLER

    if _FILE_HANDLER is not None:
        return

    try:
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        log_file = path / f"engine-{datetime.now(timezone.utc):%Y%m%d}.log"

        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        logging.getLogger().addHandler(handler)
        _FILE_HANDLER = handler
        LOG.info("Engine file logging enabled: %s", log_file)
    except OSError as exc:  # pragma: no cover - depends on machine permissions
        LOG.warning("Could not open engine log file in %s: %s", directory, exc)


def configure_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return

    level = logging.DEBUG if os.environ.get("REVOAI_LOG_LEVEL", "").upper() == "DEBUG" else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(level)


def dispatch(state: EngineState, request: RpcRequest) -> RpcResponse | None:
    """Handle one validated request. Pure enough to unit test directly."""

    if request.method == METHOD_INITIALIZE:
        try:
            params = InitializeParams.model_validate(request.params or {})
        except ValidationError as exc:
            return error_response(
                request.id,
                ErrorCode.INVALID_PARAMS,
                "Invalid initialize parameters.",
                data=str(exc),
            )

        if not is_compatible(params.protocol_version):
            return error_response(
                request.id,
                ErrorCode.PROTOCOL_VERSION_MISMATCH,
                f"Engine protocol {PROTOCOL_VERSION} does not accept client protocol "
                f"{params.protocol_version}.",
                remedy="Install matching Revo AI BIM add-in and engine versions.",
            )

        result = state.initialize(params)
        return RpcResponse(id=request.id, result=result.model_dump(by_alias=True))

    if request.method == METHOD_PING:
        try:
            params = PingParams.model_validate(request.params or {})
        except ValidationError as exc:
            return error_response(
                request.id,
                ErrorCode.INVALID_PARAMS,
                "Invalid ping parameters.",
                data=str(exc),
            )

        result = PingResult(
            message=params.message or "pong",
            server_time_utc=_utc_now(),
            engine_version=__version__,
            python_version=platform_module.python_version(),
        )
        return RpcResponse(id=request.id, result=result.model_dump(by_alias=True))

    if request.method == METHOD_SHUTDOWN:
        state.shutdown_requested = True
        result = ShutdownResult(ok=True)
        LOG.info("Shutdown requested.")
        return RpcResponse(id=request.id, result=result.model_dump(by_alias=True))

    if not state.initialized:
        return error_response(
            request.id,
            ErrorCode.NOT_INITIALIZED,
            "The engine has not been initialized.",
            remedy="Call 'initialize' before any processing request.",
        )

    if request.method == METHOD_POINTCLOUD_IMPORT:
        try:
            params = PointCloudImportParams.model_validate(request.params or {})
        except ValidationError as exc:
            return error_response(
                request.id,
                ErrorCode.INVALID_PARAMS,
                "Invalid point cloud import parameters.",
                data=str(exc),
            )

        try:
            result = import_point_cloud(params)
        except PointCloudError as exc:
            return error_response(
                request.id,
                exc.code,
                exc.message,
                data=exc.data,
                remedy=exc.remedy,
            )

        LOG.info(
            "Imported %s (%s) as %s: %s points in %s chunk(s) at %s",
            result["sourcePath"],
            result["format"],
            result["scanId"],
            result["pointCount"]["stored"],
            result["chunkCount"],
            result["storePath"],
        )
        validated = PointCloudImportResult.model_validate(result)
        return RpcResponse(
            id=request.id,
            result=validated.model_dump(by_alias=True),
        )

    if request.method == METHOD_POINTCLOUD_INFO:
        try:
            params = PointCloudInfoParams.model_validate(request.params or {})
        except ValidationError as exc:
            return error_response(
                request.id,
                ErrorCode.INVALID_PARAMS,
                "Invalid point cloud info parameters.",
                data=str(exc),
            )

        try:
            store = PointCloudStore.open(params.store_path)
        except PointCloudError as exc:
            return error_response(
                request.id,
                exc.code,
                exc.message,
                data=exc.data,
                remedy=exc.remedy,
            )

        metadata = store.info()
        units = metadata.get("units", {})
        result = PointCloudInfoResult(
            scan_id=metadata["scanId"],
            store_path=str(store.path),
            source_path=metadata["source"]["path"],
            format=metadata["source"]["format"],
            unit=units.get("source", "meters"),
            unit_source=units.get("sourceOrigin", "assumed"),
            point_count=metadata["pointCount"],
            bounds=metadata["bounds"],
            source_bounds=metadata["sourceBounds"],
            chunk_count=int(metadata["storage"]["chunkCount"]),
            attributes=list(metadata.get("attributes", [])),
            warnings=list(metadata.get("warnings", [])),
            created_at=metadata["createdAt"],
            engine_version=metadata.get("engineVersion", __version__),
        )
        return RpcResponse(
            id=request.id,
            result=result.model_dump(by_alias=True),
        )

    if request.method == METHOD_POINTCLOUD_QUERY:
        try:
            params = PointCloudQueryParams.model_validate(request.params or {})
        except ValidationError as exc:
            return error_response(
                request.id,
                ErrorCode.INVALID_PARAMS,
                "Invalid point cloud query parameters.",
                data=str(exc),
            )

        try:
            store = PointCloudStore.open(params.store_path)
            if params.bounds is not None:
                raw = store.query_bounds(
                    params.bounds.min,
                    params.bounds.max,
                    max_points=params.max_points,
                    include_colors=params.include_colors,
                    include_intensity=params.include_intensity,
                )
            elif params.center is not None and params.radius is not None:
                raw = store.query_radius(
                    params.center,
                    params.radius,
                    max_points=params.max_points,
                    include_colors=params.include_colors,
                    include_intensity=params.include_intensity,
                )
            else:
                raw = store.sample(
                    params.max_points,
                    include_colors=params.include_colors,
                    include_intensity=params.include_intensity,
                )
        except PointCloudError as exc:
            return error_response(
                request.id,
                exc.code,
                exc.message,
                data=exc.data,
                remedy=exc.remedy,
            )

        result = PointCloudQueryResult(
            positions=raw["positions"].tolist(),
            count=int(raw["count"]),
            returned=int(raw["returned"]),
            truncated=bool(raw["truncated"]),
            colors=(
                raw["colors"].astype(int).tolist()
                if raw["colors"] is not None
                else None
            ),
            intensity=(
                raw["intensity"].astype(float).tolist()
                if raw["intensity"] is not None
                else None
            ),
        )
        return RpcResponse(
            id=request.id,
            result=result.model_dump(by_alias=True, exclude_none=True),
        )

    if request.method == METHOD_SEGMENTATION_RUN:
        try:
            params = SegmentationRunParams.model_validate(request.params or {})
        except ValidationError as exc:
            return error_response(
                request.id,
                ErrorCode.INVALID_PARAMS,
                "Invalid segmentation parameters.",
                data=str(exc),
            )

        try:
            result = run_segmentation(params)
        except (PointCloudError, AnalysisError) as exc:
            return error_response(
                request.id,
                exc.code,
                exc.message,
                data=exc.data,
                remedy=exc.remedy,
            )

        LOG.info(
            "Segmented %s: %s segment(s), mean confidence %.3f, %s",
            result["scanId"],
            result["summary"]["segments"],
            result["summary"]["meanConfidence"],
            result["resultPath"],
        )
        validated = SegmentationResult.model_validate(result)
        return RpcResponse(
            id=request.id,
            result=validated.model_dump(by_alias=True),
        )

    if request.method == METHOD_SEGMENTATION_INFO:
        try:
            params = SegmentationInfoParams.model_validate(request.params or {})
        except ValidationError as exc:
            return error_response(
                request.id,
                ErrorCode.INVALID_PARAMS,
                "Invalid segmentation info parameters.",
                data=str(exc),
            )

        try:
            result = load_segmentation(params.store_path)
        except (PointCloudError, AnalysisError) as exc:
            return error_response(
                request.id,
                exc.code,
                exc.message,
                data=exc.data,
                remedy=exc.remedy,
            )

        validated = SegmentationResult.model_validate(result)
        return RpcResponse(
            id=request.id,
            result=validated.model_dump(by_alias=True),
        )

    return error_response(
        request.id,
        ErrorCode.METHOD_NOT_FOUND,
        f"Unknown method '{request.method}'.",
        remedy="This capability is not implemented in this engine version.",
    )


def handle_line(state: EngineState, line: str) -> RpcResponse | None:
    """Parse and dispatch a single line, converting every failure to a response."""

    try:
        payload: Any = json.loads(line)
    except json.JSONDecodeError as exc:
        LOG.warning("Invalid JSON received: %s", exc)
        return error_response(None, ErrorCode.PARSE_ERROR, "Invalid JSON payload.", data=str(exc))

    if not isinstance(payload, dict):
        return error_response(None, ErrorCode.INVALID_REQUEST, "Request must be a JSON object.")

    try:
        request = RpcRequest.model_validate(payload)
    except ValidationError as exc:
        return error_response(None, ErrorCode.INVALID_REQUEST, "Invalid JSON-RPC request.", data=str(exc))

    try:
        return dispatch(state, request)
    except Exception as exc:  # noqa: BLE001 - a protocol server must not die on one request
        LOG.exception("Unhandled error while processing '%s'", request.method)
        return error_response(
            request.id,
            ErrorCode.INTERNAL_ERROR,
            "The engine failed while processing the request.",
            data=str(exc),
        )


def serve(stdin: TextIO | None = None, stdout: TextIO | None = None) -> int:
    configure_logging()

    input_stream = stdin if stdin is not None else sys.stdin
    output_stream = stdout if stdout is not None else sys.stdout
    state = EngineState()

    LOG.info(
        "Revo AI BIM engine %s ready (protocol %s, Python %s).",
        __version__,
        PROTOCOL_VERSION,
        platform_module.python_version(),
    )

    for raw_line in input_stream:
        line = raw_line.strip()
        if not line:
            continue

        response = handle_line(state, line)
        if response is not None:
            output_stream.write(json.dumps(response.to_wire(), ensure_ascii=False) + "\n")
            output_stream.flush()

        if state.shutdown_requested:
            break

    LOG.info("Engine loop finished.")
    return 0


def main() -> int:
    try:
        return serve()
    except KeyboardInterrupt:  # pragma: no cover
        LOG.info("Engine interrupted.")
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
