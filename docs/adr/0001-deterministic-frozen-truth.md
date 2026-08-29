---
type: adr
decision: ADR-0001
domain: truth
status: accepted
---

# ADR-0001 — Deterministic code owns truth; reasoning consumes frozen evidence

Google Ads observations become truth only after an explicitly requested refresh
has been materialized, hashed, and atomically finalized. Account reads and any
future reasoning consume that frozen publication; they do not query Google Ads
because a snapshot was sourced from `LIVE`.

The system may later add other sources, but a source is never silently mixed
with another source and no live-to-local fallback is permitted. Deterministic
validation and publication code, rather than an LLM or caller convention,
decides identity, scope, freshness, and evidence usability.

## Consequences

- A refresh is an acquisition boundary and a read is a local truth boundary.
- Every snapshot is reproducible from a finalized manifest and dataset hashes.
- Missing or failed evidence is explicit and never treated as an empty dataset.
- v1 artifacts and legacy roots are not runtime inputs to this system.
