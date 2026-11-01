"""Reconstruction planning errors mapped onto the JSON-RPC contract."""

from __future__ import annotations

from ..protocol import ErrorCode


class PlanError(Exception):
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


def plan_failed(message: str, *, data: str | None = None) -> PlanError:
    return PlanError(
        ErrorCode.PROCESSING_FAILED,
        message,
        data=data,
        remedy="Rerun Scan Analysis with a lower confidence threshold or adjust the plan settings.",
    )
