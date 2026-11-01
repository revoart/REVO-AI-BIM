"""RPC handling for the local knowledge engine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..protocol import (
    METHOD_KNOWLEDGE_BACKUP,
    METHOD_KNOWLEDGE_BENCHMARK_ADD,
    METHOD_KNOWLEDGE_CONTEXT,
    METHOD_KNOWLEDGE_DECISION_ADD,
    METHOD_KNOWLEDGE_DOCUMENT_IMPORT,
    METHOD_KNOWLEDGE_EXPORT,
    METHOD_KNOWLEDGE_GET,
    METHOD_KNOWLEDGE_PROJECT_IMPORT,
    METHOD_KNOWLEDGE_REVIEW,
    METHOD_KNOWLEDGE_SEARCH,
    METHOD_KNOWLEDGE_SOURCE_LIST,
    METHOD_KNOWLEDGE_STATS,
    METHOD_KNOWLEDGE_TECHNIQUE_ADD,
    METHOD_KNOWLEDGE_TRANSCRIPT_IMPORT,
    METHOD_KNOWLEDGE_UPDATE,
    METHOD_KNOWLEDGE_DELETE,
)
from .errors import invalid, not_found
from .models import (
    KnowledgeBackupParams,
    KnowledgeBackupResult,
    KnowledgeBenchmarkAddParams,
    KnowledgeBenchmarkAddResult,
    KnowledgeContextParams,
    KnowledgeContextResult,
    KnowledgeDecisionAddParams,
    KnowledgeDecisionAddResult,
    KnowledgeDeleteParams,
    KnowledgeDeleteResult,
    KnowledgeDocumentImportParams,
    KnowledgeExportParams,
    KnowledgeExportResult,
    KnowledgeGetParams,
    KnowledgeGetResult,
    KnowledgeImportResult,
    KnowledgeProjectImportParams,
    KnowledgeProjectImportResult,
    KnowledgeReviewParams,
    KnowledgeReviewResult,
    KnowledgeSearchParams,
    KnowledgeSearchResult,
    KnowledgeSourceListParams,
    KnowledgeSourceListResult,
    KnowledgeStatsResult,
    KnowledgeTechniqueAddParams,
    KnowledgeTechniqueAddResult,
    KnowledgeTranscriptImportParams,
    KnowledgeUpdateParams,
    KnowledgeUpdateResult,
)
from .store import KnowledgeStore

KNOWLEDGE_METHODS = {
    METHOD_KNOWLEDGE_SOURCE_LIST,
    METHOD_KNOWLEDGE_TRANSCRIPT_IMPORT,
    METHOD_KNOWLEDGE_DOCUMENT_IMPORT,
    METHOD_KNOWLEDGE_TECHNIQUE_ADD,
    METHOD_KNOWLEDGE_SEARCH,
    METHOD_KNOWLEDGE_GET,
    METHOD_KNOWLEDGE_REVIEW,
    METHOD_KNOWLEDGE_UPDATE,
    METHOD_KNOWLEDGE_DELETE,
    METHOD_KNOWLEDGE_STATS,
    METHOD_KNOWLEDGE_CONTEXT,
    METHOD_KNOWLEDGE_PROJECT_IMPORT,
    METHOD_KNOWLEDGE_BACKUP,
    METHOD_KNOWLEDGE_EXPORT,
    METHOD_KNOWLEDGE_DECISION_ADD,
    METHOD_KNOWLEDGE_BENCHMARK_ADD,
}


def handle(state: Any, request: Any) -> dict[str, Any] | None:
    """Handle a knowledge request, or return None when it is not one."""
    method = request.method
    if method not in KNOWLEDGE_METHODS:
        return None

    store = KnowledgeStore(getattr(state, "knowledge_root", None))
    params = request.params or {}

    if method == METHOD_KNOWLEDGE_SOURCE_LIST:
        parsed = KnowledgeSourceListParams.model_validate(params)
        return KnowledgeSourceListResult(
            sources=store.list_sources(kind=parsed.kind, limit=parsed.limit)
        ).model_dump(by_alias=True)

    if method == METHOD_KNOWLEDGE_TRANSCRIPT_IMPORT:
        parsed = KnowledgeTranscriptImportParams.model_validate(params)
        result = store.add_transcript(
            transcript=parsed.transcript,
            title=parsed.title,
            url=parsed.url,
            creator=parsed.creator,
            license_text=parsed.license,
            published_at=parsed.published_at,
            external_id=parsed.external_id,
            screenshots=parsed.screenshots,
        )
        return KnowledgeImportResult.model_validate(result).model_dump(by_alias=True)

    if method == METHOD_KNOWLEDGE_DOCUMENT_IMPORT:
        parsed = KnowledgeDocumentImportParams.model_validate(params)
        result = store.add_document(
            path=parsed.path,
            title=parsed.title,
            kind=parsed.kind,
            url=parsed.url,
            creator=parsed.creator,
            license_text=parsed.license,
            revit_version=parsed.revit_version,
            external_id=parsed.external_id,
        )
        return KnowledgeImportResult.model_validate(result).model_dump(by_alias=True)

    if method == METHOD_KNOWLEDGE_TECHNIQUE_ADD:
        parsed = KnowledgeTechniqueAddParams.model_validate(params)
        record = store.add_technique(
            subject=parsed.subject,
            category=parsed.category,
            description=parsed.description,
            body=parsed.body,
            source_type=parsed.source_type,
            revit_version=parsed.revit_version,
            conditions=parsed.conditions,
            procedure=parsed.procedure,
            api_operations=parsed.api_operations,
            constraints=parsed.constraints,
            limitations=parsed.limitations,
            confidence=parsed.confidence,
            tags=parsed.tags,
            source_ids=parsed.source_ids,
            status=parsed.status,
        )
        return KnowledgeTechniqueAddResult(record=record).model_dump(by_alias=True)

    if method == METHOD_KNOWLEDGE_SEARCH:
        parsed = KnowledgeSearchParams.model_validate(params)
        result = store.search(
            query=parsed.query,
            statuses=parsed.statuses,
            source_types=parsed.source_types,
            revit_version=parsed.revit_version,
            limit=parsed.limit,
            offset=parsed.offset,
        )
        return KnowledgeSearchResult.model_validate(result).model_dump(by_alias=True)

    if method == METHOD_KNOWLEDGE_GET:
        parsed = KnowledgeGetParams.model_validate(params)
        return KnowledgeGetResult(record=store.get_record(parsed.record_id)).model_dump(
            by_alias=True
        )

    if method == METHOD_KNOWLEDGE_REVIEW:
        parsed = KnowledgeReviewParams.model_validate(params)
        record = store.review(
            record_id=parsed.record_id,
            action=parsed.action,
            reviewer=parsed.reviewer,
            note=parsed.note,
        )
        return KnowledgeReviewResult(record=record).model_dump(by_alias=True)

    if method == METHOD_KNOWLEDGE_STATS:
        return KnowledgeStatsResult.model_validate(store.stats()).model_dump(by_alias=True)

    if method == METHOD_KNOWLEDGE_UPDATE:
        parsed = KnowledgeUpdateParams.model_validate(params)
        record = store.update_record(
            record_id=parsed.record_id,
            subject=parsed.subject,
            category=parsed.category,
            description=parsed.description,
            body=parsed.body,
            procedure=parsed.procedure,
            api_operations=parsed.api_operations,
            constraints=parsed.constraints,
            limitations=parsed.limitations,
            tags=parsed.tags,
            reviewer=parsed.reviewer,
        )
        return KnowledgeUpdateResult(record=record).model_dump(by_alias=True)

    if method == METHOD_KNOWLEDGE_DELETE:
        parsed = KnowledgeDeleteParams.model_validate(params)
        result = store.delete_record(
            record_id=parsed.record_id,
            reviewer=parsed.reviewer,
            note=parsed.note,
        )
        return KnowledgeDeleteResult.model_validate(result).model_dump(by_alias=True)

    if method == METHOD_KNOWLEDGE_CONTEXT:
        parsed = KnowledgeContextParams.model_validate(params)
        result = store.context(
            query=parsed.query,
            element_kinds=parsed.element_kinds,
            revit_version=parsed.revit_version,
            limit=parsed.limit,
        )
        return KnowledgeContextResult.model_validate(result).model_dump(by_alias=True)

    if method == METHOD_KNOWLEDGE_PROJECT_IMPORT:
        parsed = KnowledgeProjectImportParams.model_validate(params)
        if parsed.extraction is not None:
            extraction = parsed.extraction
        else:
            assert parsed.path is not None
            path = Path(parsed.path).expanduser().resolve()
            if not path.is_file():
                raise not_found(f"Project extraction file was not found: {path}")
            try:
                extraction = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise invalid("Project extraction is not valid JSON.", data=str(exc)) from exc
            if not isinstance(extraction, dict):
                raise invalid("Project extraction JSON must be an object.")
        result = store.add_project_extraction(extraction)
        return KnowledgeProjectImportResult.model_validate(result).model_dump(by_alias=True)

    if method == METHOD_KNOWLEDGE_BACKUP:
        parsed = KnowledgeBackupParams.model_validate(params)
        result = store.backup(parsed.destination)
        return KnowledgeBackupResult.model_validate(result).model_dump(by_alias=True)

    if method == METHOD_KNOWLEDGE_EXPORT:
        parsed = KnowledgeExportParams.model_validate(params)
        result = store.export(parsed.destination)
        return KnowledgeExportResult.model_validate(result).model_dump(by_alias=True)

    if method == METHOD_KNOWLEDGE_DECISION_ADD:
        parsed = KnowledgeDecisionAddParams.model_validate(params)
        return KnowledgeDecisionAddResult.model_validate(
            store.add_decision(
                task=parsed.task,
                model=parsed.model,
                retrieved_ids=parsed.retrieved_ids,
                plan=parsed.plan,
                outcome=parsed.outcome,
            )
        ).model_dump(by_alias=True)

    if method == METHOD_KNOWLEDGE_BENCHMARK_ADD:
        parsed = KnowledgeBenchmarkAddParams.model_validate(params)
        return KnowledgeBenchmarkAddResult.model_validate(
            store.add_benchmark(
                project_id=parsed.project_id,
                method=parsed.method,
                metrics=parsed.metrics,
            )
        ).model_dump(by_alias=True)

    return None
