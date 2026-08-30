---
type: guide
domain: application
status: stable
tags: [architecture]
---

# Spire architecture

Spire is organized around a narrow rule: acquire provider observations
explicitly, publish them as frozen truth, expose only logical public
capabilities, and execute production changes through one verified lifecycle.

## Layer direction

```text
CLI / MCP adapters
        ↓
PublicApi
        ↓
Application composition root
        ↓
customer-scoped application services
        ↓
core workspace | truth/evidence | execution | Google Ads provider
        ↓
local workspace and Google Ads API
```

Dependencies point inward. CLI and MCP parse, serialize, and route; they do
not read storage or construct Google Ads clients. `PublicApi` exposes the same
application operations to both. `Application` is the composition root that
creates a customer-scoped provider and services.

## Boundaries

| Boundary | Ownership | Public contract |
| --- | --- | --- |
| Core | `WorkspacePaths`, identifiers, safe paths | Every runtime artifact is scoped below one validated customer root. |
| Google Ads | auth, discovery, extraction, campaign reads, provider | One lazy client provider owns credentials and Google Ads client construction. |
| Truth | manifests, `AccountSnapshot`, `DatasetResolver` | Finalized, hashed observations are the only source for local reads. |
| Evidence | schemas and `EvidenceQueryService` | Typed, allowlisted, scoped queries return logical evidence rather than storage details. |
| Execution | `ChangeSpec`, compiler, policy, authority, runs, runtime | One immutable lifecycle governs all production effects. |
| Application | `Application`, `CustomerServices`, `PublicApi` | Customer-scoped service composition and storage-independent projections. |
| Interfaces | CLI commands and MCP server | Human and agent adapters share the application contract; only the CLI can approve. |

## Read journey

```text
auth → discovery/refresh → finalized truth → AccountSnapshot
     → DatasetResolver → campaign read or evidence_query → external reasoning
```

1. `GoogleAdsAuthService` establishes or verifies access through
   `GoogleAdsCredentialProvider` and `GoogleAdsClientProvider`.
2. `PublicApi.account_refresh` resolves a finite campaign scope, then builds a
   `RefreshSpec` for `ScopedRefreshService.refresh`.
3. `ScopedRefreshService` writes datasets, an `ExtractionManifest`, and an
   atomic current pointer under the customer truth root.
4. `AccountSnapshotService.current` validates that publication and materializes
   an immutable `AccountSnapshot` from its manifest.
5. `CampaignReadService` and `EvidenceQueryService` use `DatasetResolver`; no
   public adapter derives a dataset file path.
6. `PublicApi.campaigns_get` returns a business projection. `PublicApi.evidence_query`
   validates a typed request and returns frozen rows, aggregates, semantics,
   freshness, and a logical `evidence_ref` for human or external LLM analysis.

## Evidence journey

`evidence_query` accepts a customer, explicit campaign scope, allowlisted
dataset, optional certified date range, allowlisted dimensions/metrics, bounded
ordering, and limit. `DatasetResolver` confirms the finalized manifest,
customer jail, dataset state, hashes, and scope before any rows are returned.

Each response carries `coverage`, `attribution_scope`,
`aggregation_semantics`, `limitations`, and a comparison baseline. Segmented
Google Ads views may omit privacy-thresholded, zero-metric, non-keyword, or
non-reportable data, and asset rows may overlap. Therefore their totals are
not campaign totals unless their declared semantics say so.

`negative_keywords` is a configuration inventory frozen during refresh. It
combines campaign and ad-group criteria with shared-list and account-level
negative keyword lists when the provider exposes them. The deterministic
`NegativeKeywordCandidateService` reads only `search_terms`, `keyword_daily`,
and that inventory from the same snapshot; it does not create a durable
workflow record.

## Execution journey

```text
ChangeSpec → exact AccountSnapshot → CompiledOperation → validate_only
→ HardPolicy → AuthorityCoverage → human approval → request_sent
→ mutate once → semantic read-back → VERIFIED
```

1. `PublicApi.change_budget`, `change_negative_keyword`, and
   `create_search_campaign` call the corresponding preparation method on
   `ExecutionRunService`.
2. The service persists a `ChangeSpec`, loads the exact current
   `AccountSnapshot`, and calls `BudgetCompiler.compile` for one immutable
   `CompiledOperation`.
3. `ProductionRuntime.validate_only` validates that operation through the
   shared Google Ads client. `HardPolicyService` and `AuthorityService` decide
   whether it can wait for human approval.
4. `ExecutionStore` persists the `ExecutionRun` and its append-only approval
   request. The run stops at `WAITING_FOR_APPROVAL`.
5. The trusted CLI calls `ExecutionRunService.approve_human`; approval binds a
   human principal to the run fingerprint and can be used once.
6. `ExecutionRunService.execute_approved` persists `request_sent` before the
   Google Ads mutate call. Ambiguous post-send results enter reconciliation;
   they are never blindly retried.
7. `SemanticReadBack` verifies the actual requested state. It verifies the
   exact budget, negative keyword scope/text/match type, or the created paused
   Search campaign with budget, targeting, ad groups, keywords, RSA, and final
   URL. Only a match moves the `ExecutionRun` to `VERIFIED`.

## Authority boundary

MCP can check auth, list accounts, refresh, discover and read campaigns, query
evidence, derive negative-keyword candidates, prepare all supported mutation
runs, inspect runs, and resume a run that has already been approved. It has no
approve tool.

The CLI is the trusted human-facing surface for one-off approval. An approval
is an append-only artifact bound to the exact run fingerprint, not an agent
capability or a reusable token. `OperatingMandate` is a future authority model;
it is not an active substitute for exact human approval.

## Workspace boundary

`WorkspacePaths` is the sole authority for
`.spire/customers/<customer_id>/`. `truth` contains frozen publications;
`execution` contains specifications, runs, approvals, and events; `cache`
holds temporary OAuth metadata. `config` and `knowledge` are canonical
categories but do not have active runtime payloads today.

Public projections use logical snapshot, extraction, and evidence IDs. Physical
paths, filenames, tokens, client secrets, and Google Ads resource identity are
not public interface contracts.

## Google Ads provider ownership

`GoogleAdsCredentialProvider` owns refresh-token credentials, access-token
expiry, and cache reuse. `GoogleAdsClientProvider` owns normalized
configuration, normalized login customer ID, and one lazy client per service
lifecycle. Discovery, refresh, validate-only, mutation, and semantic read-back
receive that provider rather than building clients independently.

## Monetary and refresh-scope contracts

Internal/provider monetary values and frozen evidence use integer micros.
Campaign and execution public business projections convert micros
deterministically to account-currency units and carry the currency separately.
This is governed by [ADR-0016](../adr/0016-public-currency-units-and-internal-micros.md).

Every refresh runs against a finite, explicit `RefreshSpec` scope. A public
surface may use discovery to resolve that scope before constructing the spec;
the normalized resolved IDs and fingerprint remain frozen provenance. This is
governed by [ADR-0017](../adr/0017-finite-resolved-refresh-scope.md).

## Stable core

Do not change these boundaries casually:

- `WorkspacePaths` and tenant isolation;
- frozen truth contracts, `AccountSnapshot`, and `DatasetResolver`;
- `GoogleAdsCredentialProvider` and `GoogleAdsClientProvider`;
- `PublicApi` and the shared CLI/MCP application contract;
- evidence query semantics;
- `ChangeSpec`, `CompiledOperation`, and `ExecutionRun`;
- exact human approval;
- `request_sent` before transport;
- semantic verification and no blind retry;
- the rule that MCP cannot approve.

Changes to a stable-core boundary require conformance with its accepted ADR or
an accepted successor ADR. New functionality should extend these boundaries,
not redesign them.
