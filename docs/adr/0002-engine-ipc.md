# ADR 0002 — C# ↔ Python transport

- **Status:** Accepted
- **Date:** 2026-10-31
- **Phase:** 1

## Context

The add-in (C#) and the processing engine (Python) must exchange jobs, progress,
cancellation and results. Candidate transports:

1. Local HTTP service (FastAPI/uvicorn) on a loopback port.
2. WebSocket service.
3. Named pipes.
4. Newline-delimited JSON-RPC over a child process's stdin/stdout.

## Decision

Use **newline-delimited JSON-RPC 2.0 over stdio**, with the engine launched and
owned by the add-in.

## Rationale

- No open port, no firewall prompt, no authentication surface to design.
- Lifecycle is explicit: one engine per add-in session; killing Revit stops it.
- Trivial to debug: pipe JSON into `python -m revoai_engine.service`.
- Large payloads are not sent through the pipe: the protocol passes file paths
  and job IDs, and artefacts are written to disk (Phase 3+).
- Deterministic single-threaded engine simplifies reconstruction state.

## Consequences

- Only one client per engine process.
- Progress notifications and cancellation must be modelled in the protocol
  (`$/cancel` and notification messages) rather than relying on HTTP semantics.
- A crash of the add-in can orphan the process; Phase 9 adds supervision.
- If a shared, multi-user engine service is ever required, an HTTP adapter can
  be added behind the same method contracts without changing the DTOs.

## Rejected alternatives

- **HTTP/uvicorn:** port selection, firewall, token handling, and a second
  process lifecycle to manage, with no benefit for a desktop add-in.
- **Named pipes:** more Windows-specific code and harder cross-language testing
  than stdio.
