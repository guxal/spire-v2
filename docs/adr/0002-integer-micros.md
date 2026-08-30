---
type: adr
decision: ADR-0002
domain: google-ads
status: superseded
superseded_by: ADR-0016
---

# ADR-0002 — Monetary values remain integer micros

Google Ads monetary values are preserved as integer micros from acquisition
through frozen truth and public read projections. The first slice exposes
`daily_budget` as an integer micros value, with `currency` separately carried
from account truth. Floating-point or model-authored monetary values are not
part of this contract.
