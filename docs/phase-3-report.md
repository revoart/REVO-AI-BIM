# Phase 3 Completion Report — Point Cloud Engine

**Version:** 0.3.0  
**Date:** 2026-11-01  
**Status:** Implemented and automatically verified. Real E57 import verified in
Revit 2027; Revit 2026 manual verification pending.

## 1. Scope delivered

Phase 3 turns a scan file into a local, queryable point cloud store without
pretending that reconstruction has happened.

| Capability | State |
| --- | --- |
| E57 import (all scans, pose transforms applied) | Working, tested |
| LAS import | Working, tested |
| LAZ import (lazrs backend) | Working, tested |
| PLY import (ASCII, binary little/big endian) | Working, tested |
| XYZ/TXT import (whitespace, comma or semicolon separated) | Working, tested |
| Unit detection and explicit override | Working, tested |
| Source coordinate preservation | Working, tested |
| Statistical outlier removal | Working, tested |
| Voxel downsampling | Working, tested |
| Chunked on-disk store with grid index | Working, tested |
| Bounds, radius and sample queries over JSON-RPC | Working, tested |
| Nearest-neighbour query | Working and tested at store level; not exposed over JSON-RPC yet |
| C# import dialog and workspace scan summary | Implemented, XAML probe passed |
| RCP/RCS import | **Not implemented** |
| Revit point-cloud preview or geometry | **Not implemented** (Phase 4/5) |
| Import progress percentage and cancellation | **Not implemented** |

## 2. Pipeline

```
scan file
  → format reader (E57 / LAS / LAZ / PLY / XYZ)
  → source unit resolution
  → optional statistical outlier removal
  → optional voxel downsampling
  → one explicit conversion to metres
  → 3D-grid chunking
  → metadata.json + chunks/*.npz
  → bounds / radius / sample queries (nearest is store-level)
```

### Units

- Canonical engine unit: metre.
- E57: metres by specification (`unitSource = format`).
- LAS/LAZ: a length unit is read from a WKT CRS VLR when present
  (`unitSource = header`); otherwise metres are assumed and a warning is
  returned (`unitSource = assumed`).
- PLY/XYZ: no reliable unit metadata; metres are assumed and a warning is
  returned unless the user selects a unit (`unitSource = user`).
- Supported explicit units: millimetres, centimetres, metres, inches, feet and
  US survey feet.
- `sourceBounds` is stored in source units; `bounds` is stored in metres. No
  recentring or rotation is performed.

### Storage

Each scan is written to its own folder:

```
<output>/<scanId>/
├─ metadata.json
└─ chunks/
   ├─ chunk_00000.npz
   └─ ...
```

Each chunk stores a float64 `origin` and float32 offsets, plus optional
`colors` (uint8), `intensity` (float32) and `classification` (uint8). The
metadata contains the 3D cell grid, so a query opens only chunks whose cells can
intersect the request. Chunk size defaults to 25 m and is configurable.

### Protocol

New methods, advertised in `initialize.capabilities`:

- `pointcloud.import`
- `pointcloud.info`
- `pointcloud.query`

Protocol version remains `1.0`; these are additive methods. Import is
synchronous and the C# client allows up to 30 minutes for it.

## 3. Automated evidence

| Check | Result |
| --- | --- |
| Python tests | **54 passed** |
| .NET tests | **27 passed** |
| Revit 2026 Release build | **0 warnings, 0 errors** |
| Revit 2027 Release build | **0 warnings, 0 errors** |
| WPF probe (workspace, import, settings, about, 8 icons) | **Passed** |
| Real C# → Python import/info/query integration test | **Passed** |
| Real XYZ import with chunk/query verification | **Passed** |
| Real E57 read + multi-scan pose transform test | **Passed** |
| Real LAS/LAZ read test | **Passed** |
| ASCII and binary PLY read tests | **Passed** |
| Unit preservation test (mm source → m engine) | **Passed** |
| Statistical outlier and voxel count tests | **Passed** |

Test commands used:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
dotnet test tests\RevoAI.Revit.Tests\RevoAI.Revit.Tests.csproj -c Release -p:RevitVersion=2026
dotnet build src\RevoAI.Revit\RevoAI.Revit.csproj -c Release -p:RevitVersion=2026
dotnet build src\RevoAI.Revit\RevoAI.Revit.csproj -c Release -p:RevitVersion=2027
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\probe-ui.ps1
```

## 4. What is deliberately not claimed

- **No real scanner E57 was used.** E57 tests use files written by `pye57` with
  known coordinates, colours, intensity and a translated second scan. This
  proves the reader and pose handling, not every vendor's E57 variant.
- **No RCP/RCS support.** Those require a verified Autodesk workflow and are not
  silently accepted.
- **No import streaming.** Readers currently load the source cloud before
  chunking. The store and queries are chunked, but peak import memory still
  scales with the source file. Large-scan streaming belongs to Phase 9.
- **No cancellation or progress percentage.** The UI shows an indeterminate
  progress bar and the engine returns only when finished.
- **No CRS reprojection.** Coordinates are preserved as found. A projected CRS
  is not transformed into a project coordinate system.
- **No point-cloud display in Revit.** The workspace shows import metadata only.
- **No accuracy claim.** Nothing has been reconstructed or measured yet.

## 5. Manual verification

**Revit 2027: passed.** The product owner opened the ribbon, Workspace and Import
Scan dialog and imported a real E57 scan:

- source: `gargage.e57`
- format/unit: E57, metres (`unitSource = format`)
- points: **27,802,731** stored
- chunks: **21**
- attributes: colours and intensity
- import time: **12.6 s**
- result: workspace loaded the scan store without a Revit error

The engine connection test also reported `0.4.1` add-in / `0.4.0` engine with
point-cloud and segmentation capabilities.

**Revit 2026 still needs the same manual check.** Open the ribbon, run the engine
test, import an E57/LAS/LAZ/PLY/XYZ scan and confirm the workspace summary. Report
any error dialog or unexpected value.