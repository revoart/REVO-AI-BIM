# Known Limitations

This file is deliberately blunt. Anything listed here is **not working** or
**not verified**, regardless of what other documents imply.

## Product scope (current)

1. **The UI is a shell.** The ribbon and workspace exist, but Import Scan, Scan
   Analysis, Generate BIM, Model Review and Quality Check only show honest
   "not implemented" dialogs. The only model-changing action is creating levels.
2. **No point cloud support.** E57, RCP/RCS, LAS/LAZ, PLY and XYZ are not read
   yet. The dependencies are installed for Phase 3 but no importer exists.
3. **No AI.** No model, no training, no inference, no segmentation.
4. **No BIM reconstruction.** No walls, floors, doors, windows or other scanned
   elements are created. Level creation is project setup, not Scan-to-BIM.
5. **No accuracy figures.** Nothing has been measured because nothing is
   reconstructed yet.

## Environment and compatibility

6. **Revit 2025 is not installed or tested.** The `net8.0-windows` mapping in
   `Directory.Build.props` is a hypothesis, not a verified build.
7. **Revit 2026/2027 use .NET 10**, not .NET 8 as originally assumed. The add-in
   targets `net10.0-windows`. Do not copy .NET 8 build recipes from older Revit
   documentation.
8. **Python 3.14 only.** Older Python versions are not tested. Open3D 0.20.0 is
   the only wheel verified for cp314.
9. **Windows only.** No macOS or Linux support is planned for the add-in.

## Engineering

10. **The engine is a child process over stdio.** If the add-in crashes without
    disposing the client, the engine process may survive until the OS cleans it
    up. A supervisor/watchdog arrives in Phase 9.
11. **One engine process per add-in session, single-threaded.** No concurrent
    jobs. Long-running jobs and cancellation are not implemented yet.
12. **No installer.** `install-addin.ps1` is a developer script that writes to
    `%APPDATA%`. Phase 10 replaces it with a signed installer.
13. **No licensing, telemetry, onboarding or support workflow.** Phase 10.
14. **No code signing.** Windows and Revit may warn about unsigned assemblies.
15. **OneDrive workspace.** The repository currently sits in a OneDrive folder;
    this can cause file locks and sync churn. Move to local disk for large scans.
16. **No CI pipeline yet.** Tests are run locally via `scripts\test.ps1`.

## Honesty rules for future phases

- A capability must not appear in `initialize.capabilities` until implemented.
- Inferred geometry must be labelled as inferred in the model and in the UI.
- No accuracy percentage may be published without a defined measurement method
  and a reproducible dataset.
