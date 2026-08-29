---
type: adr
decision: ADR-0003
domain: extraction
status: accepted
---

# ADR-0003 — Refresh requires an explicit campaign scope

The first production slice accepts a non-empty, explicit set of campaign IDs
for refresh. The scope is normalized, sorted, fingerprinted, and recorded in
the manifest. A refresh without a declared scope is rejected; the service does
not infer an account-wide scope or query an unbounded campaign set.

The account identity query needed to annotate the selected campaigns is part
of the same refresh and publication, but it does not change the requested
campaign scope.
