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
| `RevoAI.Revit` | `net10.0-windows` | Add-in entry point, configuration, logging, engine process client. Phase 2 adds ribbon and WPF workspace. |
| `RevoAI.Engine` | Python ≥3.11 | Local processing service. Phase 1: transport + handshake only. |
| `RevoAI.Geometry` | Python ≥3.11 | Reconstruction algorithms. Phase 1: unit kernel. |

## 3. Transport and protocol

**Decision:** newline-delimited JSON-RPC 2.0 over the child process's
stdin/stdout. See [ADR 0002](adr/0002-engine-ipc.md).

- One JSON object per line; UTF-8; no embedded newlines.
- Request `id` is a string. Responses echo it. Notifications have no `id` and
  are currently ignored by the client (reserved for progress events).
- Methods in Phase 1: `initialize`, `ping`, `shutdown`.
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
- `revoai_geometry.units` is the single conversion implementation and is unit
  tested. A wrong unit must raise, not guess.

## 8. Threading rules

- Revit API calls run only on Revit's main thread.
- The Phase 2 modeless UI marshals work through `ExternalEvent`.
- The Python engine runs out of process, so it cannot touch the Revit API.
- Long operations must be cancellable and must report progress.

## 9. Versioning

- Product version follows SemVer (`0.2.0`).
- Assembly/file versions mirror it.
- Protocol has an independent `MAJOR.MINOR`.
- Each Revit version gets its own build output folder
  (`bin\<Configuration>\<RevitVersion>`) and its own manifest installation.

## 10. User interface and Revit marshalling

- Ribbon built in `Ribbon/RevoRibbon.cs`; each button points at an
  `IExternalCommand` in `Commands/`.
- Commands that belong to later phases show an explicit TaskDialog; they never
  create placeholder geometry.
- The modeless `WorkspaceWindow` binds to `WorkspaceViewModel`.
- Every Revit API call from the window goes through `RevitTaskRunner`, which
  queues work and raises an `ExternalEvent`. The WPF thread never touches
  `Document`, `Element` or `Transaction`.
- `DocumentReader` is the only place that reads/writes Revit elements for the
  workspace. Level creation uses one transaction, skips existing names and rolls
  back on failure.
- Settings are persisted through `RevoConfigWriter`; the engine reads them when
  it starts.

## 11. Error handling

All engine failures are typed `RpcError` values with a machine code, a human
message and, where possible, a `remedy`. The add-in must present the remedy and
log the full error. Silent fallbacks are forbidden.
