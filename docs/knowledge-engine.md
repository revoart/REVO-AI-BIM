# Local BIM knowledge engine

Revo AI BIM now has a persistent, local-first knowledge library. It stores source
material, structured techniques, review history, read-only Revit project
extractions and retrieval decisions. It does **not** upload scans, RVT files or
knowledge to a service.

## Storage

Default runtime root:

```
%LOCALAPPDATA%\RevoAI\knowledge\
  knowledge.db     SQLite, WAL, FTS5
  blobs\           local source copies when needed
  exports\         user-triggered JSONL exports
  backups\         user-triggered ZIP backups
  inbox\           read-only project extraction JSON awaiting import
  models\          reserved for optional local embedding models
```

Resolution order:

1. `REVOAI_KNOWLEDGE_ROOT` environment variable.
2. `knowledgeRoot` in `%APPDATA%\RevoAI\config.json`.
3. `%LOCALAPPDATA%\RevoAI\knowledge`.

The repository `local_knowledge/` tree is a seed/catalog layout only. Payloads
are gitignored.

## Database

| Table | Contents |
| --- | --- |
| `sources` | Origin, creator, licence, URL, retrieval date, content hash |
| `documents` | Transcripts, documents, media type, text, Revit version |
| `document_chunks` | Searchable sections with headings and locators |
| `knowledge_records` | Subject, category, description, procedure, API operations, constraints, limitations, confidence, status, version |
| `record_sources` | Record-to-source provenance |
| `reviews` | Append-only review history |
| `project_extractions` | RVT provenance, version/build, units, hash, warnings |
| `project_elements` | Walls, floors, ceilings, roofs, doors, windows, stairs, railings, columns, rooms, levels, grids |
| `import_jobs` | Import bookkeeping |
| `decisions` | Which knowledge was retrieved for an Astra plan |
| `benchmarks` | Recorded measurement results |
| `knowledge_fts` | FTS5 index over records |
| `chunk_fts` | FTS5 index over source text |

SQLite FTS5 is provided by the bundled Python SQLite build. No external search
service is required.

## Status and verification

```
extracted -> pending_review -> approved | rejected | needs_correction
```

Verification flags are separate evidence:

- `verified_revit`
- `verified_pointcloud`

Only `approved` records are returned by `knowledge.context` and therefore used
as guidance during reconstruction planning. Imported documents create a raw
`source_material` record with status `extracted`; they are searchable and
reviewable but never treated as established guidance.

Approved records are not silently overwritten. Corrections must create a new
revision (`supersedes_id`), and every review action is appended to `reviews`.

## RPC surface

| Method | Purpose |
| --- | --- |
| `knowledge.source.list` | List local sources |
| `knowledge.transcript.import` | Store a transcript with metadata |
| `knowledge.document.import` | Store `.txt`, `.md`, `.html`, `.json`, `.csv`, `.xml`, `.log` |
| `knowledge.technique.add` | Add a structured technique with provenance |
| `knowledge.search` | Full-text search over records and source chunks |
| `knowledge.get` | Full record, provenance and review history |
| `knowledge.review` | Approve, reject, request correction, add verification flags |
| `knowledge.update` | Correct a non-approved record; approved records are immutable |
| `knowledge.delete` | Soft-delete a record while retaining review history |
| `knowledge.stats` | Counts, database path and size |
| `knowledge.context` | Approved, citable context for Astra |
| `knowledge.project.import` | Import a read-only Revit extraction JSON |
| `knowledge.backup` | Create a checksummed ZIP backup |
| `knowledge.export` | Export provenance-preserving JSONL |
| `knowledge.decision.add` | Record a retrieval decision |
| `knowledge.benchmark.add` | Record benchmark metrics |

## Workspace UI

The new **Knowledge library** stage provides:

- Library statistics and storage location.
- Source import for documents and transcripts.
- Read-only **Extract active project**.
- Full-text search with status filtering.
- Record details, procedure, API operations, constraints and limitations.
- Provenance and review history.
- Approve, reject and needs-correction actions.
- Delete with retained review history.
- Backup, export and open-folder actions.

A ribbon **Knowledge** panel exposes **Knowledge Library** and **Extract Project**.

## Revit project extraction

`ProjectKnowledgeExtractor` runs on Revit's main thread through
`RevitTaskRunner`. It:

- Reads the active document only.
- Captures levels, walls, floors, ceilings, roofs, doors, windows, stairs,
  railings, columns, rooms, levels and grids.
- Captures IDs, UniqueIds, category, family, type, level, host, room, bounding
  box in metres, up to 40 parameters and a geometry summary.
- Records project units, Revit version/build, file hash and document warnings.
- Writes JSON to the knowledge inbox and imports it through the engine.
- Never edits, saves or closes the document.

API signatures were verified against the installed Revit 2027 API. Builds are
run for 2026 and 2027.

## Astra retrieval

Before an Astra plan request, the engine searches approved knowledge using the
detected element kinds and appends `approvedKnowledge` (text plus citations) to
the model context. The raw scan evidence always wins. The engine records the
retrieved record IDs and the generated plan summary in `decisions`.

If the knowledge store is unavailable, plan generation proceeds with the scan
evidence only. No knowledge is invented.

## Backup and export

- `knowledge.backup` uses SQLite's backup API, writes a manifest with the schema
  version and SHA-256, then ZIPs the database.
- `knowledge.verify_backup` and `knowledge.restore_backup` are available in the
  Python store for tests and future UI wiring. Restore writes to a chosen
  destination and does not overwrite an existing database unless explicitly
  allowed.
- `knowledge.export` writes JSONL for sources, documents, chunks, records,
  provenance, reviews, project extractions, elements and benchmarks.

## Privacy

- Nothing in this workflow sends source material to a remote service.
- Video transcripts are pasted or loaded from local files.
- No DRM, login or access restriction is bypassed.
- Revit projects are extracted read-only.
- Customer data is not committed to Git.

## Tests

- `tests/RevoAI.Engine.Tests/test_knowledge.py`: persistence, restart, duplicate
  imports, review workflow, approved-only retrieval, project extraction, backup,
  restore, export and RPC dispatch.
- `tests/RevoAI.Revit.Tests/KnowledgeContractTests.cs`: wire contract and
  provenance deserialization.
- `tests/RevoAI.Revit.Tests/KnowledgeIntegrationTests.cs`: real C# client against
  the real engine, including restart persistence and backup.
- Revit 2027 smoke check: the Knowledge stage opened and queried the real engine;
  **Extract Project** imported a real two-level project (units, levels,
  parameters and counts). A full visual review of every button and a verified
  residential model extraction are still pending.

## Current limitations

1. **Full-text search only.** No embedding model or vector index is installed.
   Python 3.14 has no verified `torch`/`onnxruntime`/`faiss` stack in this
   environment. The schema includes an embeddings table but it is not populated.
2. **No automatic YouTube download.** Transcripts and screenshots are imported
   manually. A compliant optional importer is future work.
3. **No PDF parsing.** Save official documentation as HTML/Markdown/Text first.
4. **No UI for fitting/benchmark metrics yet.** The benchmark RPC exists; the
   review UI does not display benchmarks.
5. **Live Astra remains blocked** without the subscription backend or
   `OPENAI_API_KEY`. Retrieval is tested with fakes.
6. **No dimensional accuracy claim.** A verified point-cloud/RVT pair is still
   required.
7. **Approved records cannot be edited in place.** That is intentional; the
   update RPC only accepts non-approved records. Approved corrections need a
   future revision workflow. The review UI currently exposes delete and review
   actions, not an edit form.
