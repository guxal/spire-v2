---
type: adr
decision: ADR-0008
domain: truth
status: accepted
---

# ADR-0008 — Observed AccountSnapshot is separate from BusinessProfile

`AccountSnapshot` describes what Google Ads showed in one exact frozen
observation. A future `BusinessProfile` will describe operator-approved
business facts and constraints. Neither truth replaces the other, and the
first slice does not create a profile store or make it a prerequisite.
