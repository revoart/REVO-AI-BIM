# Testing

## 1. Strategy

| Layer | Tool | What it proves |
| --- | --- | --- |
| C# unit | xUnit | Protocol serialization, version rules, configuration resolution |
| C# integration | xUnit + real Python process | Add-in can start, import/query, segment, create a reconstruction plan and stop the engine |
| Python unit | pytest | Protocol, units, readers, store, segmentation, reconstruction plan |
| Python process | pytest subprocess | The real stdio loop answers correctly and exits cleanly |
| Revit manual | Revit 2026/2027 | Ribbon, import, analysis, native floor/wall creation (Phase 2+) |
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

## 4. Coverage in Phases 1–5

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
- Ordered segmentation boundaries and reconstruction planning.
- Synthetic room plan: one level, one floor polygon and four wall lines.
- Real C# → Python `reconstruction.plan` round trip.
- Native floor/wall creation is build-tested but **not** yet verified inside
  Revit.

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

## 6. Manual Revit verification (Phases 2–5)

1. Build and install **0.5.0** for Revit 2026 and 2027.
2. Restart Revit. If Windows asks about the unsigned add-in, choose **Always
   Load**; choosing "Do Not Load" leaves the Revo tab absent.
3. Confirm the **REVO AI BIM** tab and all eight controls.
4. Open **Workspace**, refresh the project and create a test level.
5. Run **Test connection** and confirm the engine reports 0.5.0 and the
   reconstruction capability.
6. Open **Import Scan**, choose a small E57/LAS/PLY/XYZ file and import it.
7. Confirm the workspace shows the format, unit source, stored point count,
   chunk count, bounds and local store path.
8. Open **Scan Analysis**, keep the defaults and run it. Confirm segments and
   confidence, and that `analysis/segmentation.json` exists.
9. Open **Generate BIM**, keep the defaults and click **Create preview**.
10. Confirm levels, floors and walls appear in the preview with no model
    changes yet.
11. Click **Create in Revit**. Confirm native floors/walls appear, carry
    `REVO-INFERRED`, and that failure rolls back cleanly.
12. Repeat for Revit 2027.

Record the outcome in the phase reports. Native geometry creation must not be
marked verified until it has been observed in Revit.

## 7. Rules

- A test that silently does nothing is not a test. Soft skips must print why.
- Never mock the engine protocol in the integration test — use the real process.
- Accuracy claims require measured data and a described method.
