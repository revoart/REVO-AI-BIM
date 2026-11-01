# Local knowledge seed catalog

This folder mirrors the **development and seed** layout for Revo AI BIM's local
knowledge engine. It is **not** the runtime database.

## Runtime storage

The product stores knowledge at:

```
%LOCALAPPDATA%\RevoAI\knowledge\
  knowledge.db        SQLite database (schema, sources, records, reviews)
  blobs\              local copies when needed
  exports\            JSONL exports created by the user
  backups\            ZIP backups created by the user
  inbox\              read-only Revit project extractions awaiting import
  models\             optional local embedding models (not used yet)
```

Override with `REVOAI_KNOWLEDGE_ROOT` or the `knowledgeRoot` setting in
`%APPDATA%\RevoAI\config.json`.

## Repository policy

Only manifests, notes and small curation metadata belong in Git. Do **not**
commit:

- Customer point clouds or `.rvt` projects.
- YouTube video files or downloaded frames.
- Autodesk documentation dumps.
- Embedding model weights.
- The SQLite database or backups.

The `.gitignore` in this folder enforces that policy.

## Source policy

- Every source must record its origin, creator, licence and retrieval date.
- Only content the user is authorized to store may be imported.
- Video transcripts are pasted or loaded from local files. No DRM or access
  restriction is bypassed.
- Autodesk documentation is stored from official files the user downloads.
- Verified Revit projects are extracted from **copies** and never modified.

## Status model

`extracted → pending_review → approved | rejected | needs_correction`

Verification flags (`verified_revit`, `verified_pointcloud`) are evidence, not
automatic approval. Only approved records are used as guidance by Astra.

See `docs/knowledge-engine.md` for the schema, RPC surface and test evidence.
