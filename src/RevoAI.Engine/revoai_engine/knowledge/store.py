"""Persistent local knowledge store.

Storage is a single SQLite database under the user's local application data
folder. Full-text search uses FTS5 (bundled with Python's sqlite3), so the
engine has no network dependency and no external database service.

Design rules enforced here:
- Records are versioned and never silently overwritten.
- Every record keeps its source/provenance rows.
- Review history is append-only.
- Imports are idempotent by content hash.
- Backups and exports are explicit files the user can inspect.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable, Iterator

from .errors import invalid, io_failed, not_found, store_failed

SCHEMA_VERSION = 2
DEFAULT_LIMIT = 20
MAX_PAGE_SIZE = 200
MAX_CHUNK_CHARS = 1800
CHUNK_OVERLAP = 200
STATUSES = (
    "extracted",
    "pending_review",
    "approved",
    "rejected",
    "needs_correction",
)
VERIFICATION_FLAGS = ("verified_revit", "verified_pointcloud")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    creator TEXT,
    license TEXT,
    published_at TEXT,
    retrieved_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    external_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(kind, content_hash)
);

CREATE INDEX IF NOT EXISTS ix_sources_kind ON sources(kind);
CREATE INDEX IF NOT EXISTS ix_sources_external ON sources(kind, external_id);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    media_type TEXT NOT NULL,
    path TEXT,
    sha256 TEXT NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    language TEXT,
    revit_version TEXT,
    locator_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(source_id, sha256)
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    heading TEXT,
    text TEXT NOT NULL,
    locator_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_chunks_document ON document_chunks(document_id);

CREATE TABLE IF NOT EXISTS knowledge_records (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL,
    revit_version TEXT,
    conditions_json TEXT NOT NULL DEFAULT '[]',
    procedure_json TEXT NOT NULL DEFAULT '[]',
    api_operations_json TEXT NOT NULL DEFAULT '[]',
    constraints_json TEXT NOT NULL DEFAULT '[]',
    limitations_json TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'pending_review'
        CHECK(status IN ('extracted','pending_review','approved','rejected','needs_correction')),
    verification_json TEXT NOT NULL DEFAULT '[]',
    tags_json TEXT NOT NULL DEFAULT '[]',
    version INTEGER NOT NULL DEFAULT 1,
    supersedes_id TEXT REFERENCES knowledge_records(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    approved_at TEXT,
    approved_by TEXT,
    deleted_at TEXT
);

CREATE INDEX IF NOT EXISTS ix_records_status ON knowledge_records(status);
CREATE INDEX IF NOT EXISTS ix_records_category ON knowledge_records(category);
CREATE INDEX IF NOT EXISTS ix_records_source_type ON knowledge_records(source_type);

CREATE TABLE IF NOT EXISTS record_sources (
    record_id TEXT NOT NULL REFERENCES knowledge_records(id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    document_id TEXT REFERENCES documents(id) ON DELETE SET NULL,
    chunk_id TEXT REFERENCES document_chunks(id) ON DELETE SET NULL,
    locator TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (record_id, source_id, document_id, chunk_id)
);

CREATE TABLE IF NOT EXISTS reviews (
    id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL REFERENCES knowledge_records(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    status_from TEXT,
    status_to TEXT NOT NULL,
    reviewer TEXT,
    note TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_reviews_record ON reviews(record_id);

CREATE TABLE IF NOT EXISTS project_extractions (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    project_name TEXT NOT NULL,
    rvt_path TEXT,
    revit_version TEXT,
    revit_build TEXT,
    units_json TEXT NOT NULL DEFAULT '{}',
    file_sha256 TEXT NOT NULL,
    summary_json TEXT NOT NULL DEFAULT '{}',
    warnings_json TEXT NOT NULL DEFAULT '[]',
    extracted_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_elements (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES project_extractions(id) ON DELETE CASCADE,
    element_id TEXT,
    unique_id TEXT,
    category TEXT NOT NULL,
    family TEXT,
    type_name TEXT,
    level_id TEXT,
    host_id TEXT,
    room_id TEXT,
    bbox_json TEXT NOT NULL DEFAULT '{}',
    parameters_json TEXT NOT NULL DEFAULT '[]',
    geometry_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS ix_project_elements_project ON project_elements(project_id);
CREATE INDEX IF NOT EXISTS ix_project_elements_category ON project_elements(category);

CREATE TABLE IF NOT EXISTS import_jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    source_id TEXT,
    status TEXT NOT NULL,
    counters_json TEXT NOT NULL DEFAULT '{}',
    error TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    task TEXT NOT NULL,
    model TEXT,
    retrieved_ids_json TEXT NOT NULL DEFAULT '[]',
    plan_json TEXT NOT NULL DEFAULT '{}',
    outcome TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS benchmarks (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES project_extractions(id) ON DELETE SET NULL,
    method TEXT NOT NULL,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
    record_id UNINDEXED,
    subject,
    description,
    body,
    tags
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
    chunk_id UNINDEXED,
    document_id UNINDEXED,
    title,
    text
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def default_root() -> Path:
    """Registered default location, overridable for tests and IT deployment."""
    configured = os.environ.get("REVOAI_KNOWLEDGE_ROOT", "").strip()
    if configured:
        return Path(os.path.expandvars(configured)).expanduser().resolve()

    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        return Path(local) / "RevoAI" / "knowledge"

    return Path.home() / ".local" / "share" / "RevoAI" / "knowledge"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _new_id() -> str:
    return uuid.uuid4().hex


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except ValueError:
        return default


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip += 1
        elif tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip:
            self._skip -= 1
        elif tag in {"p", "div", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)

    def text(self) -> str:
        joined = "".join(self.parts)
        return re.sub(r"\n{3,}", "\n\n", joined).strip()


def _strip_html(raw: str) -> str:
    parser = _TextExtractor()
    parser.feed(raw)
    return parser.text()


def _chunks(text: str) -> Iterator[tuple[str, str]]:
    """Yield (heading, chunk) pairs, preserving paragraph boundaries."""
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        return

    paragraphs = [part.strip() for part in re.split(r"\n{2,}", cleaned) if part.strip()]
    current: list[str] = []
    size = 0
    heading = ""

    for paragraph in paragraphs:
        first_line = paragraph.splitlines()[0].strip()
        candidate_heading = first_line if len(first_line) <= 120 else ""
        if not current:
            heading = candidate_heading

        if size + len(paragraph) + 1 > MAX_CHUNK_CHARS and current:
            yield heading, "\n\n".join(current)
            tail = "\n\n".join(current)[-CHUNK_OVERLAP:]
            current = [tail, paragraph] if tail else [paragraph]
            size = sum(len(part) + 2 for part in current)
            heading = candidate_heading
        else:
            current.append(paragraph)
            size += len(paragraph) + 2

    if current:
        yield heading, "\n\n".join(current)


def _terms(query: str, *, match_any: bool = False) -> str:
    tokens = re.findall(r"[\w]+", query, flags=re.UNICODE)
    tokens = [token for token in tokens if len(token) > 1][:12]
    if not tokens:
        return ""
    operator = " OR " if match_any else " AND "
    return operator.join(f'"{token}"*' for token in tokens)


class KnowledgeStore:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root).expanduser().resolve() if root else default_root()
        self.db_path = self.root / "knowledge.db"
        self.blobs_dir = self.root / "blobs"
        self.exports_dir = self.root / "exports"
        self.backups_dir = self.root / "backups"
        self.inbox_dir = self.root / "inbox"
        for directory in (
            self.root,
            self.blobs_dir,
            self.exports_dir,
            self.backups_dir,
            self.inbox_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        try:
            connection = sqlite3.connect(self.db_path, timeout=15.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA journal_mode = WAL")
            yield connection
            connection.commit()
        except sqlite3.Error as exc:
            raise store_failed("The local knowledge database operation failed.", data=str(exc)) from exc
        finally:
            try:
                connection.close()
            except UnboundLocalError:
                pass

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(_SCHEMA)
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(knowledge_records)")
            }
            if "deleted_at" not in columns:
                connection.execute(
                    "ALTER TABLE knowledge_records ADD COLUMN deleted_at TEXT"
                )
            connection.execute(
                "INSERT INTO schema_meta(key, value) VALUES('schemaVersion', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(SCHEMA_VERSION),),
            )

    # ------------------------------------------------------------------ sources

    def _find_source(
        self,
        connection: sqlite3.Connection,
        kind: str,
        content_hash: str,
        external_id: str | None,
    ) -> sqlite3.Row | None:
        row = connection.execute(
            "SELECT * FROM sources WHERE kind = ? AND content_hash = ?",
            (kind, content_hash),
        ).fetchone()
        if row is not None:
            return row
        if external_id:
            return connection.execute(
                "SELECT * FROM sources WHERE kind = ? AND external_id = ?",
                (kind, external_id),
            ).fetchone()
        return None

    def _insert_source(
        self,
        connection: sqlite3.Connection,
        *,
        kind: str,
        title: str,
        content_hash: str,
        url: str | None = None,
        creator: str | None = None,
        license_text: str | None = None,
        published_at: str | None = None,
        external_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[sqlite3.Row, bool]:
        existing = self._find_source(connection, kind, content_hash, external_id)
        if existing is not None:
            return existing, False

        source_id = _new_id()
        now = utc_now()
        connection.execute(
            """
            INSERT INTO sources(
                id, kind, title, url, creator, license, published_at,
                retrieved_at, content_hash, external_id, metadata_json, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                source_id,
                kind,
                title.strip() or "Untitled source",
                url,
                creator,
                license_text,
                published_at,
                now,
                content_hash,
                external_id,
                _json(metadata or {}),
                now,
            ),
        )
        row = connection.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        return row, True

    # ---------------------------------------------------------------- documents

    def add_document(
        self,
        *,
        path: str | Path,
        title: str | None = None,
        kind: str = "local_file",
        url: str | None = None,
        creator: str | None = None,
        license_text: str | None = None,
        revit_version: str | None = None,
        external_id: str | None = None,
    ) -> dict[str, Any]:
        file_path = Path(path).expanduser().resolve()
        if not file_path.is_file():
            raise not_found(f"Knowledge document was not found: {file_path}")

        suffix = file_path.suffix.lower()
        if suffix in {".txt", ".md", ".markdown", ".json", ".csv", ".xml", ".log"}:
            raw = file_path.read_text(encoding="utf-8", errors="replace")
            text = raw
        elif suffix in {".html", ".htm"}:
            raw = file_path.read_text(encoding="utf-8", errors="replace")
            text = _strip_html(raw)
        else:
            raise invalid(
                f"Unsupported knowledge document type '{suffix or 'none'}'. "
                "Use .txt, .md, .html, .htm, .json, .csv, .xml or .log."
            )

        if not text.strip():
            raise invalid("The knowledge document contains no readable text.")

        content_hash = _sha256_bytes(file_path.read_bytes())
        return self._store_document(
            source_kind=kind,
            title=title or file_path.stem,
            content_hash=content_hash,
            text=text,
            media_type=suffix.lstrip(".") or "text",
            path=str(file_path),
            url=url,
            creator=creator,
            license_text=license_text,
            revit_version=revit_version,
            external_id=external_id or content_hash,
            metadata={"import": "file", "originalName": file_path.name},
        )

    def add_transcript(
        self,
        *,
        transcript: str,
        title: str,
        url: str | None = None,
        creator: str | None = None,
        license_text: str | None = None,
        published_at: str | None = None,
        external_id: str | None = None,
        screenshots: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        text = transcript.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            raise invalid("The transcript is empty.")

        metadata: dict[str, Any] = {"import": "transcript"}
        allowed_screenshots: list[str] = []
        for item in screenshots or []:
            screenshot = Path(item).expanduser().resolve()
            if not screenshot.is_file():
                raise not_found(f"Screenshot was not found: {screenshot}")
            allowed_screenshots.append(str(screenshot))
        if allowed_screenshots:
            metadata["screenshots"] = allowed_screenshots

        return self._store_document(
            source_kind="youtube",
            title=title,
            content_hash=_sha256_text(text),
            text=text,
            media_type="transcript",
            path=None,
            url=url,
            creator=creator,
            license_text=license_text,
            published_at=published_at,
            revit_version=None,
            external_id=external_id,
            metadata=metadata,
        )

    def _store_document(
        self,
        *,
        source_kind: str,
        title: str,
        content_hash: str,
        text: str,
        media_type: str,
        path: str | None,
        url: str | None,
        creator: str | None,
        license_text: str | None,
        published_at: str | None,
        revit_version: str | None,
        external_id: str | None,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        with self._connect() as connection:
            source, created = self._insert_source(
                connection,
                kind=source_kind,
                title=title,
                content_hash=content_hash,
                url=url,
                creator=creator,
                license_text=license_text,
                published_at=published_at,
                external_id=external_id,
                metadata=metadata,
            )
            if not created:
                document = connection.execute(
                    "SELECT * FROM documents WHERE source_id = ? ORDER BY created_at LIMIT 1",
                    (source["id"],),
                ).fetchone()
                if document is not None:
                    stats = connection.execute(
                        "SELECT COUNT(*) AS count FROM document_chunks WHERE document_id = ?",
                        (document["id"],),
                    ).fetchone()
                    record = connection.execute(
                        "SELECT id FROM knowledge_records WHERE source_type = ? AND category = 'source_material' AND id IN ("
                        "SELECT record_id FROM record_sources WHERE source_id = ?) LIMIT 1",
                        (source["kind"], source["id"]),
                    ).fetchone()
                    return {
                        "sourceId": source["id"],
                        "documentId": document["id"],
                        "recordId": record["id"] if record else "",
                        "title": source["title"],
                        "kind": source["kind"],
                        "created": False,
                        "chunkCount": int(stats["count"]) if stats else 0,
                        "message": "This source is already in the local knowledge library.",
                    }

            now = utc_now()
            document_id = _new_id()
            connection.execute(
                """
                INSERT INTO documents(
                    id, source_id, kind, media_type, path, sha256, text, language,
                    revit_version, locator_json, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    document_id,
                    source["id"],
                    source_kind,
                    media_type,
                    path,
                    content_hash,
                    text,
                    None,
                    revit_version,
                    _json({"url": url, "title": title}),
                    now,
                ),
            )

            chunk_count = 0
            for ordinal, (heading, chunk) in enumerate(_chunks(text)):
                chunk_id = _new_id()
                connection.execute(
                    """
                    INSERT INTO document_chunks(
                        id, document_id, ordinal, heading, text, locator_json, created_at
                    ) VALUES (?,?,?,?,?,?,?)
                    """,
                    (
                        chunk_id,
                        document_id,
                        ordinal,
                        heading,
                        chunk,
                        _json({"heading": heading, "ordinal": ordinal}),
                        now,
                    ),
                )
                connection.execute(
                    "INSERT INTO chunk_fts(chunk_id, document_id, title, text) VALUES (?,?,?,?)",
                    (chunk_id, document_id, f"{title} — {heading}" if heading else title, chunk),
                )
                chunk_count += 1

            # A raw source note is stored separately from approved techniques. It
            # is searchable and reviewable, but never treated as established
            # guidance until a reviewer explicitly approves structured content.
            record_id = _new_id()
            connection.execute(
                """
                INSERT INTO knowledge_records(
                    id, subject, category, description, body, source_type,
                    revit_version, conditions_json, procedure_json,
                    api_operations_json, constraints_json, limitations_json,
                    confidence, status, verification_json, tags_json, version,
                    supersedes_id, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    record_id,
                    title,
                    "source_material",
                    f"Imported {source_kind} source. Awaiting structured extraction and review.",
                    text,
                    source_kind,
                    revit_version,
                    "[]",
                    "[]",
                    "[]",
                    "[]",
                    "[]",
                    0.0,
                    "extracted",
                    "[]",
                    _json(["source"]),
                    1,
                    None,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO record_sources(
                    record_id, source_id, document_id, chunk_id, locator, created_at
                ) VALUES (?,?,?,?,?,?)
                """,
                (record_id, source["id"], document_id, None, None, now),
            )
            self._index_record(connection, record_id)

            return {
                "sourceId": source["id"],
                "documentId": document_id,
                "recordId": record_id,
                "title": title,
                "kind": source_kind,
                "created": True,
                "chunkCount": chunk_count,
                "message": f"Imported {chunk_count} searchable section(s).",
            }

    # -------------------------------------------------------------- techniques

    def add_technique(
        self,
        *,
        subject: str,
        category: str,
        description: str,
        body: str = "",
        source_type: str = "manual",
        revit_version: str | None = None,
        conditions: list[str] | None = None,
        procedure: list[str] | None = None,
        api_operations: list[str] | None = None,
        constraints: list[str] | None = None,
        limitations: list[str] | None = None,
        confidence: float = 0.0,
        tags: list[str] | None = None,
        source_ids: list[str] | None = None,
        status: str = "pending_review",
    ) -> dict[str, Any]:
        if status not in STATUSES:
            raise invalid(f"Unknown knowledge status '{status}'.")
        if not subject.strip():
            raise invalid("A knowledge subject is required.")
        if not category.strip():
            raise invalid("A knowledge category is required.")
        if not description.strip():
            raise invalid("A knowledge description is required.")
        if not 0.0 <= float(confidence) <= 1.0:
            raise invalid("Confidence must be between 0 and 1.")

        now = utc_now()
        record_id = _new_id()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO knowledge_records(
                    id, subject, category, description, body, source_type,
                    revit_version, conditions_json, procedure_json,
                    api_operations_json, constraints_json, limitations_json,
                    confidence, status, verification_json, tags_json, version,
                    supersedes_id, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    record_id,
                    subject.strip(),
                    category.strip(),
                    description.strip(),
                    body.strip(),
                    source_type.strip() or "manual",
                    revit_version,
                    _json(conditions or []),
                    _json(procedure or []),
                    _json(api_operations or []),
                    _json(constraints or []),
                    _json(limitations or []),
                    float(confidence),
                    status,
                    "[]",
                    _json(tags or []),
                    1,
                    None,
                    now,
                    now,
                ),
            )
            for source_id in source_ids or []:
                exists = connection.execute(
                    "SELECT 1 FROM sources WHERE id = ?", (source_id,)
                ).fetchone()
                if exists is None:
                    raise not_found(f"Knowledge source was not found: {source_id}")
                connection.execute(
                    """
                    INSERT OR IGNORE INTO record_sources(
                        record_id, source_id, document_id, chunk_id, locator, created_at
                    ) VALUES (?,?,?,?,?,?)
                    """,
                    (record_id, source_id, None, None, None, now),
                )
            self._index_record(connection, record_id)
        return self.get_record(record_id)

    def _index_record(self, connection: sqlite3.Connection, record_id: str) -> None:
        record = connection.execute(
            "SELECT * FROM knowledge_records WHERE id = ?", (record_id,)
        ).fetchone()
        if record is None:
            return
        connection.execute("DELETE FROM knowledge_fts WHERE record_id = ?", (record_id,))
        connection.execute(
            "INSERT INTO knowledge_fts(record_id, subject, description, body, tags) VALUES (?,?,?,?,?)",
            (
                record_id,
                record["subject"],
                record["description"],
                record["body"],
                " ".join(_loads(record["tags_json"], [])),
            ),
        )

    # ------------------------------------------------------------------- search

    def search(
        self,
        *,
        query: str = "",
        statuses: list[str] | None = None,
        source_types: list[str] | None = None,
        revit_version: str | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
        match_any: bool = False,
    ) -> dict[str, Any]:
        limit = max(1, min(int(limit), MAX_PAGE_SIZE))
        offset = max(0, int(offset))
        if statuses:
            unknown = [status for status in statuses if status not in STATUSES]
            if unknown:
                raise invalid("Unknown status filter: " + ", ".join(unknown))

        match = _terms(query, match_any=match_any)
        record_limit = limit
        snippet_limit = min(limit, 10)

        with self._connect() as connection:
            record_rows: list[sqlite3.Row]
            if match:
                sql = """
                    SELECT r.* FROM knowledge_fts f
                    JOIN knowledge_records r ON r.id = f.record_id
                    WHERE knowledge_fts MATCH ? AND r.deleted_at IS NULL
                """
                params: list[Any] = [match]
                if statuses:
                    sql += " AND r.status IN (" + ",".join("?" for _ in statuses) + ")"
                    params.extend(statuses)
                if source_types:
                    sql += " AND r.source_type IN (" + ",".join("?" for _ in source_types) + ")"
                    params.extend(source_types)
                if revit_version:
                    sql += " AND (r.revit_version IS NULL OR r.revit_version = ?)"
                    params.append(revit_version)
                sql += " ORDER BY bm25(knowledge_fts) LIMIT ? OFFSET ?"
                params.extend([record_limit, offset])
                record_rows = connection.execute(sql, params).fetchall()
            else:
                sql = "SELECT * FROM knowledge_records WHERE deleted_at IS NULL"
                params = []
                if statuses:
                    sql += " AND status IN (" + ",".join("?" for _ in statuses) + ")"
                    params.extend(statuses)
                if source_types:
                    sql += " AND source_type IN (" + ",".join("?" for _ in source_types) + ")"
                    params.extend(source_types)
                if revit_version:
                    sql += " AND (revit_version IS NULL OR revit_version = ?)"
                    params.append(revit_version)
                sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
                params.extend([record_limit, offset])
                record_rows = connection.execute(sql, params).fetchall()

            provenance = self._provenance_for(
                connection, [row["id"] for row in record_rows]
            )

            snippet_rows: list[sqlite3.Row] = []
            if match:
                snippet_rows = connection.execute(
                    """
                    SELECT c.id AS chunk_id, c.document_id, c.text,
                           s.title, s.kind, s.url, s.id AS source_id,
                           snippet(chunk_fts, 3, '[', ']', '…', 24) AS snippet
                    FROM chunk_fts
                    JOIN document_chunks c ON c.id = chunk_fts.chunk_id
                    JOIN documents d ON d.id = c.document_id
                    JOIN sources s ON s.id = d.source_id
                    WHERE chunk_fts MATCH ?
                    ORDER BY bm25(chunk_fts)
                    LIMIT ?
                    """,
                    (match, snippet_limit),
                ).fetchall()

            total_rows = connection.execute(
                "SELECT COUNT(*) AS count FROM knowledge_records WHERE deleted_at IS NULL"
            ).fetchone()

            return {
                "query": query,
                "records": [
                    self._record_summary(row, provenance.get(row["id"], []))
                    for row in record_rows
                ],
                "snippets": [
                    {
                        "chunkId": row["chunk_id"],
                        "documentId": row["document_id"],
                        "title": row["title"],
                        "kind": row["kind"],
                        "url": row["url"],
                        "sourceId": row["source_id"],
                        "snippet": row["snippet"] or row["text"][:400],
                    }
                    for row in snippet_rows
                ],
                "total": int(total_rows["count"]) if total_rows else 0,
            }

    def _record_summary(
        self, row: sqlite3.Row, provenance: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return {
            "id": row["id"],
            "subject": row["subject"],
            "category": row["category"],
            "description": row["description"],
            "status": row["status"],
            "sourceType": row["source_type"],
            "revitVersion": row["revit_version"],
            "confidence": float(row["confidence"]),
            "verification": _loads(row["verification_json"], []),
            "tags": _loads(row["tags_json"], []),
            "version": int(row["version"]),
            "updatedAt": row["updated_at"],
            "provenance": provenance,
        }

    def _provenance_for(
        self, connection: sqlite3.Connection, record_ids: list[str]
    ) -> dict[str, list[dict[str, Any]]]:
        if not record_ids:
            return {}
        placeholders = ",".join("?" for _ in record_ids)
        rows = connection.execute(
            f"""
            SELECT rs.record_id, rs.locator, s.id AS source_id, s.kind, s.title,
                   s.url, s.creator, s.license, s.published_at
            FROM record_sources rs
            JOIN sources s ON s.id = rs.source_id
            WHERE rs.record_id IN ({placeholders})
            ORDER BY s.title
            """,
            record_ids,
        ).fetchall()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(row["record_id"], []).append(
                {
                    "sourceId": row["source_id"],
                    "kind": row["kind"],
                    "title": row["title"],
                    "url": row["url"],
                    "creator": row["creator"],
                    "license": row["license"],
                    "publishedAt": row["published_at"],
                    "locator": row["locator"],
                }
            )
        return grouped

    def get_record(self, record_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM knowledge_records WHERE id = ? AND deleted_at IS NULL",
                (record_id,),
            ).fetchone()
            if row is None:
                raise not_found(f"Knowledge record was not found: {record_id}")
            provenance = self._provenance_for(connection, [record_id]).get(record_id, [])
            reviews = connection.execute(
                "SELECT * FROM reviews WHERE record_id = ? ORDER BY created_at",
                (record_id,),
            ).fetchall()
            return {
                "id": row["id"],
                "subject": row["subject"],
                "category": row["category"],
                "description": row["description"],
                "body": row["body"],
                "sourceType": row["source_type"],
                "revitVersion": row["revit_version"],
                "conditions": _loads(row["conditions_json"], []),
                "procedure": _loads(row["procedure_json"], []),
                "apiOperations": _loads(row["api_operations_json"], []),
                "constraints": _loads(row["constraints_json"], []),
                "limitations": _loads(row["limitations_json"], []),
                "confidence": float(row["confidence"]),
                "status": row["status"],
                "verification": _loads(row["verification_json"], []),
                "tags": _loads(row["tags_json"], []),
                "version": int(row["version"]),
                "supersedesId": row["supersedes_id"],
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
                "approvedAt": row["approved_at"],
                "approvedBy": row["approved_by"],
                "provenance": provenance,
                "reviews": [
                    {
                        "action": review["action"],
                        "statusFrom": review["status_from"],
                        "statusTo": review["status_to"],
                        "reviewer": review["reviewer"],
                        "note": review["note"],
                        "createdAt": review["created_at"],
                    }
                    for review in reviews
                ],
            }

    # ------------------------------------------------------------------- review

    def review(
        self,
        *,
        record_id: str,
        action: str,
        reviewer: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        action = action.strip().lower()
        transitions = {
            "approve": "approved",
            "reject": "rejected",
            "needs_correction": "needs_correction",
            "pending_review": "pending_review",
        }
        verifications = {
            "verify_revit": "verified_revit",
            "verify_pointcloud": "verified_pointcloud",
        }
        if action not in transitions and action not in verifications and action != "unverify":
            raise invalid(f"Unknown review action '{action}'.")

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM knowledge_records WHERE id = ? AND deleted_at IS NULL",
                (record_id,),
            ).fetchone()
            if row is None:
                raise not_found(f"Knowledge record was not found: {record_id}")

            now = utc_now()
            if action in transitions:
                target = transitions[action]
                connection.execute(
                    """
                    UPDATE knowledge_records
                    SET status = ?, updated_at = ?,
                        approved_at = CASE WHEN ? = 'approved' THEN ? ELSE approved_at END,
                        approved_by = CASE WHEN ? = 'approved' THEN ? ELSE approved_by END
                    WHERE id = ?
                    """,
                    (target, now, target, now, target, reviewer, record_id),
                )
                status_from, status_to = row["status"], target
            else:
                current = _loads(row["verification_json"], [])
                if action == "unverify":
                    current = []
                    status_from = status_to = row["status"]
                else:
                    flag = verifications[action]
                    if flag not in current:
                        current.append(flag)
                    status_from = status_to = row["status"]
                connection.execute(
                    "UPDATE knowledge_records SET verification_json = ?, updated_at = ? WHERE id = ?",
                    (_json(current), now, record_id),
                )

            connection.execute(
                """
                INSERT INTO reviews(
                    id, record_id, action, status_from, status_to, reviewer, note, created_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (_new_id(), record_id, action, status_from, status_to, reviewer, note, now),
            )
        return self.get_record(record_id)

    # ------------------------------------------------------------------ update

    def update_record(
        self,
        *,
        record_id: str,
        subject: str | None = None,
        category: str | None = None,
        description: str | None = None,
        body: str | None = None,
        procedure: list[str] | None = None,
        api_operations: list[str] | None = None,
        constraints: list[str] | None = None,
        limitations: list[str] | None = None,
        tags: list[str] | None = None,
        reviewer: str | None = None,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM knowledge_records WHERE id = ? AND deleted_at IS NULL",
                (record_id,),
            ).fetchone()
            if row is None:
                raise not_found(f"Knowledge record was not found: {record_id}")
            if row["status"] == "approved":
                raise invalid(
                    "Approved knowledge is immutable. Create a new revision instead of editing it."
                )

            updates: list[str] = []
            params: list[Any] = []
            for column, value in (
                ("subject", subject),
                ("category", category),
                ("description", description),
                ("body", body),
            ):
                if value is not None:
                    updates.append(f"{column} = ?")
                    params.append(value.strip())
            for column, value in (
                ("procedure_json", procedure),
                ("api_operations_json", api_operations),
                ("constraints_json", constraints),
                ("limitations_json", limitations),
                ("tags_json", tags),
            ):
                if value is not None:
                    updates.append(f"{column} = ?")
                    params.append(_json(value))

            now = utc_now()
            updates.append("updated_at = ?")
            params.append(now)
            params.append(record_id)
            connection.execute(
                f"UPDATE knowledge_records SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            connection.execute(
                """
                INSERT INTO reviews(
                    id, record_id, action, status_from, status_to, reviewer, note, created_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    _new_id(),
                    record_id,
                    "update",
                    row["status"],
                    row["status"],
                    reviewer,
                    None,
                    now,
                ),
            )
            self._index_record(connection, record_id)
        return self.get_record(record_id)

    def delete_record(
        self,
        *,
        record_id: str,
        reviewer: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM knowledge_records WHERE id = ? AND deleted_at IS NULL",
                (record_id,),
            ).fetchone()
            if row is None:
                raise not_found(f"Knowledge record was not found: {record_id}")

            now = utc_now()
            connection.execute(
                "UPDATE knowledge_records SET deleted_at = ?, updated_at = ? WHERE id = ?",
                (now, now, record_id),
            )
            connection.execute("DELETE FROM knowledge_fts WHERE record_id = ?", (record_id,))
            connection.execute(
                """
                INSERT INTO reviews(
                    id, record_id, action, status_from, status_to, reviewer, note, created_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    _new_id(),
                    record_id,
                    "delete",
                    row["status"],
                    "deleted",
                    reviewer,
                    note,
                    now,
                ),
            )
        return {"deleted": True, "recordId": record_id}

    # --------------------------------------------------------------- extraction

    def add_project_extraction(self, extraction: dict[str, Any]) -> dict[str, Any]:
        project = extraction.get("project")
        elements = extraction.get("elements")
        if not isinstance(project, dict):
            raise invalid("Project extraction is missing the 'project' object.")
        if not isinstance(elements, list) or not elements:
            raise invalid("Project extraction contains no elements.")

        title = str(project.get("title") or "Revit project")
        revit_version = project.get("revitVersion")
        revit_build = project.get("revitBuild")
        rvt_path = project.get("path")
        units = project.get("units") or {}
        warnings = project.get("warnings") or []
        extracted_at = str(project.get("extractedAt") or utc_now())
        content_hash = _sha256_text(_json(extraction))
        file_sha = str(project.get("fileSha256") or content_hash)

        with self._connect() as connection:
            source, created = self._insert_source(
                connection,
                kind="revit_project",
                title=title,
                content_hash=content_hash,
                creator="Revit",
                license_text=None,
                external_id=file_sha,
                metadata={"revitVersion": revit_version, "revitBuild": revit_build},
            )
            if not created:
                existing = connection.execute(
                    "SELECT * FROM project_extractions WHERE source_id = ?", (source["id"],)
                ).fetchone()
                if existing is not None:
                    count = connection.execute(
                        "SELECT COUNT(*) AS count FROM project_elements WHERE project_id = ?",
                        (existing["id"],),
                    ).fetchone()
                    return {
                        "projectId": existing["id"],
                        "sourceId": source["id"],
                        "created": False,
                        "elementCount": int(count["count"]) if count else 0,
                        "warnings": _loads(existing["warnings_json"], []),
                        "message": "This project extraction is already in the local library.",
                    }

            now = utc_now()
            project_id = _new_id()
            connection.execute(
                """
                INSERT INTO project_extractions(
                    id, source_id, project_name, rvt_path, revit_version, revit_build,
                    units_json, file_sha256, summary_json, warnings_json,
                    extracted_at, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    project_id,
                    source["id"],
                    title,
                    rvt_path,
                    revit_version,
                    revit_build,
                    _json(units),
                    file_sha,
                    _json(extraction.get("counts") or {}),
                    _json(warnings),
                    extracted_at,
                    now,
                ),
            )

            inserted = 0
            for element in elements:
                if not isinstance(element, dict):
                    continue
                connection.execute(
                    """
                    INSERT INTO project_elements(
                        id, project_id, element_id, unique_id, category, family,
                        type_name, level_id, host_id, room_id, bbox_json,
                        parameters_json, geometry_json
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        _new_id(),
                        project_id,
                        str(element.get("elementId") or ""),
                        element.get("uniqueId"),
                        str(element.get("category") or "Unknown"),
                        element.get("family"),
                        element.get("typeName"),
                        element.get("levelId"),
                        element.get("hostId"),
                        element.get("roomId"),
                        _json(element.get("boundingBox") or {}),
                        _json(element.get("parameters") or []),
                        _json(element.get("geometry") or {}),
                    ),
                )
                inserted += 1

            return {
                "projectId": project_id,
                "sourceId": source["id"],
                "created": True,
                "elementCount": inserted,
                "warnings": warnings,
                "message": f"Imported {inserted} element(s) from the Revit project.",
            }

    # ------------------------------------------------------------------ context

    def context(
        self,
        *,
        query: str = "",
        element_kinds: list[str] | None = None,
        revit_version: str | None = None,
        limit: int = 8,
    ) -> dict[str, Any]:
        """Return approved, citable knowledge for Astra reasoning."""
        terms = query.strip()
        if not terms and element_kinds:
            terms = " ".join(
                [kind.replace("_", " ") for kind in element_kinds]
                + ["wall", "floor", "level", "reconstruction"]
            )
        if not terms:
            terms = "wall floor level reconstruction revit"

        result = self.search(
            query=terms,
            statuses=["approved"],
            revit_version=revit_version,
            limit=max(1, min(int(limit), 20)),
            match_any=True,
        )
        if not result["records"]:
            result = self.search(
                query="",
                statuses=["approved"],
                revit_version=revit_version,
                limit=max(1, min(int(limit), 20)),
            )
        records = result["records"]
        citations = []
        lines = []
        for record in records:
            sources = []
            for item in record["provenance"]:
                label = item["title"]
                if item.get("url"):
                    label += f" ({item['url']})"
                if item.get("locator"):
                    label += f" [{item['locator']}]"
                sources.append(label)
            citation = {
                "recordId": record["id"],
                "subject": record["subject"],
                "status": record["status"],
                "sources": sources,
            }
            citations.append(citation)
            lines.append(
                f"[{record['id']}] {record['subject']} — {record['description']}"
                + (f" Sources: {'; '.join(sources)}" if sources else "")
            )

        return {
            "query": terms,
            "records": records,
            "citations": citations,
            "text": "\n".join(lines),
            "note": (
                "Only approved knowledge is included. If empty, reason from the "
                "scan evidence and say that no approved technique was retrieved."
            ),
        }

    # -------------------------------------------------------------------- stats

    def stats(self) -> dict[str, Any]:
        with self._connect() as connection:
            def count(table: str, where: str = "", params: tuple[Any, ...] = ()) -> int:
                row = connection.execute(
                    f"SELECT COUNT(*) AS count FROM {table} {where}", params
                ).fetchone()
                return int(row["count"]) if row else 0

            by_status = {
                status: count(
                    "knowledge_records",
                    "WHERE status = ? AND deleted_at IS NULL",
                    (status,),
                )
                for status in STATUSES
            }
            size = self.db_path.stat().st_size if self.db_path.exists() else 0
            return {
                "root": str(self.root),
                "databasePath": str(self.db_path),
                "databaseBytes": size,
                "sources": count("sources"),
                "documents": count("documents"),
                "chunks": count("document_chunks"),
                "records": count("knowledge_records", "WHERE deleted_at IS NULL"),
                "recordsByStatus": by_status,
                "projects": count("project_extractions"),
                "projectElements": count("project_elements"),
                "decisions": count("decisions"),
                "benchmarks": count("benchmarks"),
                "schemaVersion": SCHEMA_VERSION,
            }

    def add_decision(
        self,
        *,
        task: str,
        model: str | None,
        retrieved_ids: list[str],
        plan: dict[str, Any],
        outcome: str,
    ) -> dict[str, Any]:
        decision_id = _new_id()
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO decisions(
                    id, task, model, retrieved_ids_json, plan_json, outcome, created_at
                ) VALUES (?,?,?,?,?,?,?)
                """,
                (
                    decision_id,
                    task,
                    model,
                    _json(retrieved_ids),
                    _json(plan),
                    outcome,
                    now,
                ),
            )
        return {"id": decision_id, "createdAt": now}

    def add_benchmark(
        self,
        *,
        project_id: str | None,
        method: str,
        metrics: dict[str, Any],
    ) -> dict[str, Any]:
        benchmark_id = _new_id()
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO benchmarks(id, project_id, method, metrics_json, created_at) "
                "VALUES (?,?,?,?,?)",
                (benchmark_id, project_id, method, _json(metrics), now),
            )
        return {"id": benchmark_id, "createdAt": now}

    # ------------------------------------------------------------ backup/export

    def backup(self, destination: str | Path | None = None) -> dict[str, Any]:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        target = (
            Path(destination).expanduser().resolve()
            if destination
            else self.backups_dir / f"knowledge-{stamp}.zip"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_db = target.parent / f".knowledge-{uuid.uuid4().hex}.db"

        try:
            with self._connect() as source:
                destination_connection = sqlite3.connect(temp_db)
                try:
                    source.backup(destination_connection)
                finally:
                    destination_connection.close()

            database_bytes = temp_db.read_bytes()
            manifest = {
                "format": "revo-knowledge-backup/1",
                "createdAt": utc_now(),
                "schemaVersion": SCHEMA_VERSION,
                "databaseSha256": _sha256_bytes(database_bytes),
                "databaseBytes": len(database_bytes),
                "counts": self.stats(),
            }
            with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("knowledge.db", database_bytes)
                archive.writestr("manifest.json", _json(manifest))
            archive_hash = _sha256_bytes(target.read_bytes())
            return {
                "path": str(target),
                "sha256": archive_hash,
                "bytes": target.stat().st_size,
                "createdAt": manifest["createdAt"],
            }
        except (OSError, sqlite3.Error) as exc:
            raise io_failed("Could not create the knowledge backup.", data=str(exc)) from exc
        finally:
            try:
                temp_db.unlink(missing_ok=True)
            except OSError:
                pass

    def verify_backup(self, backup_path: str | Path) -> dict[str, Any]:
        path = Path(backup_path).expanduser().resolve()
        if not path.is_file():
            raise not_found(f"Knowledge backup was not found: {path}")
        try:
            with zipfile.ZipFile(path) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                database = archive.read("knowledge.db")
        except (OSError, zipfile.BadZipFile, KeyError, ValueError) as exc:
            raise invalid("The knowledge backup is not a valid Revo backup.", data=str(exc)) from exc
        actual = _sha256_bytes(database)
        if manifest.get("databaseSha256") != actual:
            raise invalid("The knowledge backup checksum does not match its manifest.")
        return {"valid": True, "manifest": manifest, "sha256": actual}

    def restore_backup(
        self,
        backup_path: str | Path,
        destination_root: str | Path,
        *,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        verification = self.verify_backup(backup_path)
        destination = Path(destination_root).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        target_db = destination / "knowledge.db"
        if target_db.exists() and not overwrite:
            raise invalid(
                f"A knowledge database already exists at {target_db}. "
                "Choose another destination or allow overwrite."
            )
        try:
            with zipfile.ZipFile(Path(backup_path).expanduser().resolve()) as archive:
                with archive.open("knowledge.db") as source, target_db.open("wb") as output:
                    shutil.copyfileobj(source, output)
        except (OSError, zipfile.BadZipFile) as exc:
            raise io_failed("Could not restore the knowledge backup.", data=str(exc)) from exc
        return {
            "path": str(target_db),
            "root": str(destination),
            "sha256": verification["sha256"],
            "schemaVersion": verification["manifest"].get("schemaVersion"),
        }

    def export(self, destination: str | Path | None = None) -> dict[str, Any]:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        target = (
            Path(destination).expanduser().resolve()
            if destination
            else self.exports_dir / f"knowledge-{stamp}.jsonl"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._connect() as connection, target.open("w", encoding="utf-8") as output:
                for table in (
                    "sources",
                    "documents",
                    "document_chunks",
                    "knowledge_records",
                    "record_sources",
                    "reviews",
                    "project_extractions",
                    "project_elements",
                    "benchmarks",
                ):
                    rows = connection.execute(f"SELECT * FROM {table}").fetchall()
                    for row in rows:
                        payload = {"type": table}
                        payload.update(dict(row))
                        output.write(_json(payload) + "\n")
                output.write(_json({"type": "manifest", "schemaVersion": SCHEMA_VERSION, "createdAt": utc_now()}) + "\n")
            return {
                "path": str(target),
                "bytes": target.stat().st_size,
                "createdAt": utc_now(),
            }
        except (OSError, sqlite3.Error) as exc:
            raise io_failed("Could not export the local knowledge library.", data=str(exc)) from exc

    def list_sources(self, *, kind: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), MAX_PAGE_SIZE))
        with self._connect() as connection:
            if kind:
                rows = connection.execute(
                    "SELECT * FROM sources WHERE kind = ? ORDER BY created_at DESC LIMIT ?",
                    (kind, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM sources ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
            return [
                {
                    "id": row["id"],
                    "kind": row["kind"],
                    "title": row["title"],
                    "url": row["url"],
                    "creator": row["creator"],
                    "license": row["license"],
                    "retrievedAt": row["retrieved_at"],
                }
                for row in rows
            ]
