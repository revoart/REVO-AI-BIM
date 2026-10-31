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
- [ ] Manual ribbon/workspace test in Revit 2027
- [ ] Phase reviewed and approved

## Phases 3–10

Not started. See `ROADMAP.md`.
