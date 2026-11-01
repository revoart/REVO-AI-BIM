"""Wire models for the local knowledge RPC surface."""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from ..protocol import CamelModel


class KnowledgeSourceListParams(CamelModel):
    kind: str | None = None
    limit: int = 100


class KnowledgeSourceListResult(CamelModel):
    sources: list[dict[str, Any]]


class KnowledgeTranscriptImportParams(CamelModel):
    title: str = Field(min_length=1, max_length=300)
    transcript: str = Field(min_length=1)
    url: str | None = None
    creator: str | None = None
    license: str | None = None
    published_at: str | None = None
    external_id: str | None = None
    screenshots: list[str] = []


class KnowledgeDocumentImportParams(CamelModel):
    path: str = Field(min_length=1)
    title: str | None = None
    kind: str = "local_file"
    url: str | None = None
    creator: str | None = None
    license: str | None = None
    revit_version: str | None = None
    external_id: str | None = None


class KnowledgeImportResult(CamelModel):
    source_id: str
    document_id: str
    record_id: str = ""
    title: str
    kind: str
    created: bool
    chunk_count: int
    message: str


class KnowledgeTechniqueAddParams(CamelModel):
    subject: str = Field(min_length=1, max_length=300)
    category: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1)
    body: str = ""
    source_type: str = "manual"
    revit_version: str | None = None
    conditions: list[str] = []
    procedure: list[str] = []
    api_operations: list[str] = []
    constraints: list[str] = []
    limitations: list[str] = []
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    tags: list[str] = []
    source_ids: list[str] = []
    status: str = "pending_review"


class KnowledgeTechniqueAddResult(CamelModel):
    record: dict[str, Any]


class KnowledgeSearchParams(CamelModel):
    query: str = ""
    statuses: list[str] | None = None
    source_types: list[str] | None = None
    revit_version: str | None = None
    limit: int = 20
    offset: int = 0


class KnowledgeSearchResult(CamelModel):
    query: str
    records: list[dict[str, Any]]
    snippets: list[dict[str, Any]]
    total: int


class KnowledgeGetParams(CamelModel):
    record_id: str = Field(min_length=1)


class KnowledgeGetResult(CamelModel):
    record: dict[str, Any]


class KnowledgeReviewParams(CamelModel):
    record_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    reviewer: str | None = None
    note: str | None = None


class KnowledgeReviewResult(CamelModel):
    record: dict[str, Any]


class KnowledgeUpdateParams(CamelModel):
    record_id: str = Field(min_length=1)
    subject: str | None = None
    category: str | None = None
    description: str | None = None
    body: str | None = None
    procedure: list[str] | None = None
    api_operations: list[str] | None = None
    constraints: list[str] | None = None
    limitations: list[str] | None = None
    tags: list[str] | None = None
    reviewer: str | None = None


class KnowledgeUpdateResult(CamelModel):
    record: dict[str, Any]


class KnowledgeDeleteParams(CamelModel):
    record_id: str = Field(min_length=1)
    reviewer: str | None = None
    note: str | None = None


class KnowledgeDeleteResult(CamelModel):
    deleted: bool
    record_id: str


class KnowledgeStatsResult(CamelModel):
    root: str
    database_path: str
    database_bytes: int
    sources: int
    documents: int
    chunks: int
    records: int
    records_by_status: dict[str, int]
    projects: int
    project_elements: int
    decisions: int
    benchmarks: int
    schema_version: int


class KnowledgeContextParams(CamelModel):
    query: str = ""
    element_kinds: list[str] = []
    revit_version: str | None = None
    limit: int = 8


class KnowledgeContextResult(CamelModel):
    query: str
    records: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    text: str
    note: str


class KnowledgeProjectImportParams(CamelModel):
    path: str | None = None
    extraction: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _one_input(self) -> "KnowledgeProjectImportParams":
        if not self.path and not self.extraction:
            raise ValueError("Provide either a project extraction path or an extraction object.")
        if self.path and self.extraction:
            raise ValueError("Provide only one of path or extraction.")
        return self


class KnowledgeProjectImportResult(CamelModel):
    project_id: str
    source_id: str
    created: bool
    element_count: int
    warnings: list[str]
    message: str


class KnowledgeBackupParams(CamelModel):
    destination: str | None = None


class KnowledgeBackupResult(CamelModel):
    path: str
    sha256: str
    bytes: int
    created_at: str


class KnowledgeExportParams(CamelModel):
    destination: str | None = None


class KnowledgeExportResult(CamelModel):
    path: str
    bytes: int
    created_at: str


class KnowledgeDecisionAddParams(CamelModel):
    task: str = Field(min_length=1)
    model: str | None = None
    retrieved_ids: list[str] = []
    plan: dict[str, Any] = {}
    outcome: str = "recorded"


class KnowledgeDecisionAddResult(CamelModel):
    id: str
    created_at: str


class KnowledgeBenchmarkAddParams(CamelModel):
    project_id: str | None = None
    method: str = Field(min_length=1)
    metrics: dict[str, Any] = {}


class KnowledgeBenchmarkAddResult(CamelModel):
    id: str
    created_at: str
