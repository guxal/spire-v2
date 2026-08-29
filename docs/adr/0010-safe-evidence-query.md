---
type: adr
decision: ADR-0010
domain: evidence
status: accepted
---

# ADR-0010 — `evidence_query` is a restricted logical evidence capability

External analysis receives evidence through one typed capability. Requests
contain customer identity, explicit campaign scope, an allowlisted dataset,
optional date range, allowlisted dimensions and metrics, equality filters, and
bounded ordering/limit. Arbitrary SQL, filesystem paths, physical filenames,
investigation records, semantic profiles, and live API calls are not inputs to
this capability.

The capability resolves finalized truth through `DatasetResolver`, validates
schema and scope, performs deterministic filtering/grouping/aggregation, and
returns rows plus aggregates, schema, scope, freshness, logical evidence
reference, and explicit limitations. A failed or absent dataset is never
silently represented as an empty successful dataset.

Derived metrics use integer micros for monetary values. CTR, CPC, and CPA are
calculated from grouped integer totals; undefined divisions are `null`.
