# Phase Completion Checklist

A phase is complete only when every required item is checked and the completion
report contains test evidence.

## Phase 1 — Project foundation

- [x] Development environment inspected and recorded (`docs/environment.md`)
- [x] Installed Revit versions identified (2026, 2027; 2025 absent)
- [x] .NET SDK, Python, Git, Visual Studio checked
- [x] Repository structure created
- [x] Solution builds for Revit 2026
- [x] Solution builds for Revit 2027
- [x] Python environment initializes
- [x] Pinned dependencies documented
- [x] C# ↔ Python communication contract defined and implemented
- [x] Configuration management implemented
- [x] Structured logging implemented
- [x] Typed error handling implemented
- [x] Versioning strategy defined
- [x] .NET unit tests pass
- [x] Python unit tests pass
- [x] Cross-language integration test passes
- [x] Architecture documentation complete
- [x] Manual Revit load test on 2026 (confirmed by product owner)
- [ ] Manual Revit load test on 2027 (pending)
- [x] Phase reviewed and approved by product owner

## Phase 2 — Revit plugin interface

- [x] Ribbon tab **REVO AI BIM** with the seven required controls plus Workspace
- [x] Ribbon icons for every control
- [x] Modeless WPF workspace with project, scan, settings, levels, processing and engine panels
- [x] `ExternalEvent` plumbing (`RevitTaskRunner`)
- [x] Transaction handling with rollback (create levels)
- [x] Settings window persisting configuration
- [x] About window
- [x] Honest not-available dialogs for later phases
- [x] Windows and icons construct outside Revit (`probe-ui.ps1`)
- [ ] Manual ribbon/workspace test in Revit 2026
- [x] Manual ribbon/workspace test in Revit 2027 (ribbon, Workspace, engine test)
- [ ] Phase reviewed and approved

## Phase 3 — Point cloud engine

- [x] E57 reader with multi-scan pose transforms
- [x] LAS and LAZ reader
- [x] PLY reader (ASCII and binary)
- [x] XYZ/TXT reader
- [x] Source unit detection, explicit override and metre conversion
- [x] Source bounds preserved in source units
- [x] Statistical outlier removal
- [x] Voxel downsampling
- [x] Chunked store with 3D grid index and metadata
- [x] Bounds, radius, nearest and sample queries
- [x] JSON-RPC import/info/query methods and typed errors
- [x] C# DTOs, engine client methods and real import dialog
- [x] Workspace scan summary
- [x] Python tests for every supported format and query type
- [x] Real C# ↔ Python import/info/query integration test
- [x] Revit 2026 and 2027 Release builds with zero warnings
- [x] WPF probe constructs workspace, import, settings and about windows
- [ ] Manual import test in Revit 2026
- [x] Manual import test in Revit 2027 (real E57, 27,802,731 points, 21 chunks)
- [ ] Phase reviewed and approved

## Phase 4 — Scan Analysis baseline

- [x] Sample and voxel-downsample the imported store for analysis
- [x] RANSAC plane extraction with configurable distance, minimum points and plane limit
- [x] Floor, ceiling, wall and other horizontal/sloped classification
- [x] Instance data: normal, offset, centroid, bounds, area, point count
- [x] Plane-fit confidence with explicit meaning in the result
- [x] Atomic `analysis/segmentation.json` result
- [x] JSON-RPC `segmentation.run` / `segmentation.info` and typed `ANALYSIS_NOT_FOUND`
- [x] C# DTOs, engine client methods and real Scan Analysis dialog
- [x] Workspace detected-element and mean-confidence summary
- [x] Synthetic-room Python tests
- [x] C# contract test and real C# ↔ Python segmentation integration test
- [x] Revit 2026 and 2027 Release builds with zero warnings
- [x] WPF probe constructs the Scan Analysis window
- [ ] Manual Scan Analysis test in Revit 2026
- [ ] Manual Scan Analysis test in Revit 2027
- [ ] Phase reviewed and approved

## Phase 5 — Native walls and floors

- [x] Segmentation boundaries stored with each plane
- [x] Confidence-filtered reconstruction plan
- [x] Floor level clustering and closed floor polygons
- [x] Wall line endpoints, base level and height resolution
- [x] `reconstruction.plan` JSON-RPC method and typed DTOs
- [x] External AI plan JSON contract, validation and `PLAN_INVALID`
- [x] GPT-6 Astra BYO provider with `OPENAI_API_KEY` and `AI_PROVIDER_FAILED`
- [x] GPT-6 Astra subscription gateway client and typed subscription errors
- [ ] Subscription backend, sign-in, token storage and billing
- [x] Plan preview stage inside the single Workspace window
- [x] Native `Floor.Create` / `Wall.Create` in one transaction
- [x] Existing level reuse and missing level creation
- [x] `REVO-INFERRED` mark/comments
- [x] Transaction rollback on failure
- [x] Python plan tests and C# contract/integration tests
- [x] Revit 2026 and 2027 Release builds with zero warnings
- [x] WPF probe constructs the Workspace with all stages
- [ ] Manual floor/wall creation test in Revit 2026
- [ ] Manual floor/wall creation test in Revit 2027
- [ ] Phase reviewed and approved

## Phases 6–10

Not started. See `ROADMAP.md`.
