---
type: dashboard
domain: application
status: stable
tags: [architecture, navigation]
---

# Spire architecture dashboard

This dashboard is the human entry point for the accepted Spire architecture.
Use it to move between intent (ADRs), stable boundaries, public interfaces, and
the tests that prove those boundaries. Use CodeGraph for current structural
relationships and blast radius.

## Start here

- [Architecture overview](README.md) — layers, read/evidence/execution
  journeys, authority, workspace, provider ownership, and stable core.
- [CodeGraph architecture workflow](../development/codegraph.md) — required
  machine-facing preflight for a non-trivial change.
- [Obsidian architecture navigation](../development/obsidian.md) — this
  human-facing graph and Bases workflow.
- [Evidence aggregation semantics](../evidence-semantics.md) — safe analysis
  interpretation for segmented Google Ads evidence.

## Domains

| Domain | Navigate to | Responsibility |
| --- | --- | --- |
| `core` | `src/spire/core/` | identity, safe paths, and customer-scoped workspace |
| `google-ads` | `src/spire/google_ads/` | OAuth, client provider, discovery, refresh, campaign reads |
| `truth` | `src/spire/truth/` | immutable frozen contracts, snapshots, logical resolution |
| `evidence` | evidence query modules | dataset schema, aggregation semantics, safe queries |
| `execution` | `src/spire/execution/` | compile, policy, authority, run store, transport, verification |
| `application` | `src/spire/application.py` | customer-scoped composition and orchestration |
| `interfaces` | CLI, MCP, and `PublicApi` | public projections and adapter authority boundary |

In Code Graph, filter by `domain:<name>`. All accepted production modules use
`@status stable`; the graph's stable nodes should be interpreted through the
governing ADR and its tests, not as a claim that the module is safe to redesign.

## Stable core

- `WorkspacePaths` and customer tenancy;
- frozen truth contracts, `AccountSnapshot`, and `DatasetResolver`;
- Google Ads credential/client providers;
- `PublicApi` and the shared CLI/MCP contract;
- evidence aggregation semantics;
- `ChangeSpec`, `CompiledOperation`, and `ExecutionRun`;
- exact human approval, `request_sent` before transport, semantic verification,
  and no blind retry;
- MCP's inability to approve.

Read the [Stable core section](README.md#stable-core) before changing any of
these boundaries.

## Public interfaces

```text
CLI / MCP → PublicApi → Application → customer-scoped services
```

- CLI is the trusted human interface and owns exact run approval.
- MCP offers safe reads, refresh, evidence, run inspection, change preparation,
  and approved-run resume. It has no approval tool.
- Both use the same application composition and public projections.

## Execution navigation

```text
ChangeSpec → CompiledOperation → validate_only → policy/authority
→ human approval → request_sent → mutate → semantic read-back → VERIFIED
```

Primary intent: [ADR-0011](../adr/0011-canonical-execution-lifecycle.md),
[ADR-0012](../adr/0012-exact-human-approval.md), and
[ADR-0013](../adr/0013-provider-boundary-and-semantic-verification.md).

## Truth and evidence navigation

```text
explicit refresh → finalized manifest/datasets → AccountSnapshot
→ DatasetResolver → campaign read / evidence_query
```

Primary intent: [ADR-0001](../adr/0001-deterministic-frozen-truth.md),
[ADR-0004](../adr/0004-typed-immutable-truth.md),
[ADR-0005](../adr/0005-dataset-resolver-boundary.md), and
[ADR-0010](../adr/0010-safe-evidence-query.md).

## Accepted ADRs

| ADR | Decision |
| --- | --- |
| [0001](../adr/0001-deterministic-frozen-truth.md) | deterministic frozen truth |
| [0004](../adr/0004-typed-immutable-truth.md) | typed immutable truth contracts |
| [0005](../adr/0005-dataset-resolver-boundary.md) | logical dataset resolver boundary |
| [0006](../adr/0006-account-scoped-workspace.md) | account-scoped workspace |
| [0007](../adr/0007-google-ads-provider-ownership.md) | single lazy Google Ads client provider |
| [0008](../adr/0008-truth-and-business-profile-separation.md) | snapshot and BusinessProfile separation |
| [0009](../adr/0009-capability-projection.md) | thin deterministic public capabilities |
| [0010](../adr/0010-safe-evidence-query.md) | safe logical evidence query |
| [0011](../adr/0011-canonical-execution-lifecycle.md) | canonical run lifecycle |
| [0012](../adr/0012-exact-human-approval.md) | exact one-off human approval |
| [0013](../adr/0013-provider-boundary-and-semantic-verification.md) | validation, dispatch, and read-back |
| [0014](../adr/0014-google-ads-authentication-bootstrap.md) | explicit Google Ads auth bootstrap |
| [0015](../adr/0015-cli-interaction-policy.md) | CLI interaction and MCP authority |
| [0016](../adr/0016-public-currency-units-and-internal-micros.md) | public currency units with internal micros |
| [0017](../adr/0017-finite-resolved-refresh-scope.md) | finite resolved refresh scope |

[ADR-0002](../adr/0002-integer-micros.md) and
[ADR-0003](../adr/0003-explicit-scoped-refresh.md) are retained as superseded
historical decisions with explicit successors.

## Primary tests

| Boundary | Primary test |
| --- | --- |
| workspace and path jail | `tests/test_workspace.py` |
| frozen truth and resolver | `tests/test_truth_pipeline.py` |
| safe evidence | `tests/test_evidence_query.py` |
| OAuth/provider | `tests/test_credentials.py`, `tests/test_provider.py` |
| execution lifecycle | `tests/test_execution_service.py`, `tests/test_execution_runtime.py` |
| approval authority | `tests/test_execution_authority.py` |
| public CLI/MCP contract | `tests/test_public_surfaces.py` |
| architecture constraints | `tests/test_architecture_guards.py`, `tests/test_public_architecture.py` |

## Bases

With Obsidian Bases enabled, open `architecture.base` for a compact table of
architecture, ADR, and development notes. The Base is an index of notes, not a
dependency map.
