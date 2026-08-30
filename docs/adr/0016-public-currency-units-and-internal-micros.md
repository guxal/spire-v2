---
type: adr
decision: ADR-0016
domain: interfaces
status: accepted
supersedes: ADR-0002
---

# ADR-0016 — Public currency units; internal and provider integer micros

## Context

ADR-0002 correctly established integer micros as the safe representation for
Google Ads acquisition, frozen truth, derived evidence, compilation, and
provider mutation. The accepted public product also presents campaign budgets
and execution-run business values in account-currency units. That public
contract is deterministic and is not a float-only provider contract.

## Decision

Provider-facing and frozen monetary values remain integer micros. Public
business projections for campaign budget and execution-run current, proposed,
and delta values use deterministic conversion from micros to account-currency
units, carrying the account currency separately.

`evidence_query` continues to expose its monetary metrics in integer micros;
its derived CPC and CPA are calculated from grouped micros. Conversion happens
only at the public business projection boundary, never by an LLM or caller.

## Consequences

- Provider identity, compilation, policy, validation, mutation, and semantic
  verification retain exact integer-micros arithmetic.
- CLI and MCP display the same deterministic business values through
  `PublicApi` projections.
- Public consumers must not treat a displayed currency-unit value as a
  provider-micros payload.
