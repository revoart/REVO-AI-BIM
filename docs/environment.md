# Environment Inspection — 2026-10-31

All values below were read from the machine, not assumed.

## Hardware

| Item | Value |
| --- | --- |
| OS | Windows 11 Pro, build 26200, 64-bit |
| CPU | Intel Core i9-13900H, 14 cores / 20 logical processors |
| RAM | 31.7 GB |
| Disk | C: 373.8 GB free; F: 915.2 GB free |

## Autodesk Revit

| Version | Install path | Revit.exe | RevitAPI.dll |
| --- | --- | --- | --- |
| 2026 | `C:\Program Files\Autodesk\Revit 2026` | 26.5.0.55 | 26.5.0.55 |
| 2027 | `C:\Program Files\Autodesk\Revit 2027` | 27.0.4.412 | 27.0.4.412 |
| 2025 | **not installed** | — | — |

Revit add-in manifest folders exist for 2020–2027 under
`%APPDATA%\Autodesk\Revit\Addins`.

### Critical finding: runtime is .NET 10

`RevitAPI.runtimeconfig.json` for **both** 2026 and 2027 declares:

```json
"tfm": "net10.0",
"frameworks": [
  { "name": "Microsoft.NETCore.App", "version": "10.0.0" },
  { "name": "Microsoft.WindowsDesktop.App", "version": "10.0.0" }
]
```

Therefore the add-in targets `net10.0-windows`. The original plan assumed .NET 8
for Revit 2025/2026; that assumption does not hold on this machine.

## .NET

- SDK: **10.0.401** (only SDK installed).
- Runtimes: 8.0.21, 8.0.29, 10.0.9, 10.0.12 (plus 6.0/3.1).
- `net8.0-windows` compilation was probed successfully (reference packs restore
  from NuGet), so a future Revit 2025 build is technically possible without
  installing the .NET 8 SDK.
- Visual Studio Community 2026 18.10.3 is installed.

## Python

- Only interpreter: **3.14.7** via the `py` launcher
  (`C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64`).
- pip 26.2.1.
- Wheel availability verified by download:
  - `open3d 0.20.0` — `cp314-cp314-win_amd64` (75.7 MB).
  - `laspy 2.7.0` — pure Python.
  - `lazrs 0.8.2` — `cp314-cp314-win_amd64`.
  - `pye57 0.4.19` — `cp314-cp314-win_amd64` (with `pyquaternion 0.9.9`).
- Project virtual environment: `.venv` (Python 3.14), dependencies pinned in
  `requirements.in` / `requirements-dev.in` and resolved in
  `requirements.lock.txt`.

## Git

- Git 2.55.0.windows.3.
- Repository initialized on branch `main` at
  `C:\Users\Admin\OneDrive\Documents\Default Project\revo-ai-bim`.

## Notes and risks

1. The repository is inside OneDrive. Build outputs are git-ignored, but
   OneDrive may still lock files. Large scans should live outside OneDrive.
2. No Revit 2025 means Phase 2 manual verification can only cover 2026 and 2027.
3. Open3D is installed for Phase 3; Phase 1 does not import it at runtime.
4. The `py` launcher requires an explicit `-3.14`; the client handles this
   automatically.
