---
type: adr
decision: ADR-0018
domain: execution
status: accepted
supplements: ADR-0011
---

# ADR-0018 — Bounded execution-operation extension

## Context

ADR-0011 establishes one canonical mutation lifecycle. Spire v2 needs two
additional, bounded business operations: adding a campaign- or ad-group-level
negative keyword and creating a Search campaign. They must not introduce a
second store, recommendation workflow, approval route, or provider client.

## Decision

`ADD_NEGATIVE_KEYWORD` and `CREATE_SEARCH_CAMPAIGN` are additional
`ChangeKind` values governed by the existing `ChangeSpec` → immutable
`CompiledOperation` → `ExecutionRun` lifecycle.

Each compiled operation has a deterministic, kind-specific payload. Google Ads
resource names and temporary operation references are compiler-owned technical
details, never public request fields. All three supported mutation kinds share
the existing validate-only, hard-policy, exact one-off approval,
request-sent-before-transport, no-blind-retry, and semantic read-back rules.

Search-campaign creation is limited to the typed Search request supported by
the public contract. The compiler always creates the campaign `PAUSED`.
Verification proves the requested campaign, budget, targeting, ad groups,
keywords, RSA, and final URL exist before a run becomes `VERIFIED`.

Negative-keyword candidate detection is a deterministic, read-only projection
of frozen evidence. It creates neither recommendations nor persisted workflow
state.

## Consequences

- `ExecutionRun` remains Spire's only mutation lifecycle record.
- MCP can prepare and resume these runs but cannot approve them.
- A fresh, exact frozen snapshot remains required for production compilation.
- No recommendation inbox, operating mandate, autonomous optimization, or
  secondary execution architecture is introduced.
