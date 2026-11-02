# Architecture

## 1. System context

```
┌──────────────────────────────┐        ┌──────────────────────────────────┐
│ Autodesk Revit 2026 / 2027   │        │ Revo AI BIM Python engine        │
│ (.NET 10 host)               │        │ (separate process, Python 3.14)  │
│                              │        │                                  │
│  RevoAI.Revit.dll            │ stdio  │  revoai_engine.service           │
│   ├─ ribbon / WPF (Phase 2)  │◄──────►│   ├─ point cloud ingest (Ph. 3)  │
│   ├─ Revit transactions      │ JSON-  │   ├─ AI inference      (Ph. 4)   │
│   └─ PythonEngineClient      │ RPC    │   └─ reconstruction    (Ph. 5+)  │
│                              │        │                                  │
│  RevitAPI / RevitAPIUI       │        │  revoai_geometry                 │
└──────────────────────────────┘        └──────────────────────────────────┘
```

Hard boundary: **Revit API objects never cross into Python.** Python receives
files, coordinates and parameters; it returns plain data (element descriptions,
confidence, geometry primitives). The C# side owns every Revit transaction.

## 2. Projects

| Project | TFM | Responsibility |
| --- | --- | --- |
| `RevoAI.Contracts` | `net8.0` | Wire DTOs, protocol version, error codes, JSON settings. No Revit or Windows dependency, so it is reusable by a future Revit 2025 build. |
| `RevoAI.Revit` | `net10.0-windows` | Add-in entry point, configuration, logging, engine process client, ribbon and single-window staged WPF workspace. |
| `RevoAI.Engine` | Python ≥3.11 | Local processing service: transport, point cloud, spatial queries, segmentation baseline and reconstruction planning. |
| `RevoAI.Geometry` | Python ≥3.11 | Unit kernel and, in later phases, reconstruction algorithms. |

## 3. Transport and protocol

**Decision:** newline-delimited JSON-RPC 2.0 over the child process's
stdin/stdout. See [ADR 0002](adr/0002-engine-ipc.md).

- One JSON object per line; UTF-8; no embedded newlines.
- Request `id` is a string. Responses echo it. Notifications have no `id` and
  are currently ignored by the client (reserved for progress events).
- Methods: `initialize`, `ping`, `shutdown`, `pointcloud.import`,
  `pointcloud.info`, `pointcloud.query`, `segmentation.run`,
  `segmentation.info`, `reconstruction.plan`.
- Major protocol version must match (`1.x` accepted). Mismatch returns
  `-32010`.
- Methods other than `ping`/`shutdown` require `initialize` first (`-32011`).
- Unknown methods return `-32601`; malformed JSON returns `-32700`.
- `stderr` is a log channel only, never protocol data.

Capabilities are reported explicitly by `initialize`; the engine must never
advertise a method it does not implement.

## 4. Process lifecycle

1. The add-in resolves the engine root and interpreter from `RevoConfig`.
2. It starts `python -m revoai_engine.service` with `PYTHONPATH` pointing at
   the two Python packages.
3. It performs `initialize` with a startup timeout.
4. Requests are serialized by a `SemaphoreSlim`; the engine is single-threaded.
5. Shutdown sends `shutdown`, waits up to 5 s, then kills the process tree.
6. Engine crashes surface as `RevoAIEngineException` (`-32012`) including the
   tail of stderr.

## 5. Configuration

`%APPDATA%\RevoAI\config.json` (camelCase):

```json
{
  "pythonExecutable": "C:\\Path\\to\\python.exe",
  "engineRoot": "C:\\Path\\to\\revo-ai-bim",
  "startupTimeoutSeconds": 60,
  "requestTimeoutSeconds": 120
}
```

Environment overrides: `REVOAI_PYTHON`, `REVOAI_ENGINE_ROOT`,
`REVOAI_LOG_DIR`. An empty `pythonExecutable` auto-selects
`<engineRoot>\.venv\Scripts\python.exe`, falling back to the `py` launcher with
`-3.14`.

## 6. Logging

- Add-in: JSON Lines at `%LOCALAPPDATA%\RevoAI\logs\revoai-YYYYMMDD.log`.
- Engine: human-readable lines on stderr, mirrored to
  `<logDirectory>\engine-YYYYMMDD.log` after `initialize`.
- No log message may contain customer scan content.

## 7. Units and coordinates

- Canonical engine unit: **metre**.
- Revit internal unit: **foot**; conversion happens at the Revit boundary.
- Source scan coordinates are preserved; no recentring is performed without an
  explicit, recorded transform.
- Import metadata records `sourceBounds` in source units, `bounds` in metres,
  the source unit, how it was determined (`format`, `header`, `user` or
  `assumed`) and the exact metres-per-source-unit factor.
- Supported units include millimetres, centimetres, metres, inches, feet and US
  survey feet.
- `revoai_geometry.units` is the single conversion implementation and is unit
  tested. A wrong unit must raise, not guess.

## 8. Point cloud pipeline

```
source file
  → format reader (E57 / LAS / LAZ / PLY / XYZ)
  → source-unit resolution
  → optional outlier removal / voxel downsampling
  → one explicit conversion to metres
  → 3D-grid chunking
  → metadata.json + chunks/*.npz
  → bounds / radius / sample queries (nearest is store-level)
```

- Readers return positions in the file's source coordinate system and report
  the unit they can prove. The importer performs the only unit conversion.
- No reader recentres, rotates or rescales coordinates. `sourceBounds` and the
  source unit remain in metadata for auditing.
- Each chunk stores a float64 origin and float32 offsets, plus optional uint8
  colours, float32 intensity and uint8 classification.
- `metadata.json` contains a 3D cell-to-chunk grid. Queries open only chunks
  whose cells intersect the request; they do not load the whole store.
- Chunk size defaults to 25 m. Import is synchronous and currently loads the
  source cloud before chunking; streaming import is a Phase 9 item.
- A scan store is written to a temporary folder and renamed into place, so a
  failed import does not leave a half-written store.

### Model-visible reference

After a successful import the add-in queries up to 4,000 evenly sampled points
and builds a `DirectShape` named **Revo Point Cloud Reference** from small
tetrahedral markers, converted from scan metres to Revit internal units. It is a
visual aid only: the scan store remains the source of truth and the DirectShape
is not native point-cloud data. The sidebar button deletes or rebuilds that
element; the element persists with the project when saved.

## 9. Scan Analysis baseline

Phase 4 intentionally ships a deterministic geometric baseline rather than
claiming a trained model that does not exist.

```
point cloud store
  → global sample (maxPoints)
  → optional voxel downsampling
  → RANSAC plane extraction (Open3D)
  → floor / ceiling / wall / other classification
  → plane fit, density, size, coverage and confidence signals
  → analysis/segmentation.json
```

- Each result element is an **instance** with an id, kind, plane normal/offset,
  centroid, bounds, area, inlier count and confidence.
- Classification uses the plane's vertical normal component and its centroid
  height relative to the analysed cloud. Flat planes near the bottom are floors;
  flat planes near the top are ceilings; vertical planes are walls.
- Confidence combines planarity, sampling density, segment size, coverage and
  fit error. It is explicitly labelled as plane-fit confidence, not dimensional
  accuracy.
- Sampling and voxel settings are recorded with the result. Large scans can miss
  small surfaces when the point limit is low.
- Analysis writes JSON only. It never creates Revit geometry.
- `segmentation.info` reads the stored result and returns the same shape.

## 10. Reconstruction plan and native geometry

```
segmentation.json
  → confidence filter
  → floor level clustering
  → closed floor polygons
  → wall line + base level + wall height
  → reconstruction-plan.json
  → C# Revit transaction: levels, Floor.Create, Wall.Create
```

- Plan creation is read-only. It writes JSON beside the scan.
- The plan can come from the built-in geometric baseline, an external JSON file,
  or the GPT-6 Astra provider. External/Astra plans are bounds-checked against
  the scan and normalized before preview; they are never executed directly.
- Astra has two paths: a Revo-managed subscription gateway (recommended; no
  OpenAI key on the customer machine) and a BYO `OPENAI_API_KEY` developer mode.
  The key is never logged or written to the plan.
- The subscription gateway is configured with `REVOAI_ASTRA_GATEWAY_URL` and
  `REVOAI_SUBSCRIPTION_TOKEN`; entitlement, quota and billing live in the Revo
  backend. See `docs/subscription-architecture.md`.
- Floors use ordered plane boundaries from segmentation; the current boundary
  is a convex hull, so concave spaces are simplified.
- Walls use the longest boundary extent as a line. The base level is the nearest
  floor below the wall; height comes from the nearest ceiling above, otherwise
  the configured fallback.
- Existing Revit levels are reused by elevation; missing levels are created.
- `Generate BIM` shows the plan first. Only **Create in Revit** starts the
  transaction.
- Created floors and walls receive `REVO-INFERRED` marks and comments containing
  the source segment and confidence.
- Any failure rolls back the transaction. No placeholder geometry is created.
- Default project floor/wall types are used; wall type width is not
  instance-editable.

## 11. Threading rules

- Revit API calls run only on Revit's main thread.
- The modeless WPF UI (Phases 2-3) marshals Revit API work through `ExternalEvent`.
- The Python engine runs out of process, so it cannot touch the Revit API.
- Long operations must be cancellable and must report progress.

## 12. Versioning

- Product version follows SemVer (`0.7.1`).
- Assembly/file versions mirror it.
- Protocol has an independent `MAJOR.MINOR`.
- Each Revit version gets its own build output folder
  (`bin\<Configuration>\<RevitVersion>`) and its own manifest installation.

## 13. User interface and Revit marshalling

- Ribbon built in `Ribbon/RevoRibbon.cs`; each button points at an
  `IExternalCommand` in `Commands/`.
- Commands that belong to later phases show an explicit TaskDialog; they never
  create placeholder geometry.
- The modeless `WorkspaceWindow` binds to `WorkspaceViewModel` and contains the
  entire scan-to-BIM workflow as stages.
- `Import scan`, `Analyze scan` and `Generate BIM` are stage views inside that
  single window, selected from the sidebar or the ribbon. No separate process
  window is opened.
- The `Knowledge library` stage is also inside the workspace. It searches the
  local SQLite/FTS5 store, reviews records and invokes the read-only project
  extractor. A separate `KnowledgeTranscriptWindow` collects source metadata.
- Import sends the file to `pointcloud.import` and displays metadata.
- Analysis calls `segmentation.run` and displays segments/confidence.
- Generate previews the plan. **Create in Revit** runs `ModelBuilder.Create`
  through `RevitTaskRunner` in one transaction and marks created elements
  inferred.
- Every Revit API call from the window goes through `RevitTaskRunner`, which
  queues work and raises an `ExternalEvent`. The WPF thread never touches
  `Document`, `Element` or `Transaction`.
- `DocumentReader` is the only place that reads/writes Revit elements for the
  workspace. Level creation uses one transaction, skips existing names and rolls
  back on failure.
- Settings are persisted through `RevoConfigWriter`; the engine reads them when
  it starts.

## 14. Error handling

All engine failures are typed `RpcError` values with a machine code, a human
message and, where possible, a `remedy`. The add-in must present the remedy and
log the full error. Silent fallbacks are forbidden.

## 15. Local knowledge engine

```
knowledge source (transcript / document / read-only RVT extraction)
  → source hash + provenance
  → SQLite documents/chunks + FTS5
  → structured record (pending review)
  → human review (approved / rejected / needs correction)
  → knowledge.context (approved only, with citations)
  → Astra plan context / decision log
```

- Runtime root: `%LOCALAPPDATA%\RevoAI\knowledge`, overridable with
  `REVOAI_KNOWLEDGE_ROOT`.
- `knowledge.db` uses WAL, foreign keys and FTS5. Each engine request opens a
  short-lived connection; migrations are idempotent.
- Imports are idempotent by content hash. Approved records are immutable and
  never overwritten by later imports.
- Raw sources create a `source_material` record with status `extracted`; they are
  searchable but never used as guidance until manually approved.
- The Revit extractor is read-only, runs through `RevitTaskRunner`, and never
  saves or closes the document.
- Astra retrieval adds only approved, citable context. The scan evidence remains
  authoritative. Retrieval IDs and the plan summary are recorded in `decisions`.
- Backups are checksummed ZIPs; exports are JSONL with full provenance.
- No network access is required for storage, search, review, extraction, backup
  or export. Video and documentation ingestion is manual and user-authorized.

See `docs/knowledge-engine.md` for the schema and RPC surface.
