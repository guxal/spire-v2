# MCP Installation

Spire provides an MCP JSON-RPC server over `stdio`. It opens no ports and does
not require an additional MCP package.

## Install

```bash
uv sync
```

Alternatively:

```bash
python -m pip install -e ".[dev]"
```

## Start the server

```bash
spire mcp
```

The process accepts JSON-RPC messages on `stdin` and responds on `stdout`.
Set its working directory to the checkout root so Spire uses that project's
configuration file and workspace.

Conceptual Claude Desktop example:

```json
{
  "mcpServers": {
    "spire": {
      "command": "spire",
      "args": ["mcp"],
      "cwd": "/ruta/al/checkout/spire-v2"
    }
  }
}
```

If the executable is not on `PATH`, use the explicit virtual environment:

```json
{
  "mcpServers": {
    "spire": {
      "command": "/ruta/al/checkout/spire-v2/.venv/bin/spire",
      "args": ["mcp"],
      "cwd": "/ruta/al/checkout/spire-v2"
    }
  }
}
```

## Tools and authority

The server exposes tools for authentication status, accounts, discovery,
explicit refresh, campaigns, evidence, negative candidates, and runs. It can
prepare `UPDATE_BUDGET`, `ADD_NEGATIVE_KEYWORD`, and
`CREATE_SEARCH_CAMPAIGN` runs up to `WAITING_FOR_APPROVAL`; Search campaigns
are always prepared as `PAUSED`.

Segmented Google Ads datasets require a finite date range. For
`account_refresh`, pass `date_range` with `start` and `end` when you need
performance evidence.

It does not expose `approve_run`, `grant_authority`, or `mint_approval`.
Human approval is performed only through the trusted CLI:

```bash
spire runs approve --run-id <run_id>
spire runs resume --run-id <run_id>
```

Initial authentication is performed outside MCP:

```bash
spire auth google-ads login
spire auth google-ads verify --customer-id <customer_id>
```

See [Google Ads Authentication](google-ads-auth.md) for credentials and token
cache information.
