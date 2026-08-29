---
type: adr
decision: ADR-0009
domain: interfaces
status: accepted
---

# ADR-0009 — Public capabilities are thin deterministic projections

The first public capability is campaign discovery/list/get. It exposes
business-level fields and logical evidence IDs only. Physical datasets,
parquet/JSONL filenames, Google Ads resource names, sessions, and command
orchestration are internal implementation details. Capability registration is
deferred until a public registry is needed; no speculative registry framework
is introduced in this slice.
