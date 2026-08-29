---
type: adr
decision: ADR-0006
domain: core
status: accepted
---

# ADR-0006 — Account-scoped runtime workspace

All new account runtime state lives under `.spire/customers/<customer_id>/`
with the canonical categories `config`, `truth`, `knowledge`, `execution`,
and `cache`. `WorkspacePaths` is the only authority allowed to derive these
roots. Customer IDs are validated and every descendant is jailed against
traversal and symlink escape.

The old `data`, `actions`, `context`, `business_memory`, `recommendations`,
and `campaign_studio` roots are not runtime roots in v2.
