---
type: guide
domain: interfaces
status: stable
tags: [architecture, obsidian]
---

# Obsidian architecture navigation

Obsidian is Spire's human architecture-navigation workflow. It is separate
from the machine-facing CodeGraph MCP/CLI described in
[CodeGraph architecture workflow](codegraph.md).

## Current local setup

This repository's `.obsidian` configuration currently enables:

- the community plugin **Code Graph** (`code-graph`, version 1.0.6);
- the core **Bases** plugin;
- the Code Graph graph view with domain colouring and domain zone auras.

Code Graph reads Python structure, imports, calls, containment, tests, ADR
links, and comment metadata. It is a visualizer and navigation aid; CodeGraph
MCP remains the tool for agent-level dependency and blast-radius analysis.

## Set up from zero

1. Open the repository root as an Obsidian vault.
2. In **Settings → Community plugins**, install and enable **Code Graph**.
   It is desktop-only; the installed plugin ID is `code-graph`.
3. In **Settings → Core plugins**, enable **Bases**.
4. Run **Code Graph: Open graph view** from the Command Palette. In the Code
   Graph settings, use **Domain** for colour mode and **Domain** for the
   zone-aura source. Keep the structural edge types enabled.
5. Run **Code Graph: Reindex files** after opening the vault or after a broad
   metadata change. The plugin also refreshes after relevant file changes.
6. Open [Architecture Dashboard](../architecture/Architecture%20Dashboard.md)
   and, with Bases enabled, `docs/architecture/architecture.base` for the
   curated entry points.

The plugin also offers **Code Graph: Seed domains from codebase**. Do not use
it as a routine Spire update: it writes headers based on folder/community
heuristics. Spire's approved domain vocabulary is maintained deliberately in
source metadata and documented below.

## Metadata policy

Production Python modules use these comment tags only:

```text
@file
@domain
@status
@adr
@tested-by
```

Relationships that Python AST/import analysis can infer are not duplicated in
comments. In particular, Spire does not use `@depends-on` or `@see`.

### Domains

The minimum stable taxonomy is:

- `core` — identity, errors, tenant workspace;
- `google-ads` — credentials, provider, authentication, discovery, extraction,
  and campaign reads;
- `truth` — immutable contracts, snapshots, and logical dataset resolution;
- `evidence` — evidence schemas, query semantics, and evidence adapters;
- `execution` — change compilation, policy, authority, run persistence, and
  provider execution;
- `application` — composition and customer-scoped orchestration;
- `interfaces` — CLI, MCP, and storage-independent public projections.

### Status

Code Graph's current status view enumerates `stable`, `wip`, and `deprecated`.
Spire uses `stable` for the accepted production modules documented here. Do
not mark a module `deprecated` without an explicit replacement, and do not use
`wip` to describe an accepted stable-core boundary.

### ADR and test links

Only high-authority modules link a governing ADR with `@adr`. A module gets an
`@tested-by` link only when one primary test file meaningfully proves that
boundary. These are navigation links, not a substitute for the full test suite
or for dependency analysis.

## How to explore

- Start at the architecture dashboard, then filter the Code Graph view by a
  `domain:<name>` query.
- Open a stable-core node to inspect its imported neighbors and its ADR/test
  links.
- Use the dashboard's ADR and test sections to move between intent, code, and
  proof.
- Use Bases for the curated architecture notes. Do not maintain a hand-written
  dependency graph: CodeGraph owns structural truth; Obsidian owns human
  navigation.
