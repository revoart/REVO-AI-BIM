# Roadmap

Each phase has explicit acceptance criteria and must be reviewed before the next
phase starts. No phase is marked complete without test evidence.

| Phase | Scope | Status |
| --- | --- | --- |
| 1 | Project foundation: repo, builds, environment, IPC contract, logging, config, tests | **Complete (verified)** |
| 2 | Revit ribbon + WPF workspace + `ExternalEvent` plumbing | **Implemented - Revit 2027 workspace verified; level creation/2026 pending** |
| 3 | Point cloud engine: E57/XYZ/PLY/LAS/LAZ, preprocessing, chunking, indexing | **Implemented - Revit 2027 real E57 import verified; 2026 pending** |
| 4 | AI building intelligence: semantic/instance segmentation, confidence | **Implemented - manual in-Revit check pending** |
| 5 | Native walls and floors: first commercial milestone | **Implemented - manual in-Revit check pending** |
| 6 | Doors and windows: openings, hosted families | Not started |
| 7 | Ceilings, roofs, stairs, railings, columns, beams, rooms | Not started |
| 8 | QA engine: deviation analysis, coverage, confidence reporting | Not started |
| 9 | Performance, scalability, reliability, benchmarks | Not started |
| 10 | Commercial release: licensing, installer, onboarding, support | Not started |

## Phase 1 deliverables (this milestone)

- Environment inspection recorded in `docs/environment.md`.
- Solution builds for Revit 2026 and 2027 on .NET 10.
- Python 3.14 environment with pinned dependencies.
- Versioned JSON-RPC contract with C# and Python implementations.
- Working engine process: `initialize`, `ping`, `shutdown`.
- Configuration, structured logging, typed errors.
- Unit tests on both sides plus a real cross-language integration test.
- Architecture, development, testing and limitation documentation.

## Phase 2 deliverables (implemented)

- Ribbon tab **REVO AI BIM** with Workspace, Import Scan, Scan Analysis,
  Generate BIM, Model Review, Quality Check, Settings and About.
- Modeless WPF workspace with project/scan/settings/levels/processing panels.
- `ExternalEvent` (`RevitTaskRunner`) for all Revit API calls from the UI.
- Transactional level creation with rollback.
- Settings and About windows.
- Honest "not available yet" dialogs for Phases 4-8 commands; Import Scan became
  a real point cloud import in Phase 3.

## Phase 3 deliverables (implemented)

- E57, LAS, LAZ, PLY and XYZ/TXT readers with synthetic-file tests.
- Source unit resolution: E57 metres, LAS/LAZ WKT CRS when available, explicit
  user override, otherwise an explicit metre assumption with a warning.
- Source coordinate preservation (`sourceBounds` in source units, `bounds` in
  metres, no recentring).
- Optional statistical outlier removal and voxel downsampling.
- Chunked NPZ store with a 3D grid index and `metadata.json`.
- Bounds, radius and sample queries over JSON-RPC; nearest-neighbour search is
  implemented and tested at store level.
- JSON-RPC methods `pointcloud.import`, `pointcloud.info` and
  `pointcloud.query`, with a real C# client and import dialog.
- Workspace scan summary showing format, unit, stored points, chunks, bounds and
  local store path.

## Phase 4 deliverables (implemented)

- Geometric RANSAC plane extraction over a sampled/voxelised point cloud.
- Instance geometry for each detected plane: normal, offset, centroid, bounds,
  area and inlier count.
- Semantic classification into floor, ceiling, wall, horizontal and sloped.
- Plane-fit confidence from planarity, sampling density, segment size, coverage
  and fit error; the method and its meaning are written into every result.
- JSON result persisted beside the scan at `analysis/segmentation.json`.
- JSON-RPC methods `segmentation.run` and `segmentation.info`.
- C# DTOs, engine client methods, real Scan Analysis dialog and workspace
  detected-element/confidence summary.
- Python tests with synthetic rooms and C# end-to-end engine tests.

This baseline is deterministic geometry, not a trained neural network and not a
dimensional-accuracy claim. Trained models and BIM geometry remain later work.

## Phase 5 deliverables (implemented)

- Segmentation instances now include an ordered plane boundary for reconstruction.
- `reconstruction.plan` turns confidence-filtered floors and walls into a plan
  with levels, closed floor polygons, wall lines, base levels and heights.
- Plan preview dialog with floor/wall counts, confidence, warnings and no Revit
  mutation.
- Native `Floor.Create` and `Wall.Create` in one Revit transaction.
- Existing levels are reused by elevation; missing levels are created.
- Created elements carry `REVO-INFERRED` marks and comments with source segment
  and confidence.
- Transaction rollback on failure; no placeholder geometry.
- Python plan tests, C# contract tests and real engine plan integration tests.

This milestone uses default Revit floor/wall types and convex-hull floor
boundaries. Doors, windows, ceilings, wall thickness control and accuracy
measurement remain later work.

## Phase 5.1 deliverables (implemented)

- Persistent local knowledge library at `%LOCALAPPDATA%\RevoAI\knowledge`.
- SQLite schema with sources, documents, chunks, records, provenance, reviews,
  project extractions, elements, decisions and benchmarks.
- FTS5 search over records and source chunks.
- Transcript and document import with source metadata, licence and content-hash
  deduplication.
- Structured technique records with procedure, API operations, conditions,
  constraints, limitations, confidence and provenance.
- Review workflow: extracted, pending review, approved, rejected, needs
  correction, plus Revit/point-cloud verification flags.
- Approved-only retrieval context for Astra, with citation logging.
- Read-only Revit project extraction for levels, walls, floors, ceilings, roofs,
  doors, windows, stairs, railings, columns, rooms and grids.
- Knowledge library stage in the workspace and a Knowledge ribbon panel.
- Checksummed backup and provenance-preserving JSONL export.
- Python and .NET tests for persistence, review, retrieval, extraction,
  duplicate handling, backup/restore and export.

Not yet implemented: embeddings/vector search, automatic YouTube ingestion, PDF
parsing, benchmark UI and any dimensional-accuracy claim. Live Astra remains
blocked without credentials or the subscription backend.

## Phase 5.3 deliverables (implemented)

- Small portrait workspace (430×820) with three usage steps and a point-cloud
  control. Technical tables, engine diagnostics and knowledge UI removed.
- DeepSeek Go provider with configurable endpoint and key.
- Orthographic plan and four elevation depth snapshots with axes/scale metadata.
- AI schedule contract validated before Revit, covering walls, slabs, openings,
  doors, windows, roofs and columns.
- Native builder: slabs, thickness-specific walls, hosted doors/windows, flat
  roofs and columns (when a family is loaded).
- Visible incremental build: levels, slabs, walls, openings, roofs and columns are
  committed in separate transactions; the UI shows progress and the 3D view follows
  the new work.
- Revit 2027 builder probe passed: 1 slab, 4 walls, 2 openings, 1 roof.
- Knowledge Library is backend-only; no customer-facing UI.

Not yet implemented: live DeepSeek Go run, pitched/gable roof slopes, stairs,
family-type dimension matching, and cloud-to-model verification.

## Product milestone definition

Phase 5 is the first commercially meaningful milestone: a real E57 residential
scan becomes editable native Revit walls and floors, with measured accuracy.
