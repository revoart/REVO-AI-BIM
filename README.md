# Revo AI BIM

AI-assisted Scan-to-BIM for Autodesk Revit, developed by **RevoStudioz**.

Revo AI BIM converts laser-scanned buildings into editable, native Revit
elements. The product is built in ten gated phases; each phase is implemented,
tested and reviewed before the next begins.

> **Current status: Phase 5 - implemented. E57, LAS, LAZ, PLY and XYZ/TXT scans
> can be imported, analysed into floor/ceiling/wall instances, and converted
> into a previewable plan for native Revit floors and walls. A real
> 27.8-million-point E57 import is verified in Revit 2027; native geometry
> creation and the Scan Analysis UI still need manual in-Revit verification.**
>
> This is not a trained neural network and there is no Revit point-cloud preview
> yet. Generated floors and walls are inferred from a deterministic geometric
> baseline, not measured accuracy.

## What exists today

| Area | Status |
| --- | --- |
| Repository, build system, versioning | Done |
| Revit 2026 / 2027 add-in builds (.NET 10) | Done, builds verified |
| REVO AI BIM ribbon tab with 8 controls | Done, builds; in-Revit check pending |
| Modeless WPF workspace | Done, XAML construction verified |
| Settings window writing real config | Done, tested |
| Native Revit level creation (transaction + ExternalEvent) | Done, builds; in-Revit check pending |
| C# ↔ Python engine protocol (JSON-RPC 2.0 over stdio) | Done, tested end to end |
| Python engine process (`initialize`, `ping`, `shutdown`) | Done, tested |
| E57 / LAS / LAZ / PLY / XYZ point cloud import | Done, tested with synthetic files |
| Unit detection, explicit override and source-coordinate preservation | Done, tested |
| Outlier removal and voxel downsampling | Done, tested |
| Chunked point cloud store and spatial queries | Done, tested |
| Real Import Scan dialog and workspace scan summary | Done, XAML probe passed; in-Revit check pending |
| Geometric floor/ceiling/wall segmentation with confidence | Done, tested with synthetic rooms |
| Real Scan Analysis dialog and workspace metrics | Done, XAML probe passed; in-Revit check pending |
| Reconstruction plan with levels, floor polygons and wall lines | Done, tested |
| Native Revit floor and wall creation with inferred-element marking | Implemented; manual in-Revit check pending |
| Unit conversion kernel (metres ↔ feet ↔ mm/in/US survey feet) | Done, tested |
| Structured logging, configuration, error model | Done |
| Trained ML, doors/windows, Revit point-cloud preview | **Not started** |

## Repository layout

```
revo-ai-bim/
├─ src/
│  ├─ RevoAI.Contracts/     C# DTOs and protocol constants (net8.0, no Revit deps)
│  ├─ RevoAI.Revit/         Revit add-in (net10.0-windows, WPF enabled)
│  ├─ RevoAI.Engine/        Python engine package (revoai_engine)
│  └─ RevoAI.Geometry/      Python geometry package (revoai_geometry)
├─ tests/
│  ├─ RevoAI.Revit.Tests/   xUnit: protocol, config, real engine process, analysis and reconstruction client
│  ├─ RevoAI.Engine.Tests/  pytest: protocol, point cloud, segmentation, reconstruction plan
│  └─ RevoAI.Geometry.Tests/pytest: unit conversions
├─ docs/                    Architecture, ADRs, environment, phase report
├─ scripts/                 Bootstrap, build, test, add-in install, smoke test
├─ models/                  Trained model artifacts (empty; Phase 4 baseline uses no weights)
├─ samples/                 Local scan fixtures (never committed)
└─ installers/              Installer sources (empty until Phase 10)
```

## Prerequisites (verified on the reference machine)

- Windows 11 64-bit
- Autodesk Revit **2026** and/or **2027**
- .NET SDK **10.0.401** (Revit 2026/2027 host .NET 10)
- Python **3.14** with the `py` launcher
- Git
- Visual Studio 2022/2026 or Build Tools (optional; `dotnet` CLI is enough)

Revit 2025 is **not installed** here. Its `net8.0-windows` mapping exists in
`Directory.Build.props` but is unverified.

## Quick start

```powershell
cd revo-ai-bim
.\scripts\bootstrap.ps1 -RevitVersion 2026
.\scripts\test.ps1
```

Build both installed Revit versions:

```powershell
.\scripts\build.ps1 -RevitVersion all
```

Run the engine protocol smoke test without Revit:

```powershell
.\scripts\smoke-engine.ps1
```

Check that all windows and ribbon icons construct correctly (no Revit needed):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\probe-ui.ps1
```

Install the developer add-in:

```powershell
.\scripts\build.ps1 -RevitVersion 2026
.\scripts\install-addin.ps1 -RevitVersion 2026
```

Then start Revit: the **REVO AI BIM** tab appears with Workspace, Import Scan,
Scan Analysis, Generate BIM, Model Review, Quality Check, Settings and About.
Open **Workspace** to see the project, levels, settings and engine test, or use
**Import Scan** to import an E57, LAS/LAZ, PLY or XYZ file into a local chunked
store. Imported scans are not yet drawn in Revit; the workspace reports the
stored point count, chunk count, bounds and store path. **Scan Analysis** then
runs the geometric plane baseline and reports detected floors, ceilings and
walls with plane-fit confidence. **Generate BIM** then previews a plan of native
floors and walls and creates them in one Revit transaction after confirmation.
Created elements are marked `REVO-INFERRED`; no geometry is created until the
user clicks **Create in Revit**.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — components, boundaries, protocol
- [DEVELOPMENT.md](DEVELOPMENT.md) — setup, build matrix, debugging
- [ROADMAP.md](ROADMAP.md) — the ten phases and their gates
- [TESTING.md](TESTING.md) — test strategy and evidence
- [docs/environment.md](docs/environment.md) — inspected machine facts
- [docs/phase-1-report.md](docs/phase-1-report.md) - Phase 1 completion report
- [docs/phase-2-report.md](docs/phase-2-report.md) - Phase 2 completion report
- [docs/phase-3-report.md](docs/phase-3-report.md) - Phase 3 completion report
- [docs/phase-4-report.md](docs/phase-4-report.md) - Phase 4 completion report
- [docs/phase-5-report.md](docs/phase-5-report.md) - Phase 5 completion report
- [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) — what does not work yet

## License

Proprietary. Copyright © 2026 RevoStudioz. All rights reserved.
