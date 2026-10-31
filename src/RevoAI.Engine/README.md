# RevoAI.Engine

Local Python processing engine for Revo AI BIM.

Phase 1 implements the transport and handshake only:

- `revoai_engine.service` — newline-delimited JSON-RPC 2.0 over stdin/stdout
- `initialize`, `ping`, `shutdown`
- structured stderr/file logging

Point cloud ingestion, AI segmentation and geometry reconstruction are added in
Phases 3–5. No capability is reported unless it is implemented.
