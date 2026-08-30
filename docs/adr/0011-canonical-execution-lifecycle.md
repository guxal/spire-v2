# ADR-0011: Canonical ExecutionRun lifecycle

## Status

Accepted

## Decision

Spire v2 has one mutation lifecycle: a business `ChangeSpec` is compiled from
the exact frozen `AccountSnapshot` into an immutable operation, validated by
the provider, authorized, sent once, and semantically verified. `ExecutionRun`
is the only lifecycle record and all of its state is account-scoped below
`.spire/customers/<customer_id>/execution/`.

`ChangeSpec` contains intention and provenance, never credentials, authority,
execution authority, or provider resource identity supplied by a caller.
Production compilation consumes frozen truth and performs no live structural
read.

## Consequences

There is no CampaignJourney, legacy action store, v1 fallback, or parallel
mutation lifecycle. Integer micros are used at the provider boundary.
