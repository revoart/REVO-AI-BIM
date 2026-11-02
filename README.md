# Revo AI BIM

AI-assisted Scan-to-BIM for Autodesk Revit, developed by **RevoStudioz**.

Revo AI BIM converts laser-scanned buildings into editable, native Revit
elements. The product is built in ten gated phases; each phase is implemented,
tested and reviewed before the next begins.

> **Current status: AI schedule prototype with a visible step-by-step Revit
> build. The portrait tool has three steps: Scan, Analyse and Build. Claude
> (preferred when a key is configured) or DeepSeek Go generates a measured
> schedule from plan/elevation snapshots, then Revit commits levels, slabs,
> walls, hosted doors/windows, roofs and columns stage by stage so the user can
> watch the model appear. The Knowledge Library is permanently removed from the
> customer UI.**
>
> This is not a trained neural network. Revit shows a sampled **point-cloud
> reference** made of model markers, not a native RCP/RCS scan; it is a visual
> aid, not measured point data. Generated geometry is inferred from the scan and
> schedule, not a measured accuracy guarantee. Native generation is blocked when
> the unit is assumed, floors are missing, or the floor/level result is
> incoherent. Approved knowledge can guide the AI in the backend, but scan
> evidence remains authoritative.

## What exists today

| Area | Status |
| --- | --- |
| Repository, build system, versioning | Done |
| Revit 2026 / 2027 add-in builds (.NET 10) | Done, builds verified |
| REVO AI BIM ribbon tab with 10 controls | Done, builds; in-Revit check pending |
| Modeless WPF workspace | Done, XAML construction verified |
| Settings window writing real config | Done, tested |
| Native Revit level creation (transaction + ExternalEvent) | Done, builds; in-Revit check pending |
| C# ↔ Python engine protocol (JSON-RPC 2.0 over stdio) | Done, tested end to end |
| Python engine process (`initialize`, `ping`, `shutdown`) | Done, tested |
| E57 / LAS / LAZ / PLY / XYZ point cloud import | Done, tested with synthetic files |
| Unit detection, explicit override and source-coordinate preservation | Done, tested |
| Outlier removal and voxel downsampling | Done, tested |
| Chunked point cloud store and spatial queries | Done, tested |
| Real Import Scan stage and workspace scan summary | Done, XAML probe passed; in-Revit check pending |
| Geometric floor/ceiling/wall segmentation with confidence | Done, tested with synthetic rooms |
| Real Scan Analysis stage and workspace metrics | Done, XAML probe passed; in-Revit check pending |
| Reconstruction plan with levels, floor polygons and wall lines | Done, tested |
| Native Revit floor and wall creation with inferred-element marking | Implemented; manual in-Revit check pending |
| Model-visible point-cloud reference with show/hide control | Known issue: Revit 2027 tessellation build fails; line fallback unverified |
| Native build safety gate (units, floors, coherence) | Implemented; blocks unreliable plans |
| Native slabs, walls, hosted doors/windows and flat roofs | Implemented; Revit 2027 builder probe passed |
| Visible stage-by-stage AI build with progress | Implemented; commits levels, slabs, walls, openings, roofs and columns separately |
| Claude or DeepSeek Go AI schedule from plan/elevation snapshots | Implemented; live API not tested without a key |
| Local knowledge library (SQLite + FTS5, provenance, review, backup/export) | Backend only; permanently removed from the customer UI |
| Unit conversion kernel (metres ↔ feet ↔ mm/in/US survey feet) | Done, tested |
| Structured logging, configuration, error model | Done |
| Trained ML, doors/windows, native RCP/RCS point-cloud import | **Not started** |

## Repository layout

```
revo-ai-bim/
├─ src/
│  ├─ RevoAI.Contracts/     C# DTOs and protocol constants (net8.0, no Revit deps)
│  ├─ RevoAI.Revit/         Revit add-in (net10.0-windows, WPF enabled)
│  ├─ RevoAI.Engine/        Python engine package (revoai_engine)
│  └─ RevoAI.Geometry/      Python geometry package (revoai_geometry)
├─ local_knowledge/         Seed catalog; runtime data lives in %LOCALAPPDATA%
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
If Revit shows **Security - Unsigned Add-In**, choose **Always Load**; **Do Not
Load** hides the add-in.
Open **Workspace** to see the project, levels, settings and engine test, or use
**Import Scan** to import an E57, LAS/LAZ, PLY or XYZ file into a local chunked
store. Imported scans are not yet drawn in Revit; the workspace reports the
stored point count, chunk count, bounds and store path. **Scan Analysis** then
runs the geometric plane baseline and reports detected floors, ceilings and
walls with plane-fit confidence. Use the sidebar to move through **Import scan →
Analyze scan → Generate BIM** without leaving the Workspace. Generate BIM
previews native floors and walls and creates them in one Revit transaction after
confirmation. Created elements are marked `REVO-INFERRED`; no geometry is created
until the user clicks **Create in Revit**.

The Build stage prefers **Claude** when `ANTHROPIC_API_KEY` is configured, and
otherwise uses **DeepSeek Go**. Set the key before starting Revit. The engine
generates plan and elevation depth snapshots, sends them with measured metadata,
validates the returned schedule and only then builds native slabs, walls, hosted
doors/windows and roofs. The Claude key is used only for schedule generation and
is never logged. Force a provider with `REVOAI_AI_PROVIDER=claude|deepseek`. See
[docs/scan-to-bim-agent.md](docs/scan-to-bim-agent.md),
[docs/external-bim-plan.md](docs/external-bim-plan.md) and
[docs/subscription-architecture.md](docs/subscription-architecture.md).

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
- [docs/external-bim-plan.md](docs/external-bim-plan.md) - External AI BIM plan JSON contract
- [docs/subscription-architecture.md](docs/subscription-architecture.md) - Revo-managed Astra subscription architecture
- [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) — what does not work yet

## License

Proprietary. Copyright © 2026 RevoStudioz. All rights reserved.
