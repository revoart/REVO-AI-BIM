# Development Guide

## 1. Prerequisites

Verified on the reference machine (see [docs/environment.md](docs/environment.md)):

| Tool | Version |
| --- | --- |
| Windows | 11 Pro 26200, x64 |
| .NET SDK | 10.0.401 |
| .NET runtimes | 8.0.x, 10.0.x (Revit 2026/2027 host .NET 10) |
| Python | 3.14.7 (`py -3.14`) |
| Git | 2.55.0 |
| Visual Studio | 2026 Community 18.10.3 (optional) |
| Revit | 2026 (26.5.0.55), 2027 (27.0.4.412) |

Revit 2025 is not installed. Building for it is untested.

## 2. First-time setup

```powershell
cd revo-ai-bim
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.in
.\.venv\Scripts\python.exe -m pip install -e src\RevoAI.Engine -e src\RevoAI.Geometry
dotnet build RevoAI.slnx -p:RevitVersion=2026
```

Or simply:

```powershell
.\scripts\bootstrap.ps1
```

If PowerShell blocks scripts (`running scripts is disabled on this system`), run
them explicitly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
```

Do not weaken the machine-wide policy just for this repository.

The virtual environment is git-ignored. Python packages are installed editable,
so source changes take effect without reinstalling.

## 3. Build matrix

```powershell
# Revit 2026 (default)
dotnet build RevoAI.slnx -p:RevitVersion=2026

# Revit 2027
dotnet build RevoAI.slnx -p:RevitVersion=2027

# Both, via script
.\scripts\build.ps1 -RevitVersion all -Configuration Release
```

Outputs:

- `src/RevoAI.Revit/bin/Debug/2026/RevoAI.Revit.dll`
- `src/RevoAI.Revit/bin/Debug/2027/RevoAI.Revit.dll`

Revit DLLs are referenced with `Private=false`; they are never copied.

### Adding another Revit version

1. Add the install path and target framework mapping in
   `Directory.Build.props`. Confirm the host runtime by reading
   `RevitAPI.runtimeconfig.json` in the Revit install folder — do not assume.
2. Build with `-p:RevitVersion=<year>`.
3. Extend `scripts/install-addin.ps1` `ValidateSet`.
4. Record the result in `docs/environment.md`.

## 4. Tests

```powershell
dotnet test tests\RevoAI.Revit.Tests\RevoAI.Revit.Tests.csproj
.\.venv\Scripts\python.exe -m pytest
```

The .NET integration tests start the real Python engine and require `.venv`.
If it is missing they report `SKIPPED` in the test output instead of failing.

## 5. Running the engine manually

```powershell
$env:PYTHONPATH="$PWD\src\RevoAI.Engine;$PWD\src\RevoAI.Geometry"
'{"jsonRpc":"2.0","id":"1","method":"ping"}' | .\.venv\Scripts\python.exe -m revoai_engine.service
```

Or `.\scripts\smoke-engine.ps1`.

## 6. Checking the UI without Revit

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\probe-ui.ps1
```

This builds a throwaway WPF host that constructs the workspace, settings and
about windows and loads all eight ribbon icons through their pack URIs. It
catches XAML/resource regressions but does not exercise Revit API behaviour.

## 7. Loading the add-in in Revit

```powershell
.\scripts\build.ps1 -RevitVersion 2026
.\scripts\install-addin.ps1 -RevitVersion 2026
```

Start Revit. The **REVO AI BIM** tab appears. Open **Workspace** to see project
information, levels, settings and the engine connection test. The install script
writes `%APPDATA%\RevoAI\config.json` (if absent) so the workspace can start the
repository `.venv` engine.

To remove: `.\scripts\uninstall-addin.ps1 -RevitVersion 2026`.

## 8. Coding standards

- Nullable reference types are enabled; warnings are treated as defects.
- Revit-free code lives in `Configuration/`, `Logging/`, `Engine/` so it can be
  tested outside Revit (the test project links those folders).
- Do not reference `Autodesk.Revit.*` from `RevoAI.Contracts` or Python.
- Every public behaviour needs a test. A feature is not "done" because it
  compiles.
- JSON field names are camelCase on both sides; change both sides together and
  bump the protocol version.
- Never commit scan data, models or credentials.

## 8. Repository hygiene

This repository currently lives under a OneDrive-synced folder. OneDrive can
lock `bin/obj` during builds and sync large scan files. For heavy Phase 3 work,
move the repository to a local, non-synced disk (for example `C:\Dev`) and
re-open the workspace there.
