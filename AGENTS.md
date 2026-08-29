# AGENTS.md instructions

## Architecture preflight

For every non-trivial change:

1. Inspect the relevant accepted ADRs in `docs/adr/` before editing.
2. If the reference repository is involved, use CodeGraph against `../spire-agent`
   before reading or extracting implementation behavior.
3. State the smallest compliant change, its inward dependencies, and the tests
   that prove the boundary.
4. Re-run architecture guards and focused tests before declaring the change done.

Accepted ADRs are architectural authority for this repository. Historical code
is evidence, not authority. Use the smallest compliant implementation and do
not add hidden legacy compatibility, fallback paths, or runtime dependencies on
`../spire-agent`.

## CodeGraph

In repositories indexed by CodeGraph (a `.codegraph/` directory exists at the repo root), reach for it before grep/find or reading files when you need to understand or locate code:

- Use the `codegraph_explore` MCP tool when available. It answers most code questions in one call with relevant symbols, verbatim source, and call paths.
- The shell fallback is `codegraph explore "<symbol names or question>"`.

If there is no `.codegraph/` directory, skip CodeGraph entirely.
