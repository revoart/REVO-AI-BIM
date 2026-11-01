"""Analysis domain errors mapped onto the JSON-RPC error contract."""

from __future__ import annotations

from ..protocol import ErrorCode


class AnalysisError(Exception):
    """A user-actionable Scan Analysis failure."""

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


def analysis_not_found(store_path: str) -> AnalysisError:
    return AnalysisError(
        ErrorCode.ANALYSIS_NOT_FOUND,
        f"No segmentation analysis exists for the scan store '{store_path}'.",
        remedy="Run Scan Analysis on this store before requesting its result.",
    )


def analysis_failed(message: str, *, data: str | None = None) -> AnalysisError:
    return AnalysisError(
        ErrorCode.PROCESSING_FAILED,
        message,
        data=data,
        remedy="Reduce the analysis point count or adjust the plane settings.",
    )
