# ADR 0001 — Target frameworks per Revit version

- **Status:** Accepted
- **Date:** 2026-10-31
- **Phase:** 1

## Context

The initial product plan assumed .NET 8 for Revit 2025 and 2026. Inspecting the
installed Revit builds showed that both Revit 2026 (26.5.0.55) and Revit 2027
(27.0.4.412) host **.NET 10**:

```json
// C:\Program Files\Autodesk\Revit 2026\RevitAPI.runtimeconfig.json
"tfm": "net10.0"
```

Revit 2025 is not installed on the development machine.

## Decision

- Revit 2026 and 2027 add-ins target `net10.0-windows`.
- `RevoAI.Contracts` targets `net8.0` so it remains consumable by a future
  Revit 2025 (`net8.0-windows`) build.
- The Revit version is selected at build time:
  `dotnet build -p:RevitVersion=2026|2027`.
- A `2025` mapping exists in `Directory.Build.props` but is **unverified** and
  must not be advertised as supported.

## Consequences

- Building against the installed Revit API DLLs is straightforward and warnings
  are clean.
- Documentation that says ".NET 8 for Revit 2026" is wrong for this environment
  and must not be copied forward.
- Adding Revit 2025 later requires installing it, confirming its runtime, then
  building and manually testing; the contracts layer already supports it.

## Rejected alternatives

- **Single net8.0 build for all versions.** Cannot reference net10 Revit API
  assemblies cleanly and would depend on unsupported forward compatibility.
- **Separate forked source per Revit version.** Duplicates code and guarantees
  drift.
