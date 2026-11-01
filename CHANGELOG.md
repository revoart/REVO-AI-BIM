# Changelog

All notable changes are documented here. Format follows Keep a Changelog and
Semantic Versioning.

## [0.5.1] - 2026-11-01 - Single-window staged workflow

### Changed

- Import, Scan Analysis and Generate BIM are now stages inside the existing
  Workspace window. The separate process windows are no longer opened.
- Sidebar stage navigation: Project setup, Import scan, Analyze scan, Generate
  BIM, with a high-contrast blue active stage and left-aligned labels.
- Stage-specific headers, subtitles and continuation buttons.
- Levels table no longer auto-generates duplicate columns.
- **Create in Revit** is disabled until a plan preview exists.
- Generate BIM can consume an external AI plan JSON file, validate it with
  `PLAN_INVALID` (`-32027`), normalize it and preview it before creation.
- GPT-6 Astra BYO-key provider calls `gpt-6-astra` from the local engine using
  `OPENAI_API_KEY`, then validates the returned plan with the same rules. The
  provider path is mocked-tested; a live call requires an API key.
- GPT-6 Astra subscription provider calls a Revo gateway with
  `REVOAI_ASTRA_GATEWAY_URL` and `REVOAI_SUBSCRIPTION_TOKEN`; the OpenAI key stays
  server-side. Backend/sign-in/billing are still to be implemented.
- Added `SUBSCRIPTION_REQUIRED` and `SUBSCRIPTION_QUOTA_EXCEEDED` error codes and
  `docs/subscription-architecture.md`.
- Added the external Claude/Astra BIM plan contract in
  `docs/external-bim-plan.md`.
- Current scan summary remains visible in the sidebar while working.
- The workspace project information, levels, diagnostics and engine controls
  moved into the Project setup stage.
- Generate BIM and Scan Analysis results remain in the same window for review.

### Verified

- 65 Python tests and 32 .NET tests pass.
- Revit 2026/2027 Release builds still complete with zero warnings.
- WPF probe still passes for all windows and icons.

## [0.5.0] - 2026-11-01 - Phase 5: native walls and floors

### Added

- Ordered plane boundaries on segmentation instances, used for reconstruction.
- `reconstruction.plan` JSON-RPC method and typed plan DTOs.
- Reconstruction plan with level clustering, closed floor polygons, wall lines,
  base levels, wall heights and confidence filtering.
- Plan file written to `<scan store>/analysis/reconstruction-plan.json`.
- **Generate BIM** dialog with preview of levels, floors, walls, heights and
  warnings; nothing is created before confirmation.
- Native `Floor.Create` and `Wall.Create` calls in one transaction.
- Existing level reuse by elevation and creation of missing levels.
- `REVO-INFERRED` marks/comments on created floors and walls.
- Transaction rollback on failure.
- Python plan tests, C# contract tests and real engine plan integration test.

### Changed

- Product and engine version 0.5.0.
- Ribbon **Generate BIM** now opens the real plan/generation dialog.
- Workspace phase badge and footer reflect Phase 5.
- Documentation updated for the first commercial milestone.

### Verified

- 59 Python tests and 32 .NET tests pass.
- Revit 2026 and 2027 Release builds complete with zero warnings.
- WPF probe constructs the workspace, settings and about windows.
- Real engine plan integration test passes.
- Synthetic room produces one level, one floor and four walls.

### Known gaps

- Native floor/wall creation still needs a manual in-Revit check.
- Uses default floor/wall types; requested wall thickness is not applied.
- Floor boundaries are convex hulls, so L-shaped or concave rooms are
  oversimplified.
- Ceilings, doors, windows, furniture, stairs and curved surfaces are not
  created.
- No dimensional accuracy claim.

## [0.4.1] - 2026-11-01 - Import Scan crash hotfix

### Fixed

- Removed the fatal `ProgressValue` TwoWay binding on the read-only workspace
  property; the progress bar now binds one-way.
- Deferred workspace/import/analysis window opening to Revit's `Idling` event so
  no WPF window, modal loop or `ExternalEvent` is created inside a ribbon
  command. This prevents the Revit 2027 `0xe0434352` termination.
- Create the `RevitTaskRunner`/`ExternalEvent` during `OnStartup`, where Revit
  permits it, instead of during a deferred UI action.
- Import and Scan Analysis windows are now modeless, owned by the workspace and
  forced to a normal window state, so they cannot hide inside a nested modal
  loop or open minimized.
- Added managed crash logging for the WPF dispatcher, AppDomain and unobserved
  tasks.

### Verified

- Import Scan opens the workspace and import dialog without terminating Revit
  2027.
- Imported a real 27,802,731-point E57 scan into 21 chunks in 12.6 s on Revit
  2027; the workspace loaded the store with colours and intensity.
- Ran Phase 4 segmentation on that real scan: 82,260 analysed points, 14 planar
  instances, mean plane-fit confidence 0.761, 90.2% coverage, 1.04 s.
- Unsupported `.rwcx` input now returns the normal typed error dialog instead of
  crashing.
- Revit 2026 and 2027 Release builds still complete with zero warnings.

## [0.4.0] - 2026-11-01 - Phase 4: Scan Analysis baseline

### Added

- Geometric semantic/instance segmentation baseline using Open3D RANSAC plane
  extraction over a sampled and optionally voxel-downsampled cloud.
- Plane instances with normal, offset, centroid, bounds, area, inlier count and
  floor/ceiling/wall classification.
- Plane-fit confidence from planarity, density, size, coverage and fit error,
  with an explicit note that it is not dimensional accuracy.
- Analysis result persisted atomically at
  `<scan store>/analysis/segmentation.json`.
- JSON-RPC `segmentation.run` and `segmentation.info`, advertised in
  `initialize.capabilities`.
- Typed `ANALYSIS_NOT_FOUND` error (`-32026`).
- C# segmentation DTOs, `PythonEngineClient` methods, real Scan Analysis dialog
  and workspace detected-element/confidence summary.
- Ribbon **Scan Analysis** now runs the real baseline instead of showing a
  placeholder dialog.
- Python synthetic-room tests, C# contract tests and a real C# -> Python
  segmentation integration test.

### Changed

- Product and engine version 0.4.0.
- Workspace phase badge and processing metrics reflect Phase 4.
- `README`, architecture, testing, roadmap, checklist and limitations updated.

### Verified

- 57 Python tests and 30 .NET tests pass.
- Revit 2026 and 2027 Release builds complete with zero warnings.
- WPF probe constructs the workspace, import, analysis, settings and about
  windows.
- Engine smoke test advertises segmentation capabilities at 0.4.0.

### Known gaps

- The segmentation baseline is geometric, not a trained ML model. It does not
  detect doors, windows, furniture or curved surfaces.
- Confidence is a plane-fit score, not a dimensional accuracy figure.
- No Revit geometry is created; results are JSON data only.
- Manual in-Revit verification of Phases 2-4 is pending.

## [0.3.0] - 2026-11-01 - Phase 3: point cloud engine

### Added

- E57, LAS, LAZ, PLY and XYZ/TXT point cloud readers.
- E57 multi-scan import with pose transforms applied by `pye57`.
- Source unit resolution and explicit override, including US survey feet.
- Source bounds preserved in source units alongside metre bounds.
- Optional statistical outlier removal and voxel downsampling.
- Chunked NPZ point cloud store with float64 chunk origins, float32 offsets and
  a 3D grid index in `metadata.json`.
- Bounds, radius, nearest-neighbour and sample queries that open only candidate
  chunks.
- JSON-RPC `pointcloud.import`, `pointcloud.info` and `pointcloud.query`.
- Typed point cloud error codes and remedies.
- C# point cloud DTOs, `PythonEngineClient` methods and real import dialog.
- Workspace point cloud summary: format, unit source, points, chunks, bounds and
  local store path.
- Ribbon **Import Scan** now opens the real import dialog.
- Python tests for every format, units, preprocessing, storage, queries and the
  service protocol; C# contract and real-engine integration tests.

### Changed

- Product version 0.3.0; engine package version 0.3.0.
- `requirements.in`/lock include `pye57` and `pyquaternion`.
- Protocol `initialize.capabilities` now advertises the three point cloud
  methods.

### Verified

- 54 Python tests and 27 .NET tests pass.
- Revit 2026 and 2027 Release builds complete with zero warnings.
- WPF probe constructs workspace, import, settings and about windows.
- Real C# → Python import/info/query integration test passes.

### Known gaps

- Manual in-Revit verification of Phases 2 and 3 is pending.
- RCP/RCS import, import streaming, cancellation/progress and CRS reprojection
  are not implemented.
- Nearest-neighbour search is tested at store level but not exposed over
  JSON-RPC.
- No Revit point-cloud preview or BIM geometry yet.

## [0.2.0] - 2026-10-31 — Phase 2: Revit plugin interface

### Added

- **REVO AI BIM** ribbon tab with Workspace, Import Scan, Scan Analysis,
  Generate BIM, Model Review, Quality Check, Settings and About.
- Modeless WPF workspace: project information, scan panel, reconstruction
  settings, level list, processing status, error list and engine diagnostics.
- Settings window that reads and writes `%APPDATA%\RevoAI\config.json` with
  validation, interpreter/engine folder pickers and log-folder shortcut.
- About window with product, Revit and protocol versions.
- `ExternalEvent`-based `RevitTaskRunner`: every Revit API call from the UI is
  marshalled to Revit's main thread.
- Real transactional level creation from the workspace (create missing levels,
  skip existing names, rollback on failure).
- Python engine connection test inside the workspace (real process, real ping).
- Ribbon icon set generated by `scripts/generate-icons.ps1`.
- UI probe (`scripts/probe-ui.ps1`) that constructs every window and loads every
  icon without Revit.
- `RevoConfigWriter` with round-trip tests.

### Changed

- Product version 0.2.0; engine and geometry package versions aligned.
- `install-addin.ps1` writes a developer configuration pointing at the
  repository virtual environment when no config exists.

### Verified

- Builds for Revit 2026 and 2027, zero warnings.
- 22 .NET tests and 36 Python tests pass.
- All three WPF windows construct and all eight 32 px icons load via pack URI.
- Settings round-trip persists and reloads correctly.

### Known gaps

- Ribbon and level creation still need a manual in-Revit check.
- No point cloud, AI or BIM reconstruction (Phases 3–5).

## [0.1.0] - 2026-10-31 — Phase 1: Project foundation

### Added

- Repository structure, solution (`RevoAI.slnx`), central package management.
- `RevoAI.Contracts` (`net8.0`): JSON-RPC 2.0 DTOs, protocol versioning, error
  codes, shared JSON settings.
- `RevoAI.Revit` (`net10.0-windows`): Revit 2026/2027 build selection, add-in
  entry point with safe startup/shutdown, structured JSON-lines logging,
  configuration loader, Python engine process client.
- `RevoAI.Engine` (Python): newline-delimited JSON-RPC service with
  `initialize`, `ping`, `shutdown`, typed errors and file/stderr logging.
- `RevoAI.Geometry` (Python): unit kernel (metres as canonical engine unit,
  feet as Revit internal unit).
- Tests: xUnit protocol/config/integration tests; pytest protocol/dispatch/
  process/unit tests.
- Scripts: bootstrap, build, test, developer add-in install/uninstall, engine
  smoke test.
- Documentation: architecture, development, roadmap, testing, environment,
  ADRs, phase report, known limitations.

### Verified

- Builds for Revit 2026 (26.5.0.55) and Revit 2027 (27.0.4.412) with .NET SDK
  10.0.401, zero warnings.
- C# ↔ Python handshake, ping and shutdown over a real child process.
- Python 3.14.7 environment with Open3D 0.20.0 wheel availability confirmed.

### Known gaps

- No Revit ribbon or WPF interface yet (Phase 2).
- No point cloud, AI or BIM generation (Phases 3–5).
- Revit 2025 not installed; its build mapping is unverified.
- Manual Revit load test still required on the target machine.
