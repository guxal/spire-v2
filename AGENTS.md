# AGENTS.md instructions

## Architecture preflight

For every non-trivial change:

1. Use CodeGraph first. If the local index is missing, initialize it using
   `docs/development/codegraph.md` before exploring source.
2. Read the relevant accepted ADRs in `docs/adr/`.
3. Identify the domain, critical symbols, upstream/downstream relationships,
   public contracts, invariants, owning tests, and blast radius.
4. Compare graph reality with ADR decisions. If they conflict, stop and report
   the conflict before editing the dependent boundary.
5. Implement the smallest compliant change.
6. Update ADRs and architecture documents only when the architecture actually
   changes.
7. Re-run architecture guards and focused tests before declaring the change
   done.

Accepted ADRs are architectural authority for this repository. Historical code
is evidence, not authority. Do not add hidden legacy compatibility, fallback
paths, or runtime dependencies on `../spire-agent`.

Use the `codegraph_explore` MCP capability when available. The shell fallback
is `codegraph explore "<symbol names or question>"`.

## Stable core rule

New capabilities should extend existing boundaries rather than redesign stable
core components. Changing a stable-core boundary requires either an existing
ADR that permits the change or an accepted successor architectural decision.

The stable core is documented in `docs/architecture/README.md` and includes
customer tenancy, frozen truth, dataset resolution, Google Ads providers,
`PublicApi`, evidence semantics, execution contracts, exact human approval,
request-sent persistence, semantic verification, no blind retry, and MCP's
inability to approve.

## Metadata rule

Maintain `@domain`, `@status`, `@adr`, and `@tested-by` when architectural
ownership actually changes. Do not mechanically rewrite metadata on every code
edit. Source headers use only `@file`, `@domain`, `@status`, `@adr`, and
`@tested-by`; AST and CodeGraph own inferable structural relationships.
