"""Error model for the local knowledge engine.

The knowledge store is local-first. Failures are explicit and never silently
degrade to fabricated knowledge.
"""

from __future__ import annotations

from ..protocol import ErrorCode


class KnowledgeError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        data: str | None = None,
        remedy: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data
        self.remedy = remedy


def store_failed(message: str, *, data: str | None = None) -> KnowledgeError:
    return KnowledgeError(
        ErrorCode.KNOWLEDGE_STORE_FAILED,
        message,
        data=data,
        remedy="Check the local knowledge folder and file permissions.",
    )


def invalid(message: str, *, data: str | None = None) -> KnowledgeError:
    return KnowledgeError(
        ErrorCode.KNOWLEDGE_INVALID,
        message,
        data=data,
        remedy="Correct the request and retry.",
    )


def not_found(message: str) -> KnowledgeError:
    return KnowledgeError(
        ErrorCode.KNOWLEDGE_NOT_FOUND,
        message,
        remedy="Refresh the knowledge library and choose an existing item.",
    )


def io_failed(message: str, *, data: str | None = None) -> KnowledgeError:
    return KnowledgeError(
        ErrorCode.KNOWLEDGE_IO_FAILED,
        message,
        data=data,
        remedy="Check the path, available disk space and permissions.",
    )
