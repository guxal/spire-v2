# Spire

Spire is a deterministic Google Ads operations control plane. It acquires
scoped provider data, freezes it as verifiable local truth, exposes safe
evidence to people and agents, and executes authorized changes through one
canonical lifecycle.

## Principles

- **Explicit acquisition.** Google Ads data enters Spire only through an
  explicit discovery or refresh action.
- **Frozen truth.** Reads and analysis consume a finalized, hashed snapshot;
  they do not silently query the provider.
- **Deterministic effects.** A production request compiles from exact frozen
  truth into one immutable provider operation.
- **Evidence before reasoning.** `evidence query` exposes scoped, structured
  facts for external reasoning rather than embedding an LLM in the product.
- **Human authority.** A production change requires exact, single-use human
  approval for the persisted run.
- **Semantic verification.** A successful provider response is not enough:
  Spire reads back the provider state and verifies the requested meaning.
- **One application contract.** CLI and MCP are thin adapters over the same
  `PublicApi` and application services.

## Architecture

```text
Human / Agent
      |
   CLI / MCP
      |
  PublicApi
      |
 Application
      |
Truth / Evidence / Execution
      |
WorkspacePaths + Google Ads provider
```

The architecture, stable boundaries, and journeys are described in
[Architecture](docs/architecture/README.md). Accepted decisions live in
[ADRs](docs/adr/). The exact supported product surface is listed in
[Current capability scope](docs/capabilities.md).

## Current capabilities

### Authentication

Spire supports installed-app Google OAuth bootstrap, secret-safe local status,
and a harmless authenticated access check. It owns a customer-scoped temporary
access-token cache and a lazy Google Ads client provider.

### Account discovery

Spire lists accessible accounts and discovers live campaigns for an explicit
customer account.

### Refresh

An account refresh resolves a finite campaign scope, retrieves current Google
Ads observations, and atomically publishes frozen truth with hashes and
coverage states.

### Campaign reads

Campaign list and get read the current frozen snapshot. Their public budgets
are expressed in account-currency units; provider and frozen monetary values
remain integer micros.

### Evidence

`evidence datasets` lists logical datasets in the current snapshot.
`evidence query` is a restricted, scoped query over those datasets. It returns
logical evidence references, schema, freshness, and aggregation semantics.
`negative_keywords` is a frozen inventory of campaign, ad-group, shared-list,
and account-level negative keywords where the Google Ads account exposes each
source. `change negative-candidates` deterministically flags objective
search-term signals from that same frozen snapshot; it does not persist a
workflow item.

### Execution

The supported production mutations are `UPDATE_BUDGET`,
`ADD_NEGATIVE_KEYWORD`, and `CREATE_SEARCH_CAMPAIGN`. Each compiles from
frozen truth, is remotely validated with Google Ads `validate_only`, evaluated
by HardPolicy, held for exact human approval, dispatched once, and
semantically verified by provider read-back. Search campaigns are always
created `PAUSED`.

### CLI

The `spire` command is the trusted human-facing interface. All commands accept
explicit IDs, support `--json`, and can use `--no-input` in automation.

### MCP

`spire mcp` starts a stdio JSON-RPC server for safe public reads, refresh,
evidence, run inspection, budget-change preparation, and approved-run resume.
MCP cannot approve a run.

## Quick start

Spire requires Python 3.11 or later and Google Ads credentials.

### Install

```bash
python -m pip install -e ".[dev]"
```

### Configure Google Ads and authenticate

```bash
cp config/google-ads.example.yaml config/google-ads.yaml
# Edit config/google-ads.yaml with your developer token, OAuth client, and login customer ID.
spire auth google-ads login
spire auth google-ads verify --customer-id <customer_id>
```

The private `config/google-ads.yaml` file and tokens are never public API
outputs. See [Google Ads authentication](docs/google-ads-auth.md) for setup,
token lifecycle, and troubleshooting.

### Select and refresh an account

```bash
spire accounts list
spire campaigns discover --customer-id <customer_id>
spire account refresh \
  --customer-id <customer_id> \
  --campaign-id <campaign_id> \
  --date-start YYYY-MM-DD \
  --date-end YYYY-MM-DD
```

`--campaign-id` may be omitted when a finite public discovery result can
resolve the scope. The resulting refresh still executes against explicit,
recorded campaign IDs.

### Read campaigns and evidence

```bash
spire campaigns list --customer-id <customer_id>
spire campaigns get --customer-id <customer_id> --campaign-id <campaign_id>
spire evidence datasets --customer-id <customer_id> --campaign-id <campaign_id>
spire evidence query \
  --customer-id <customer_id> \
  --campaign-id <campaign_id> \
  --dataset campaign_daily \
  --dimension date \
  --metric impressions \
  --metric clicks \
  --metric cost_micros
```

### Start MCP

```bash
spire mcp
```

For a client configuration example and the available authority boundary, see
[MCP installation](docs/mcp-installation.md).

## Analyze a campaign

Spire's analysis workflow is:

```text
refresh → campaigns get → evidence datasets/query → external LLM or human reasoning
```

First refresh the exact campaign and date range to obtain a new frozen
snapshot. Confirm the campaign with `campaigns get`, inspect the dataset list,
and query only that current logical evidence. Preserve each response's
`evidence_ref` and its `coverage`, `attribution_scope`, and
`aggregation_semantics` when reasoning about it.

Spire currently has no internal LLM and no legacy `investigate` engine.
It deliberately supplies evidence rather than recommendations from a hidden
reasoning layer. See [Evidence aggregation semantics](docs/evidence-semantics.md).

## Work with negative keywords

Refresh first, inspect the frozen inventory with `evidence query`, then derive
deterministic candidates. Candidate evidence is not an instruction to mutate:
review its reason codes and metrics before preparing a change.

```bash
spire evidence query \
  --customer-id <customer_id> \
  --campaign-id <campaign_id> \
  --dataset negative_keywords
spire change negative-candidates \
  --customer-id <customer_id> \
  --campaign-id <campaign_id>
spire change negative-keyword \
  --customer-id <customer_id> \
  --campaign-id <campaign_id> \
  --text "<negative text>" \
  --match-type EXACT \
  --environment PRODUCTION
```

The final two lifecycle steps are the same exact human approval and resume
commands shown for a budget change. An optional `--ad-group-id` creates an
ad-group-level negative; otherwise the change is campaign-level.

## Create a paused Search campaign

Create a small typed JSON request. Geo and language criterion IDs are explicit
targeting inputs; Spire resolves the provider resource names internally.

```json
{
  "campaign_name": "Search · example service",
  "daily_budget": "10",
  "geo_target_ids": ["2170"],
  "language_criterion_ids": ["1003"],
  "bidding_strategy": "MAXIMIZE_CLICKS",
  "ad_groups": [{
    "name": "Core service",
    "keywords": [{"text": "example service", "match_type": "PHRASE"}],
    "headlines": ["Example service", "Local specialists", "Request a quote"],
    "descriptions": ["A concise approved description.", "A second approved description."],
    "final_url": "https://www.example.com/service"
  }]
}
```

```bash
spire change search-campaign \
  --customer-id <customer_id> \
  --request-file search-campaign.json \
  --environment PRODUCTION
```

Preparation stops at `WAITING_FOR_APPROVAL`. After a human approves the exact
run, `runs resume` creates the campaign in `PAUSED` state and verifies its
campaign, budget, targeting, ad groups, keywords, RSA, and final URL.

## Execute a budget change

Read the current public budget, choose the exact target in account currency,
then prepare one production run:

```bash
spire campaigns get --customer-id <customer_id> --campaign-id <campaign_id>
spire change budget \
  --customer-id <customer_id> \
  --campaign-id <campaign_id> \
  --daily-budget <target_budget> \
  --environment PRODUCTION
```

Preparation deterministically compiles the operation, runs Google Ads
`validate_only`, applies HardPolicy and authority coverage, persists the run,
and stops in `WAITING_FOR_APPROVAL`. Inspect the same run from a new CLI
process before approval:

```bash
spire runs list \
  --customer-id <customer_id> \
  --campaign-id <campaign_id> \
  --status waiting_for_approval \
  --latest
spire runs get --run-id <run_id>
```

After a human has reviewed the exact current/proposed values, policy,
fingerprint, validate-only result, and `request_sent` state, that human can
approve the exact run once and resume it:

```bash
spire runs approve --run-id <run_id> --yes
spire runs resume --run-id <run_id>
spire runs get --run-id <run_id>
```

Resume persists `request_sent` before transport, never blindly retries an
ambiguous send, and marks the run `VERIFIED` only after semantic read-back
matches the target. MCP can prepare and inspect a run, but cannot approve it.

## Workspace

Runtime state is tenant-scoped:

```text
.spire/customers/<customer_id>/
├── config/      # canonical per-customer category; no active payload today
├── truth/       # finalized refresh publications, manifests, datasets, current pointer
├── knowledge/   # canonical reserved category; no active BusinessProfile store today
├── execution/   # ChangeSpecs, runs, approvals, and append-only events
└── cache/       # temporary OAuth access-token metadata
```

`WorkspacePaths` is the only component that derives these paths. Public
capabilities expose logical IDs and projections, not physical dataset paths.

## Testing

Run the local quality gates from the repository root:

```bash
python -m pytest
python -m ruff check src tests
```

The architecture-specific checks are included in the test suite. The complete
development workflow is documented in [Architecture](docs/architecture/README.md),
[CodeGraph](docs/development/codegraph.md),
[Obsidian](docs/development/obsidian.md), and [ADRs](docs/adr/).

## Current limitations

- There is no recommendation inbox or persistence, `OperatingMandate`,
  `BusinessProfile`, autonomous optimization, bidding mutation, RSA replacement
  mutation, sitelink mutation, internal LLM, or legacy investigate engine.
- Search-campaign creation is intentionally narrow: it supports the typed
  Search request documented above and creates campaigns paused only.
- Google Ads segmented datasets can be partial or non-additive. Their response
  semantics identify the coverage and safe comparison baseline.
- Google Ads may restrict Auction Insights participant identity or metrics; no
  domain is inferred when the provider does not return it.
- Refresh is explicit. Read projections continue to use frozen truth until a
  subsequent refresh publishes newer truth.
