# Testing

## 1. Strategy

| Layer | Tool | What it proves |
| --- | --- | --- |
| C# unit | xUnit | Protocol serialization, version rules, configuration resolution |
| C# integration | xUnit + real Python process | Add-in can start, handshake, ping, import/query a scan, run segmentation and stop the engine |
| Python unit | pytest | Protocol models, dispatch rules, unit conversions, readers, preprocessing, store, segmentation |
| Python process | pytest subprocess | The real stdio loop answers correctly and exits cleanly |
| Revit manual | Revit 2026/2027 | Ribbon, workspace, settings, level creation, scan import and analysis (Phase 2+) |
| WPF probe | `scripts/probe-ui.ps1` | Windows and ribbon icons construct without Revit |

There is no Revit API automation in Phase 1. Revit-dependent behaviour is
verified manually and recorded in the phase report.

## 2. Commands

If script execution is blocked by policy, prefix with
`powershell -NoProfile -ExecutionPolicy Bypass -File`.

```powershell
# Everything
.\scripts\test.ps1

# .NET only
dotnet test tests\RevoAI.Revit.Tests\RevoAI.Revit.Tests.csproj

# Python only
.\.venv\Scripts\python.exe -m pytest -v

# Engine protocol smoke test
.\scripts\smoke-engine.ps1

# WPF window and icon construction (no Revit required)
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\probe-ui.ps1
```

## 3. Integration test behaviour

`EngineIntegrationTests` launches `.venv\Scripts\python.exe` and speaks the real
protocol. When the virtual environment is absent, the tests print
`SKIPPED: Python environment not found` and return without failing, so pure
.NET CI jobs remain green. The Python pytest suite is the authoritative check in
that case.

## 4. Coverage in Phases 1–4

Covered:

- Major-version compatibility, including malformed inputs.
- camelCase wire names in both languages.
- Typed error propagation (`-32011`, `-32601`, `-32700`, `-32600`, `-32020` to
  `-32026`).
- Initialize → ping → shutdown over a real process.
- Configuration precedence (environment > file > defaults).
- Engine root discovery and interpreter selection.
- Unit aliases and exact conversion factors (metre/foot/US survey foot/inch/mm/cm).
- E57, LAS, LAZ, PLY and XYZ readers with known synthetic coordinates.
- E57 multi-scan pose transforms.
- LAS/LAZ WKT unit detection and 16-bit colour scaling.
- Source-unit conversion and `sourceBounds` preservation.
- Statistical outlier removal and voxel downsampling counts.
- Chunked store round-trip and bounds/radius/nearest/sample queries.
- Real C# → Python `pointcloud.import` / `info` / `query` round trip.
- Typed file-not-found error across the real process boundary.
- Synthetic-room segmentation detects floor, ceiling and four wall planes.
- Segmentation confidence, planarity, area and persisted JSON result.
- `segmentation.run` / `segmentation.info` round trip and typed
  `ANALYSIS_NOT_FOUND`.
- Real C# → Python segmentation round trip.

Not covered (by design, later phases):

- Revit document transactions and element creation beyond levels.
- Real vendor E57 variants and RCP/RCS.
- Import streaming, cancellation and peak-memory behaviour.
- Trained-ML accuracy metrics and dimensional accuracy.
- Revit point-cloud rendering or BIM geometry.

## 5. Manual Revit verification (Phase 1)

1. Build and install for Revit 2026.
2. Launch Revit.
3. Confirm no add-in error dialog appears.
4. Confirm the log contains the startup and shutdown records.
5. Repeat for Revit 2027.

Record the outcome in `docs/phase-1-report.md`.

## 6. Manual Revit verification (Phases 2–4)

1. Build and install 0.4.0 for Revit 2026 and 2027.
2. Restart Revit so the new manifest is loaded.
3. Confirm the **REVO AI BIM** tab and all eight controls.
4. Open **Workspace**, refresh the project and create a test level.
5. Run **Test connection** and confirm the engine reports 0.4.0 and the point
   cloud plus segmentation capabilities.
6. Open **Import Scan**, choose a small E57/LAS/PLY/XYZ file and import it.
7. Confirm the workspace shows the format, unit source, stored point count,
   chunk count, bounds and local store path.
8. Open **Scan Analysis**, keep the defaults and run it.
9. Confirm the dialog lists floor/ceiling/wall instances with confidence and
   that the workspace shows detected elements and mean confidence.
10. Confirm no Revit geometry or point-cloud graphic was invented and that the
    analysis result file exists under `analysis/segmentation.json`.
11. Repeat for Revit 2027.

Record the outcome in `docs/phase-2-report.md`, `docs/phase-3-report.md` and
`docs/phase-4-report.md`.

## 7. Rules

- A test that silently does nothing is not a test. Soft skips must print why.
- Never mock the engine protocol in the integration test — use the real process.
- Accuracy claims require measured data and a described method.
