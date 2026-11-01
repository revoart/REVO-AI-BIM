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


def provider_failed(message: str, *, data: str | None = None) -> PlanError:
    return PlanError(
        ErrorCode.AI_PROVIDER_FAILED,
        message,
        data=data,
        remedy=(
            "Set OPENAI_API_KEY for the user running Revit and verify network access "
            "to the OpenAI API."
        ),
    )


def subscription_required(message: str, *, data: str | None = None) -> PlanError:
    return PlanError(
        ErrorCode.SUBSCRIPTION_REQUIRED,
        message,
        data=data,
        remedy="Sign in to the Revo AI BIM subscription and restart Revit.",
    )


def subscription_quota_exceeded(message: str, *, data: str | None = None) -> PlanError:
    return PlanError(
        ErrorCode.SUBSCRIPTION_QUOTA_EXCEEDED,
        message,
        data=data,
        remedy="Check the subscription usage limit or upgrade the plan.",
    )


def plan_invalid(message: str, *, data: str | None = None) -> PlanError:
    return PlanError(
        ErrorCode.PLAN_INVALID,
        message,
        data=data,
        remedy=(
            "Use the documented external BIM plan schema: metres, scan coordinates, "
            "known level ids, finite floor polygons and non-zero wall lines."
        ),
    )
