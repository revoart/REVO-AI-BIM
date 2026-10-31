# Revo AI BIM

AI-assisted Scan-to-BIM for Autodesk Revit, developed by **RevoStudioz**.

Revo AI BIM converts laser-scanned buildings into editable, native Revit
elements. The product is built in ten gated phases; each phase is implemented,
tested and reviewed before the next begins.

> **Current status: Phase 2 (Revit plugin interface) — implemented. The ribbon,
> workspace, settings and engine diagnostics build and pass automated checks.
> Manual in-Revit verification of the ribbon is pending. Point cloud import, AI
> and BIM generation are still not implemented.**
>
> There is no point cloud import, AI detection, or BIM generation yet. Nothing
> in this repository claims otherwise.

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
| Unit conversion kernel (metres ↔ feet ↔ mm/in) | Done, tested |
| Structured logging, configuration, error model | Done |
| Scan import, AI, reconstruction | **Not started** |

## Repository layout

```
revo-ai-bim/
├─ src/
│  ├─ RevoAI.Contracts/     C# DTOs and protocol constants (net8.0, no Revit deps)
│  ├─ RevoAI.Revit/         Revit add-in (net10.0-windows, WPF enabled)
│  ├─ RevoAI.Engine/        Python engine package (revoai_engine)
│  └─ RevoAI.Geometry/      Python geometry package (revoai_geometry)
├─ tests/
│  ├─ RevoAI.Revit.Tests/   xUnit: protocol, config, real engine process
│  ├─ RevoAI.Engine.Tests/  pytest: protocol, dispatch, stdio round trip
│  └─ RevoAI.Geometry.Tests/pytest: unit conversions
├─ docs/                    Architecture, ADRs, environment, phase report
├─ scripts/                 Bootstrap, build, test, add-in install, smoke test
├─ models/                  Trained model artifacts (empty until Phase 4)
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
Open **Workspace** to see the project, levels, settings and engine test.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — components, boundaries, protocol
- [DEVELOPMENT.md](DEVELOPMENT.md) — setup, build matrix, debugging
- [ROADMAP.md](ROADMAP.md) — the ten phases and their gates
- [TESTING.md](TESTING.md) — test strategy and evidence
- [docs/environment.md](docs/environment.md) — inspected machine facts
- [docs/phase-1-report.md](docs/phase-1-report.md) - Phase 1 completion report
- [docs/phase-2-report.md](docs/phase-2-report.md) - Phase 2 completion report
- [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) — what does not work yet

## License

Proprietary. Copyright © 2026 RevoStudioz. All rights reserved.
