# ADR-0012: Exact human approval is one-off authority

## Status

Accepted

## Decision

One-off production execution requires an exact human approval bound to one
`ExecutionRun` and its immutable fingerprint. Approval is single-use and
append-only in the execution workspace. Operating mandates may be added later,
but are not required for the first UPDATE_BUDGET capability.

The external agent surface may prepare a run and return an approval request;
only a trusted human-facing surface may approve it. An agent cannot approve,
grant authority, or bypass the approval boundary.
