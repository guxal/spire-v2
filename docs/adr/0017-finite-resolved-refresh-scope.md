---
type: adr
decision: ADR-0017
domain: truth
status: accepted
supersedes: ADR-0003
---

# ADR-0017 — Refresh executes against a finite resolved campaign scope

## Context

ADR-0003 correctly prohibits unbounded refresh. The accepted public API may
discover campaigns before constructing `RefreshSpec` when a user omits a
campaign ID, including an enabled-only selection. That resolution is a public
convenience, not a relaxation of the acquisition boundary.

## Decision

`RefreshSpec` requires a non-empty, finite, explicit set of campaign IDs.
Public or interactive discovery may resolve this set before `RefreshSpec` is
created. The resolved IDs are normalized, sorted, fingerprinted, and recorded
in the frozen manifest as the refresh scope.

No refresh may infer an unbounded account-wide scope or query an unbounded
campaign set. The account identity query remains part of the same bounded
publication and does not widen the campaign scope.

## Consequences

- `account refresh` can offer discovery-backed usability without weakening
  frozen-truth provenance.
- `AccountSnapshot`, `DatasetResolver`, evidence, and execution can validate
  the exact resolved scope after publication.
- Consumers receive a deterministic scope record whether campaign IDs were
  supplied directly or resolved by the public surface.
