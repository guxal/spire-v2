---
type: adr
decision: ADR-0005
domain: truth
status: accepted
---

# ADR-0005 — DatasetResolver is the logical dataset boundary

Consumers request a dataset using customer, extraction, dataset, and optional
campaign scope identities. Only `DatasetResolver` knows the physical truth
layout. It validates the customer jail, finalized manifest, identity, dataset
state, hash, and scope before returning rows.

Missing, failed, and not-requested datasets are errors, not empty results. The
resolver has no v1 fallback, archive fallback, guessed-path API, or public
physical filename contract.
