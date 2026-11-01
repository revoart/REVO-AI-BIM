# Phase 4 Completion Report — Scan Analysis Baseline

**Version:** 0.4.1  
**Date:** 2026-11-01  
**Status:** Implemented and automatically verified. Import Scan crash fixed and
verified in Revit 2027 with a real E57 scan; Scan Analysis manual verification is
still pending.

## 1. Scope delivered

Phase 4 adds a real Scan Analysis pipeline over the point cloud store. It is a
deterministic geometric baseline, not a trained neural network, and it creates
no Revit geometry.

| Capability | State |
| --- | --- |
| Global point sampling and optional voxel downsampling | Working, tested |
| RANSAC plane extraction | Working, tested |
| Floor / ceiling / wall / horizontal / sloped classification | Working, tested |
| Plane instance normal, offset, centroid, bounds and area | Working, tested |
| Plane-fit confidence with explicit meaning | Working, tested |
| Atomic `analysis/segmentation.json` result | Working, tested |
| `segmentation.run` / `segmentation.info` JSON-RPC methods | Working, tested |
| C# Scan Analysis stage and workspace metrics | Implemented, XAML probe passed |
| Trained ML segmentation | **Not implemented** |
| Doors, windows, furniture, columns, stairs, curves | **Not classified** |
| Revit geometry from analysis | **Not implemented** (Phase 5+) |

## 2. Method

```
point cloud store
  → global sample (default max 200,000 points)
  → optional voxel downsampling (default 0.05 m)
  → RANSAC plane extraction (Open3D)
  → classify by plane normal and centroid height
  → score plane fit, planarity, density, size and coverage
  → analysis/segmentation.json
```

- Planes with a near-vertical normal are walls; near-horizontal planes near the
  bottom of the cloud are floors, near the top are ceilings, and other
  horizontal/sloped planes are labelled honestly.
- Each element carries a plane normal/offset, centroid, bounds, area, point
  count, signals and confidence.
- Confidence is a **plane-fit quality score**, not dimensional accuracy:
  `0.35*planarity + 0.20*coverage + 0.20*density + 0.10*size + 0.15*fit`.
- The method string and note are stored in every result so downstream code
  cannot mistake the output for a trained-model accuracy claim.
- Analysis is deterministic: RANSAC seed is fixed.

## 3. Automated evidence

| Check | Result |
| --- | --- |
| Python tests | **57 passed** |
| .NET tests | **30 passed** |
| Revit 2026 Release build | **0 warnings, 0 errors** |
| Revit 2027 Release build | **0 warnings, 0 errors** |
| WPF probe (workspace, import, analysis, settings, about, 8 icons) | **Passed** |
| Real C# → Python segmentation run/info integration test | **Passed** |
| Synthetic room: floor, ceiling and four walls detected | **Passed** |
| Persisted result reload and typed not-found error | **Passed** |
| Engine smoke test advertises 0.4.0 capabilities | **Passed** |
| Import Scan opens without Revit termination (0.4.1 hotfix) | **Passed** |
| Unsupported `.rwcx` input returns a typed error, no crash | **Passed** |
| Real 27.8M-point E57 analysis (200k sample, 0.05 m voxel) | **Passed** |

Commands used:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
dotnet test tests\RevoAI.Revit.Tests\RevoAI.Revit.Tests.csproj -c Release -p:RevitVersion=2026
dotnet build src\RevoAI.Revit\RevoAI.Revit.csproj -c Release -p:RevitVersion=2026
dotnet build src\RevoAI.Revit\RevoAI.Revit.csproj -c Release -p:RevitVersion=2027
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\probe-ui.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke-engine.ps1
```

### Real-scan run (engine)

The verified Revit 2027 import was also analysed directly through the engine with
the default Scan Analysis settings:

| Value | Result |
| --- | --- |
| Source points | 27,802,731 |
| Sampled points | 198,591 |
| Points after 0.05 m voxel | 82,260 |
| Segments | 14 |
| Classes | 7 ceiling, 6 floor, 1 wall |
| Mean plane-fit confidence | 0.761 |
| Assigned-plane coverage | 90.2% |
| Engine time | 1.04 s |
| Result | `<store>/analysis/segmentation.json` |

This is a large multi-level/site scan spanning roughly 125 m x 130 m. Several
horizontal levels were labelled floor or ceiling from their height, confirming
the documented multi-storey limitation. The run proves the real engine, storage
and confidence path; the Scan Analysis stage still needs a manual UI check.

## 4. What is deliberately not claimed

- **No trained model.** The word "AI" in the product name does not turn this
  geometric baseline into a neural network.
- **No dimensional accuracy.** Confidence is a fit score. No measured accuracy
  figure exists because no BIM geometry has been created or compared.
- **No object detection beyond planar surfaces.** Doors, windows, furniture,
  columns, stairs and curved surfaces are not classified.
- **No room topology, multi-storey separation or element merging.** Coplanar
  walls can split into more than one instance when coverage has gaps; only the
  lowest and highest horizontal planes are called floor and ceiling.
- **No Revit output.** The result is JSON only.
- **No cancellation or progress percentage.** Analysis uses an indeterminate
  progress bar and a long request timeout.

## 5. Manual verification still required

0.4.1 is built and installed for Revit 2026 and 2027. The installed assemblies
match the Release outputs and report version `0.4.1.0`.

The Revit 2027 import path is verified with a real 27,802,731-point E57 scan
(21 chunks, colours and intensity). The remaining check is **Scan Analysis**:

1. Start Revit 2026/2027 with 0.4.1 installed.
2. Import a scan, then select the sidebar **2 Analyze scan** stage.
3. Run the defaults and confirm floor/ceiling/wall instances appear with
   confidence.
4. Confirm the workspace shows detected elements and mean confidence.
5. Confirm `analysis/segmentation.json` exists in the scan store.
6. Confirm no Revit geometry was created.
7. Repeat for the other Revit version.

Revit 2027 ribbon/workspace/import is verified. Revit 2026 and Scan Analysis manual checks remain pending.
