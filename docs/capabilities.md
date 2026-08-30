# Current Spire v2 capability scope

Spire v2 provides deterministic Google Ads operations through frozen truth and
one canonical `ExecutionRun` lifecycle.

## Supported analysis

- campaign list and get from the current `AccountSnapshot`;
- restricted frozen `evidence_query` datasets, with coverage and aggregation
  semantics on every response;
- `negative_keywords` inventory covering campaign, ad-group, shared-list, and
  account-level sources when Google Ads exposes them during refresh;
- deterministic negative-keyword candidates from frozen search terms, positive
  keywords, and the existing negative inventory.

Candidate detection is a read-only projection. It has no durable inbox or
workflow state.

## Supported mutations

| Change kind | Public preparation | Verification |
| --- | --- | --- |
| `UPDATE_BUDGET` | `spire change budget` / MCP `change_budget` | exact campaign budget |
| `ADD_NEGATIVE_KEYWORD` | `spire change negative-keyword` / MCP `change_negative_keyword` | exact scope, text, and match type |
| `CREATE_SEARCH_CAMPAIGN` | `spire change search-campaign` / MCP `create_search_campaign` | campaign, paused status, budget, targeting, ad groups, keywords, RSA, final URL |

All three are prepared through `ChangeSpec`, immutable `CompiledOperation`,
Google Ads `validate_only`, HardPolicy, exact single-use human approval,
`request_sent` before transport, one canonical mutate, and semantic read-back.
MCP cannot approve any run. Search campaigns are created `PAUSED`.

## Explicitly not implemented

- recommendation inbox or persistence;
- `OperatingMandate`;
- `BusinessProfile`;
- autonomous optimization;
- bidding mutations;
- RSA replacement mutation;
- sitelink mutation;
- internal LLM investigate engine.
