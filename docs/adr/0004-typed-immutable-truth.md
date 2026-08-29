---
type: adr
decision: ADR-0004
domain: truth
status: accepted
---

# ADR-0004 — Truth contracts are typed, immutable, and verifiable

`ExtractionManifest`, `DatasetState`, and `AccountSnapshot` are small frozen
contracts. They carry customer identity, explicit scope, source, observation
time, dataset coverage, hashes, and provenance. A snapshot references frozen
datasets by logical extraction identity and does not copy their rows.

Hashes are computed from canonical JSON. A malformed identity, scope, status,
or content hash fails closed.
