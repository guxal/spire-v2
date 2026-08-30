---
type: guide
domain: application
status: stable
tags: [architecture, codegraph]
---

# CodeGraph architecture workflow

## Purpose

CodeGraph is machine-facing architecture intelligence for Spire. Agents use it
before a non-trivial change to locate symbols, trace callers and callees,
inspect blast radius, and connect implementation structure to the relevant
ADRs.

It does not replace ADRs:

- **ADRs** define architectural intent and invariants.
- **CodeGraph** reveals current structural relationships and affected tests.

This is distinct from the human-facing Obsidian **Code Graph** plugin. See
[Obsidian architecture navigation](obsidian.md).

## Installation and availability

This checkout was verified with CodeGraph `1.6.0`:

```bash
codegraph version
```

The repository does not prescribe a package-manager installation command.
Use the team-managed CodeGraph CLI installation, then verify that `codegraph`
is available with the command above.

## Initialize the repository

From the repository root, run:

```bash
codegraph init .
```

In CodeGraph 1.6.0 this builds the initial index and creates
`.codegraph/codegraph.db` (with a local `.codegraph/.gitignore`). The index is
local developer state, not a product runtime dependency.

Verify initialization without reading source manually:

```bash
codegraph status --json .
```

The result should report `initialized: true`, an `indexPath` ending in
`.codegraph`, and `state: complete`.

## MCP configuration for Codex

The installed CodeGraph CLI prints the current Codex configuration with:

```bash
codegraph install --print-config codex
```

For the verified 1.6.0 installation, the resulting Codex configuration is:

```toml
[mcp_servers.codegraph]
command = "codegraph"
args = ["serve", "--mcp"]
```

After configuring Codex, verify the configured server without exposing any
source or credentials:

```bash
codex mcp get codegraph
```

When the MCP server is available to an agent, use its CodeGraph exploration
capabilities (for example `codegraph_explore`) first. The portable shell
fallback is:

```bash
codegraph explore "PublicApi AccountSnapshot DatasetResolver"
```

## Architecture preflight

For each non-trivial change:

```text
task
→ CodeGraph
→ relevant accepted ADRs
→ affected domain
→ critical symbols
→ upstream/downstream
→ public contracts and invariants
→ owning tests
→ blast radius
→ smallest compliant change
```

Use a focused `explore`, `node`, `impact`, `callers`, `callees`, or `affected`
query. Then compare graph reality with the governing accepted ADR. If they
conflict, stop the dependent change and report the conflict; do not use current
code to silently override an accepted decision.

## Updating the graph

After a bounded edit, synchronize the existing index:

```bash
codegraph sync .
```

Rebuild from scratch when CodeGraph recommends it, after an index failure, or
when a broad structural change makes incremental state unsuitable:

```bash
codegraph index .
```

`codegraph status --json .` reports pending changes and whether a reindex is
recommended. The graph is an analysis aid; it never grants edit, production,
or approval authority.
