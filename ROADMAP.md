# Roadmap

Each phase has explicit acceptance criteria and must be reviewed before the next
phase starts. No phase is marked complete without test evidence.

| Phase | Scope | Status |
| --- | --- | --- |
| 1 | Project foundation: repo, builds, environment, IPC contract, logging, config, tests | **Complete (verified)** |
| 2 | Revit ribbon + WPF workspace + `ExternalEvent` plumbing | **Implemented — manual in-Revit check pending** |
| 3 | Point cloud engine: E57/XYZ/PLY/LAS/LAZ, preprocessing, chunking, indexing | Not started |
| 4 | AI building intelligence: semantic/instance segmentation, confidence | Not started |
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
- Honest "not available yet" dialogs for Phases 3–8 commands.

## Product milestone definition

Phase 5 is the first commercially meaningful milestone: a real E57 residential
scan becomes editable native Revit walls and floors, with measured accuracy.
