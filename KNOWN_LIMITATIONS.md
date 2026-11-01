# Known Limitations

This file is deliberately blunt. Anything listed here is **not working** or
**not verified**, regardless of what other documents imply.

## Product scope (current)

1. **Import and Scan Analysis work; reconstruction commands are still shells.**
   E57, LAS, LAZ, PLY and XYZ/TXT scans can be imported, and Scan Analysis runs
   the geometric segmentation baseline. Generate BIM, Model Review and Quality
   Check still show honest "not implemented" dialogs. The only model-changing
   action is creating levels.
2. **No RCP/RCS support.** Those formats require a verified Autodesk workflow
   and are not accepted by the importer.
3. **No point-cloud display in Revit.** The workspace shows import and analysis
   metadata; it does not draw points, meshes or placeholder geometry.
4. **No trained ML.** Scan Analysis is a deterministic geometric RANSAC
   baseline. There is no neural network, training dataset or learned model.
5. **Limited BIM reconstruction.** Phase 5 can create native floors and walls
   from the geometric plan, marked `REVO-INFERRED`. Doors, windows, ceilings,
   furniture, stairs and curved surfaces are not created. This still needs a
   manual in-Revit check.
6. **No accuracy figures.** No reconstructed element has been compared against
   measured ground truth. Plane-fit confidence is not dimensional accuracy.
7. **No import streaming or cancellation.** Readers load the source cloud
   before chunking, so peak memory scales with the source file. The UI shows an
   indeterminate progress bar, and the engine has no cancel request. Phase 9.
8. **No CRS reprojection.** Coordinates are preserved as found; a projected CRS
   is not transformed into a project coordinate system.
9. **Unit assumptions are explicit.** E57 is metres by specification. LAS/LAZ
   uses a WKT CRS unit when present, otherwise metres are assumed. PLY/XYZ have
   no reliable unit metadata, so metres are assumed unless the user selects a
   unit. Warnings are returned and shown in the UI.
10. **Vendor E57 variants are not covered.** E57 tests use files written by
    `pye57`; they prove the reader and pose handling, not every scanner export.

## Scan Analysis limits (Phase 4)

- The baseline detects planar instances only: floors, ceilings, walls and other
  dominant planes. Doors, windows, furniture, columns, stairs and curved
  surfaces are not classified.
- It has no room topology, no multi-storey separation, no surface merging into
  building elements and no model coordinates yet. Only the lowest and highest
  horizontal planes are called floor and ceiling; intermediate levels are
  labelled `horizontal`.
- A plane may be split into multiple instances when a coplanar surface has gaps
  or different sampling density. No merge step exists yet.
- Confidence combines planarity, sampling density, size, coverage and fit error.
  It is a fit-quality score, not an accuracy or acceptance guarantee.
- Analysis is limited by `maxPoints` and optional voxel downsampling; low-density
  or very large scans can miss small surfaces.
- The result is written to `analysis/segmentation.json`; it is not imported into
  Revit and does not create geometry.

## Generate BIM limits (Phase 5)

- Floors are created from convex-hull plane boundaries. Concave rooms, courtyard
  cut-outs and L-shaped spaces are oversimplified.
- One wall line is derived from the longest boundary extent of each wall plane.
  Coplanar wall fragments are not merged.
- Default project floor and wall types are used. The requested wall thickness is
  not applied because Revit wall type width is not instance-editable.
- Ceilings are used only to determine wall height when a ceiling is available;
  ceiling geometry is not created.
- Levels are clustered by floor elevation. Multi-storey scans can produce
  questionable levels and floor/ceiling assignments.
- Creation happens in one transaction. Any Revit geometry failure rolls back the
  whole batch.
- The generated elements are labelled `REVO-INFERRED`; they are not a measured
  as-built guarantee.

## Environment and compatibility

11. **Revit 2025 is not installed or tested.** The `net8.0-windows` mapping in
    `Directory.Build.props` is a hypothesis, not a verified build.
12. **Revit 2026/2027 use .NET 10**, not .NET 8 as originally assumed. The add-in
    targets `net10.0-windows`. Do not copy .NET 8 build recipes from older Revit
    documentation.
13. **Python 3.14 only.** Older Python versions are not tested. Open3D 0.20.0,
    `pye57` 0.4.19 and `laspy` 2.7.0 are the verified cp314 wheels.
14. **Windows only.** No macOS or Linux support is planned for the add-in.

## Engineering

15. **The engine is a child process over stdio.** If the add-in crashes without
    disposing the client, the engine process may survive until the OS cleans it
    up. A supervisor/watchdog arrives in Phase 9.
16. **One engine process per add-in session, single-threaded.** No concurrent
    jobs. Long-running jobs and cancellation are not implemented yet.
17. **No installer.** `install-addin.ps1` is a developer script that writes to
    `%APPDATA%`. Phase 10 replaces it with a signed installer.
18. **No licensing, telemetry, onboarding or support workflow.** Phase 10.
19. **No code signing.** Windows and Revit may warn about unsigned assemblies.
20. **OneDrive workspace.** The repository currently sits in a OneDrive folder;
    this can cause file locks and sync churn. Move to local disk for large scans.
21. **No CI pipeline yet.** Tests are run locally via `scripts\test.ps1`.
22. **Nearest-neighbour search is not exposed over JSON-RPC.** It is implemented
    and tested in `PointCloudStore.nearest`, but `pointcloud.query` currently
    supports bounds, radius and sample modes only.

## Honesty rules for future phases

- A capability must not appear in `initialize.capabilities` until implemented.
- Inferred geometry must be labelled as inferred in the model and in the UI.
- No accuracy percentage may be published without a defined measurement method
  and a reproducible dataset.
