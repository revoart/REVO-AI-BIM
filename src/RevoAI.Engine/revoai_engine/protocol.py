"""Wire protocol shared with the C# add-in.

The wire format is newline-delimited JSON-RPC 2.0 with camelCase field names.
It is deliberately small and versioned: the add-in and engine must agree on the
major version before any processing request is accepted.
"""

from __future__ import annotations

import re
from enum import IntEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

PROTOCOL_VERSION = "1.0"

METHOD_INITIALIZE = "initialize"
METHOD_PING = "ping"
METHOD_SHUTDOWN = "shutdown"
METHOD_POINTCLOUD_IMPORT = "pointcloud.import"
METHOD_POINTCLOUD_INFO = "pointcloud.info"
METHOD_POINTCLOUD_QUERY = "pointcloud.query"
METHOD_SEGMENTATION_RUN = "segmentation.run"
METHOD_SEGMENTATION_INFO = "segmentation.info"
METHOD_RECONSTRUCTION_PLAN = "reconstruction.plan"

CAPABILITIES = (
    METHOD_INITIALIZE,
    METHOD_PING,
    METHOD_SHUTDOWN,
    METHOD_POINTCLOUD_IMPORT,
    METHOD_POINTCLOUD_INFO,
    METHOD_POINTCLOUD_QUERY,
    METHOD_SEGMENTATION_RUN,
    METHOD_SEGMENTATION_INFO,
    METHOD_RECONSTRUCTION_PLAN,
)


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

    FILE_NOT_FOUND = -32020
    UNSUPPORTED_FORMAT = -32021
    INVALID_POINT_CLOUD = -32022
    PROCESSING_FAILED = -32023
    STORE_NOT_FOUND = -32024
    INVALID_UNIT = -32025
    ANALYSIS_NOT_FOUND = -32026
    PLAN_INVALID = -32027
    AI_PROVIDER_FAILED = -32028
    SUBSCRIPTION_REQUIRED = -32029
    SUBSCRIPTION_QUOTA_EXCEEDED = -32030


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


class Bounds3(CamelModel):
    min: list[float]
    max: list[float]

    @field_validator("min", "max")
    @classmethod
    def _three_components(cls, value: list[float]) -> list[float]:
        if len(value) != 3:
            raise ValueError("Bounds must contain exactly three components.")
        return value


class PointCounts(CamelModel):
    original: int
    valid: int
    after_outlier_removal: int
    after_downsampling: int
    stored: int


class PointCloudImportParams(CamelModel):
    path: str = Field(min_length=1)
    format: str | None = None
    unit: str = "auto"
    output_directory: str = Field(min_length=1)
    scan_id: str | None = None
    chunk_size_meters: float = 25.0
    voxel_size_meters: float | None = None
    remove_outliers: bool = False
    outlier_neighbors: int = 20
    outlier_std_ratio: float = 2.0
    overwrite: bool = False

    @field_validator("format")
    @classmethod
    def _normalise_format(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().lower().lstrip(".")
        return cleaned or None

    @field_validator("unit")
    @classmethod
    def _normalise_unit(cls, value: str) -> str:
        cleaned = value.strip().lower()
        allowed = {
            "auto",
            "millimeters",
            "centimeters",
            "meters",
            "inches",
            "feet",
            "ussurveyfeet",
        }
        if cleaned not in allowed:
            raise ValueError(
                "unit must be auto, millimeters, centimeters, meters, inches, feet "
                "or usSurveyFeet"
            )
        return cleaned

    @field_validator("scan_id")
    @classmethod
    def _validate_scan_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", cleaned):
            raise ValueError(
                "scanId must be 1-64 characters using letters, digits, '.', '_' or '-'."
            )
        return cleaned

    @field_validator("chunk_size_meters")
    @classmethod
    def _validate_chunk_size(cls, value: float) -> float:
        if not 0.1 <= value <= 1000.0:
            raise ValueError("chunkSizeMeters must be between 0.1 and 1000 metres.")
        return value

    @field_validator("voxel_size_meters")
    @classmethod
    def _validate_voxel_size(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if not 0.0001 <= value <= 1000.0:
            raise ValueError("voxelSizeMeters must be between 0.0001 and 1000 metres.")
        return value

    @field_validator("outlier_neighbors")
    @classmethod
    def _validate_neighbors(cls, value: int) -> int:
        if not 3 <= value <= 200:
            raise ValueError("outlierNeighbors must be between 3 and 200.")
        return value

    @field_validator("outlier_std_ratio")
    @classmethod
    def _validate_std_ratio(cls, value: float) -> float:
        if not 0.1 <= value <= 10.0:
            raise ValueError("outlierStdRatio must be between 0.1 and 10.")
        return value


class PointCloudImportResult(CamelModel):
    scan_id: str
    store_path: str
    source_path: str
    format: str
    unit: str
    unit_source: str
    point_count: PointCounts
    bounds: Bounds3
    source_bounds: Bounds3
    chunk_count: int
    attributes: list[str]
    warnings: list[str]
    elapsed_ms: float
    source_sha256: str
    engine_version: str


class PointCloudInfoParams(CamelModel):
    store_path: str = Field(min_length=1)


class PointCloudInfoResult(CamelModel):
    scan_id: str
    store_path: str
    source_path: str
    format: str
    unit: str
    unit_source: str
    point_count: PointCounts
    bounds: Bounds3
    source_bounds: Bounds3
    chunk_count: int
    attributes: list[str]
    warnings: list[str]
    created_at: str
    engine_version: str


class PointCloudQueryParams(CamelModel):
    store_path: str = Field(min_length=1)
    bounds: Bounds3 | None = None
    center: list[float] | None = None
    radius: float | None = None
    max_points: int = 10_000
    include_colors: bool = False
    include_intensity: bool = False

    @field_validator("center")
    @classmethod
    def _center_is_three(cls, value: list[float] | None) -> list[float] | None:
        if value is not None and len(value) != 3:
            raise ValueError("center must contain exactly three components.")
        return value

    @field_validator("radius")
    @classmethod
    def _positive_radius(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("radius must be greater than zero.")
        return value

    @field_validator("max_points")
    @classmethod
    def _query_limit(cls, value: int) -> int:
        if not 1 <= value <= 200_000:
            raise ValueError("maxPoints must be between 1 and 200000.")
        return value

    @model_validator(mode="after")
    def _one_query_mode(self) -> "PointCloudQueryParams":
        has_radius = self.center is not None or self.radius is not None
        if self.bounds is not None and has_radius:
            raise ValueError("Specify either bounds or center+radius, not both.")
        if has_radius and (self.center is None or self.radius is None):
            raise ValueError("center and radius must be supplied together.")
        return self


class PointCloudQueryResult(CamelModel):
    positions: list[list[float]]
    count: int
    returned: int
    truncated: bool
    colors: list[list[int]] | None = None
    intensity: list[float] | None = None


class SegmentationRunParams(CamelModel):
    store_path: str = Field(min_length=1)
    voxel_size_meters: float = 0.05
    max_points: int = 200_000
    plane_distance_meters: float = 0.03
    min_plane_points: int = 300
    max_planes: int = 40
    confidence_threshold: float = 0.75

    @field_validator("voxel_size_meters")
    @classmethod
    def _validate_voxel_size(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("voxelSizeMeters must be between 0 and 1 metre.")
        return value

    @field_validator("max_points")
    @classmethod
    def _validate_max_points(cls, value: int) -> int:
        if not 1_000 <= value <= 1_000_000:
            raise ValueError("maxPoints must be between 1000 and 1000000.")
        return value

    @field_validator("plane_distance_meters")
    @classmethod
    def _validate_plane_distance(cls, value: float) -> float:
        if not 0.001 <= value <= 0.5:
            raise ValueError("planeDistanceMeters must be between 0.001 and 0.5 m.")
        return value

    @field_validator("min_plane_points")
    @classmethod
    def _validate_min_plane_points(cls, value: int) -> int:
        if not 10 <= value <= 100_000:
            raise ValueError("minPlanePoints must be between 10 and 100000.")
        return value

    @field_validator("max_planes")
    @classmethod
    def _validate_max_planes(cls, value: int) -> int:
        if not 1 <= value <= 200:
            raise ValueError("maxPlanes must be between 1 and 200.")
        return value

    @field_validator("confidence_threshold")
    @classmethod
    def _validate_confidence_threshold(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("confidenceThreshold must be between 0 and 1.")
        return value


class SegmentationInfoParams(CamelModel):
    store_path: str = Field(min_length=1)


class PlaneModel(CamelModel):
    normal: list[float]
    offset: float

    @field_validator("normal")
    @classmethod
    def _normal_is_three(cls, value: list[float]) -> list[float]:
        if len(value) != 3:
            raise ValueError("Plane normal must contain exactly three components.")
        return value


class SegmentationSignals(CamelModel):
    planarity: float
    density_per_square_meter: float
    coverage: float
    size: float
    fit_error_meters: float
    inlier_ratio: float


class SegmentationElement(CamelModel):
    id: str
    kind: str
    point_count: int
    confidence: float
    area_m2: float
    centroid: list[float]
    bounds: Bounds3
    boundary: list[list[float]] = Field(default_factory=list)
    plane: PlaneModel
    signals: SegmentationSignals

    @field_validator("centroid")
    @classmethod
    def _centroid_is_three(cls, value: list[float]) -> list[float]:
        if len(value) != 3:
            raise ValueError("Centroid must contain exactly three components.")
        return value


class SegmentationSummary(CamelModel):
    source_points: int
    analyzed_points: int
    segments: int
    by_kind: dict[str, int]
    mean_confidence: float
    high_confidence_segments: int
    assigned_points: int
    coverage: float


class SegmentationResult(CamelModel):
    scan_id: str
    store_path: str
    method: str
    method_note: str
    parameters: dict[str, Any]
    summary: SegmentationSummary
    elements: list[SegmentationElement]
    warnings: list[str]
    result_path: str
    created_at: str
    engine_version: str
    elapsed_ms: float


class ReconstructionPlanParams(CamelModel):
    store_path: str = Field(min_length=1)
    provider: Literal[
        "geometric", "external", "astra", "astra_subscription"
    ] = "geometric"
    external_plan_path: str | None = None
    astra_model: str = "gpt-6-astra"
    confidence_threshold: float = 0.75
    fallback_wall_height_meters: float = 2.7
    level_tolerance_meters: float = 0.25
    max_elements: int = 200

    @field_validator("confidence_threshold")
    @classmethod
    def _confidence_range(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("confidenceThreshold must be between 0 and 1.")
        return value

    @field_validator("fallback_wall_height_meters")
    @classmethod
    def _wall_height_range(cls, value: float) -> float:
        if not 0.5 <= value <= 10.0:
            raise ValueError("fallbackWallHeightMeters must be between 0.5 and 10 m.")
        return value

    @field_validator("level_tolerance_meters")
    @classmethod
    def _level_tolerance_range(cls, value: float) -> float:
        if not 0.01 <= value <= 2.0:
            raise ValueError("levelToleranceMeters must be between 0.01 and 2 m.")
        return value

    @field_validator("max_elements")
    @classmethod
    def _max_elements_range(cls, value: int) -> int:
        if not 1 <= value <= 1000:
            raise ValueError("maxElements must be between 1 and 1000.")
        return value


class PlanLevel(CamelModel):
    id: str
    name: str
    elevation_meters: float


class PlanFloor(CamelModel):
    id: str
    source_segment_id: str
    level_id: str
    boundary: list[list[float]]
    area_m2: float
    confidence: float


class PlanWall(CamelModel):
    id: str
    source_segment_id: str
    level_id: str
    start: list[float]
    end: list[float]
    height_meters: float
    height_source: str
    confidence: float

    @field_validator("start", "end")
    @classmethod
    def _wall_point_is_three(cls, value: list[float]) -> list[float]:
        if len(value) != 3:
            raise ValueError("Wall endpoints must contain three components.")
        return value


class ReconstructionPlanResult(CamelModel):
    scan_id: str
    store_path: str
    method: str
    parameters: dict[str, Any]
    levels: list[PlanLevel]
    floors: list[PlanFloor]
    walls: list[PlanWall]
    warnings: list[str]
    result_path: str
    created_at: str
    engine_version: str
    elapsed_ms: float


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
