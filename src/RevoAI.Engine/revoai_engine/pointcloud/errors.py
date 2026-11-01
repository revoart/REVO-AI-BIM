"""Point cloud domain errors mapped onto the JSON-RPC error contract."""

from __future__ import annotations

from ..protocol import ErrorCode


class PointCloudError(Exception):
    """A user-actionable point cloud failure.

    The service layer converts these into JSON-RPC errors with a remedy instead
    of leaking a Python traceback to Revit.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        remedy: str | None = None,
        data: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.remedy = remedy
        self.data = data


def file_not_found(path: str) -> PointCloudError:
    return PointCloudError(
        ErrorCode.FILE_NOT_FOUND,
        f"Point cloud file does not exist: '{path}'.",
        remedy="Check the path and try again.",
    )


def unsupported_format(path: str, detail: str | None = None) -> PointCloudError:
    message = (
        f"Unsupported point cloud format for '{path}'. "
        "Supported formats: E57, LAS, LAZ, PLY, XYZ and TXT."
    )
    return PointCloudError(
        ErrorCode.UNSUPPORTED_FORMAT,
        message,
        data=detail,
        remedy="Export the scan to E57, LAS/LAZ, PLY or XYZ and import it again.",
    )


def invalid_cloud(message: str, *, data: str | None = None) -> PointCloudError:
    return PointCloudError(
        ErrorCode.INVALID_POINT_CLOUD,
        message,
        data=data,
        remedy="Check that the file contains finite XYZ coordinates and try again.",
    )


def processing_failed(message: str, *, data: str | None = None) -> PointCloudError:
    return PointCloudError(
        ErrorCode.PROCESSING_FAILED,
        message,
        data=data,
        remedy="Reduce the point count or disable preprocessing, then retry.",
    )


def store_not_found(path: str) -> PointCloudError:
    return PointCloudError(
        ErrorCode.STORE_NOT_FOUND,
        f"Point cloud store does not exist or is not readable: '{path}'.",
        remedy="Import the scan again to rebuild the local store.",
    )


def invalid_unit(value: str) -> PointCloudError:
    return PointCloudError(
        ErrorCode.INVALID_UNIT,
        f"Unsupported unit '{value}'.",
        remedy=(
            "Use auto, millimeters, centimeters, meters, inches, feet or "
            "usSurveyFeet."
        ),
    )
