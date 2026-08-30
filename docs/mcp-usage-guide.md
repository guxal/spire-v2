---
type: guide
domain: interfaces
status: stable
tags: [mcp, usage, public-api]
---

# Using Spire through an AI agent

This guide is for people who have already connected Spire MCP to an external
agent such as Codex or Claude. You do not need to know Python, storage paths,
or Google Ads API resource names.

Spire gives the agent controlled access to Google Ads account discovery,
explicit data refresh, frozen campaign truth, evidence queries, negative
keyword analysis, supported production-change preparation, and execution
inspection or resume. The external agent reasons about the evidence. Spire
controls the evidence, scope, deterministic compilation, provider validation,
human authority, dispatch, and semantic verification.

> MCP cannot approve a production mutation. A human must approve the exact
> Run through the trusted Spire CLI.

## The golden rule for prompts

You normally do not need to name MCP tools. Ask naturally, for example:

> Analyze the currently enabled campaign.

The agent should select the appropriate Spire capabilities. For a more
reliable complex request, say that it must refresh first, use only fresh
frozen evidence, avoid historical reports, avoid mutation, and distinguish
facts from recommendations.

## Copy/paste prompts

Replace placeholders such as `<RUN_ID>` and `<TARGET>` before sending a prompt.

### Account overview

```text
Use Spire to inspect my Google Ads account.

Refresh the current data first, then tell me:
- which campaigns are active;
- their current budgets;
- serving status;
- what fresh evidence is available.

Use only the latest frozen Spire evidence.
Do not make any changes.
```

### Complete enabled-campaign analysis

```text
Use Spire to investigate the performance of the currently ENABLED campaign.

First refresh its data. Use only the fresh snapshot produced by that refresh.

Analyze all available relevant evidence, including:
- campaign performance and daily trend;
- search terms and keywords;
- existing negative keywords and negative keyword candidates;
- ad groups, ads, RSA copy, and assets;
- geographic performance and schedules;
- auction and competition evidence where available.

Evaluate impressions, clicks, CTR, CPC, cost, conversions, CPA, wasted spend,
query relevance, keyword performance, negative coverage, ad and landing-page
relevance, geographic patterns, schedule patterns, and impression-share
limitations.

Respect each response's coverage and aggregation semantics. Do not sum
segmented datasets as if they were campaign totals.

Separate:
1. observed facts;
2. hypotheses;
3. prioritized recommendations;
4. evidence limitations.

Do not modify Google Ads.
```

### Search-term and negative-keyword audit

```text
Refresh the enabled campaign and analyze its search terms against:
- positive keywords;
- existing negative keywords;
- current negative keyword candidates.

Find potentially irrelevant or wasteful searches.

For each candidate show:
- search term;
- spend and click evidence;
- why it may be irrelevant;
- suggested negative and match type;
- whether it is already covered;
- a possible conflict with positive keywords.

Do not apply anything yet.
```

### Prepare one negative keyword

```text
Use fresh Spire evidence to evaluate the negative keyword candidate <X>.

If it is still valid and not already covered, prepare an
ADD_NEGATIVE_KEYWORD production change for the correct campaign. Run Spire
validate_only and policy checks, then stop at WAITING_FOR_APPROVAL.

Show me:
- campaign;
- negative keyword;
- scope;
- match type;
- evidence supporting it;
- Run ID;
- dry-run result;
- fingerprint.

Do not approve or execute it.
```

After reviewing the prepared Run, approve it yourself in the trusted CLI:

```bash
spire runs approve --run-id <RUN_ID>
```

Then ask the agent:

```text
The Run <RUN_ID> has been human-approved through the trusted Spire CLI.
Use Spire to resume that exact Run and report the semantic verification result.
```

### Budget analysis

```text
Analyze whether the currently enabled campaign appears constrained by budget.

Refresh first and use fresh evidence. Compare:
- current daily budget;
- spend and campaign trend;
- conversions and CPA;
- search impression share;
- rank-lost impression share;
- budget-lost impression share.

Tell me whether increasing budget is supported by evidence.
Do not change the budget.
```

### Prepare a budget change

```text
Read the current budget of the enabled campaign using Spire.

Prepare a production UPDATE_BUDGET from the current value to <TARGET> using
the canonical Spire execution lifecycle. Stop at WAITING_FOR_APPROVAL.

Show:
- current budget;
- proposed budget;
- delta;
- validate_only result;
- policy result;
- Run ID;
- fingerprint.

Do not approve it.
```

Use the same trusted CLI approval and exact-Run resume pattern shown for a
negative keyword.

### Prepare a paused Search campaign

```text
Use Spire to prepare a new Google Search campaign.

Campaign:
- name: <NAME>
- daily budget: <VALUE>
- geo target IDs: <IDS>
- language target IDs: <IDS>
- bidding strategy: <MAXIMIZE_CLICKS or MAXIMIZE_CONVERSIONS>
- final URL: <URL>

Ad groups:
- name: <AD_GROUP_NAME>

Keywords:
- <KEYWORD> — <EXACT, PHRASE, or BROAD>

RSA headlines:
- <HEADLINE_1>
- <HEADLINE_2>
- <HEADLINE_3>

RSA descriptions:
- <DESCRIPTION_1>
- <DESCRIPTION_2>

Requirements:
- compile deterministically;
- run Google Ads validate_only;
- create the campaign PAUSED;
- stop at WAITING_FOR_APPROVAL;
- do not approve or execute automatically.

Show the complete human-readable preview, Run ID, dry-run result, and
fingerprint.
```

After human approval through the CLI, ask the agent to resume that exact Run.
Spire verifies the campaign, paused status, budget, targeting, ad groups,
keywords, RSA, and final URL before reporting `VERIFIED`.

### Inspect pending Runs

```text
Use Spire to list my current execution Runs.

Show waiting for approval, approved, applying or reconciling, and verified or
failed Runs. Focus on non-terminal Runs first.

Do not approve or resume anything.
```

### Inspect one Run

```text
Inspect Spire Run <RUN_ID>.

Explain:
- requested change and target;
- current state;
- validate_only result;
- policy result;
- approval state;
- request_sent;
- dispatch state;
- semantic verification.

Do not modify the Run.
```

### Resume an approved Run

```text
Run <RUN_ID> has already been approved by me through the trusted Spire CLI.

Verify the persisted approval exists and belongs to this exact Run. Resume the
same Run through Spire. Do not create another Run. Do not retry blindly if
request_sent already exists.

Report:
- dispatch result;
- read-back;
- final state.
```

### Reusable safety suffixes

Append either of these to a request when appropriate.

```text
READ ONLY.
Do not create ChangeSpecs or ExecutionRuns.
Do not mutate Google Ads.
```

```text
Refresh first.
Use only evidence from the new resulting snapshot.
Do not use historical investigation artifacts or previous recommendations.
```

## Human approval: the exact boundary

The agent and MCP can prepare a change, run `validate_only`, apply policy, and
stop at `WAITING_FOR_APPROVAL`:

```text
prepare → validate_only → policy → WAITING_FOR_APPROVAL
```

A human reviews that exact Run and approves it using the trusted CLI:

```bash
spire runs approve --run-id <RUN_ID>
```

For non-interactive use, `--yes` affirms the displayed exact preview:

```bash
spire runs approve --run-id <RUN_ID> --yes
```

Only then can the agent resume the same Run:

```text
run_resume → mutate → semantic read-back → VERIFIED / FAILED / RECONCILING
```

Approval is exact and single-use. Asking an agent to “approve it” cannot
bypass this boundary: MCP has no approval tool. Do not create a replacement
Run after approval; resume the approved Run with its original fingerprint.

## How to write good prompts

For a clear request, specify these six things:

| Include | Example |
| --- | --- |
| Objective | Find wasted search spend. |
| Scope | Currently enabled campaign. |
| Freshness | Refresh first. |
| Questions | Search terms, keywords, and negatives. |
| Mutation permission | Read only. |
| Output | Facts → findings → recommendations → limitations. |

This makes the intended scope and safety boundary clear without requiring MCP
tool names.

## What Spire currently supports

### Read and analysis

- Google Ads authentication status and accessible-account listing;
- live campaign discovery, plus campaign list and get from the current frozen
  snapshot;
- explicit account refresh with an optional campaign and date scope;
- logical-dataset listing and safe frozen `evidence_query`;
- frozen negative-keyword inventory;
- deterministic negative-keyword candidates from frozen evidence;
- safe execution-Run listing and inspection.

### Supported mutations

- `UPDATE_BUDGET`;
- `ADD_NEGATIVE_KEYWORD` at campaign or ad-group scope;
- `CREATE_SEARCH_CAMPAIGN` from the supported typed request. New Search
  campaigns are always created `PAUSED`.

### Public execution

Every supported mutation follows one lifecycle:

```text
frozen truth → deterministic compilation → Google Ads validate_only
→ HardPolicy → WAITING_FOR_APPROVAL → exact human approval
→ request_sent → one canonical mutate → semantic read-back
```

MCP can prepare, inspect, and resume an already human-approved Run. The CLI is
the only public surface that can approve it.

### Limitations

- Evidence is only as complete as the frozen Google Ads data available during
  the refresh; there is no live evidence fallback.
- Segmented evidence can be partial or non-additive. Use each query response's
  coverage, attribution scope, aggregation semantics, and limitations.
- Search-term reporting can omit low-volume or privacy-thresholded queries.
- Auction Insights participant data, including competitor identity, can be
  restricted by the Google Ads provider account.

## What not to ask Spire to do yet

Spire does not currently support:

- autonomous approval or any approval through MCP;
- arbitrary Google Ads mutations;
- a recommendation inbox or recommendation persistence;
- `OperatingMandate` or `BusinessProfile` reasoning;
- autonomous optimization;
- bidding mutations;
- RSA replacement mutations;
- sitelink mutations;
- an internal LLM or legacy investigate engine.

## Troubleshooting

| Situation | Safe next step |
| --- | --- |
| No account appears | Ask the agent to check Spire authentication status and list accounts. If authentication is not ready, complete Google Ads login or verification in the trusted CLI. |
| Evidence is stale | Ask the agent to refresh the exact campaign and finite date range, then use only the resulting snapshot. |
| No dataset is available | Ask the agent to list the current snapshot's datasets and coverage. Check campaign scope and date range; do not fall back to old reports. |
| Run is waiting for approval | Review the exact preview, then approve that Run through `spire runs approve --run-id <RUN_ID>`. |
| Run is `RECONCILING` | Inspect the same Run first. Do not create a replacement Run or blindly retry; resume only the same Run when Spire can safely continue reconciliation. |
| Google Ads provider data is unavailable | Keep the existing frozen snapshot for read-only analysis, or retry an explicit refresh later. Do not infer missing provider data. |
| Auction Insights participant data is restricted | Treat participant or competitor identity as unavailable. Use the available campaign summary and record the stated limitation. |

## Quick reference

| I want to… | Ask the agent… |
| --- | --- |
| Analyze a campaign | “Refresh first and analyze the currently enabled campaign using only fresh frozen evidence. Do not mutate.” |
| Find negative candidates | “Refresh the enabled campaign and derive negative keyword candidates from fresh evidence. Do not apply anything.” |
| Inspect current negatives | “Refresh the enabled campaign and show its frozen negative keyword inventory and coverage.” |
| Prepare a negative | “Evaluate candidate `<X>` and prepare one negative-keyword change if valid. Stop at `WAITING_FOR_APPROVAL`.” |
| Analyze budget | “Refresh first and assess whether the enabled campaign is budget constrained. Do not change it.” |
| Prepare a budget change | “Read the current budget and prepare an `UPDATE_BUDGET` to `<TARGET>`. Stop at `WAITING_FOR_APPROVAL`.” |
| Create a Search campaign | “Prepare a paused Search campaign using the supplied campaign, targeting, keyword, and RSA details. Stop for approval.” |
| List pending Runs | “List non-terminal Spire Runs first. Do not approve or resume anything.” |
| Inspect a Run | “Inspect Run `<RUN_ID>` and explain its validation, approval, dispatch, and verification state. Do not modify it.” |
| Resume an approved Run | “Verify approval for Run `<RUN_ID>`, resume that same Run, and report semantic verification. Do not create another Run.” |
