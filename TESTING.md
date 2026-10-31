# Testing

## 1. Strategy

| Layer | Tool | What it proves |
| --- | --- | --- |
| C# unit | xUnit | Protocol serialization, version rules, configuration resolution |
| C# integration | xUnit + real Python process | Add-in can start, handshake, ping and stop the engine |
| Python unit | pytest | Protocol models, dispatch rules, unit conversions |
| Python process | pytest subprocess | The real stdio loop answers correctly and exits cleanly |
| Revit manual | Revit 2026/2027 | Ribbon, workspace, settings, level creation (Phase 2+) |
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

## 4. Coverage in Phase 1

Covered:

- Major-version compatibility, including malformed inputs.
- camelCase wire names in both languages.
- Typed error propagation (`-32011`, `-32601`, `-32700`, `-32600`).
- Initialize → ping → shutdown over a real process.
- Configuration precedence (environment > file > defaults).
- Engine root discovery and interpreter selection.
- Unit aliases and exact conversion factors (metre/foot/inch/mm/cm).

Not covered (by design, later phases):

- Revit document transactions and element creation.
- Point cloud I/O and memory behaviour.
- AI accuracy metrics.

## 5. Manual Revit verification (Phase 1)

1. Build and install for Revit 2026.
2. Launch Revit.
3. Confirm no add-in error dialog appears.
4. Confirm the log contains the startup and shutdown records.
5. Repeat for Revit 2027.

Record the outcome in `docs/phase-1-report.md`.

## 6. Rules

- A test that silently does nothing is not a test. Soft skips must print why.
- Never mock the engine protocol in the integration test — use the real process.
- Accuracy claims require measured data and a described method.
