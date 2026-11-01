# Roadmap

Each phase has explicit acceptance criteria and must be reviewed before the next
phase starts. No phase is marked complete without test evidence.

| Phase | Scope | Status |
| --- | --- | --- |
| 1 | Project foundation: repo, builds, environment, IPC contract, logging, config, tests | **Complete (verified)** |
| 2 | Revit ribbon + WPF workspace + `ExternalEvent` plumbing | **Implemented — manual in-Revit check pending** |
| 3 | Point cloud engine: E57/XYZ/PLY/LAS/LAZ, preprocessing, chunking, indexing | **Implemented — manual in-Revit check pending** |
| 4 | AI building intelligence: semantic/instance segmentation, confidence | **Implemented - manual in-Revit check pending** |
| 5 | Native walls and floors: first commercial milestone | Not started |
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

## Product milestone definition

Phase 5 is the first commercially meaningful milestone: a real E57 residential
scan becomes editable native Revit walls and floors, with measured accuracy.
