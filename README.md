# Spire v2

## Quick Start

1. Install: `python -m pip install -e ".[dev]"`
2. Configure and authenticate: `cp config/google-ads.example.yaml config/google-ads.yaml`, edit it, then run `spire auth google-ads login`.
3. Verify: `spire auth google-ads verify` and select an account from the MCC picker, or use `--customer-id <customer_id>` for a direct check.
4. Discover the account with the account discovery capability.
5. Run an explicit scoped account refresh.
6. Read a frozen campaign with `campaigns(get)`.
7. Query frozen evidence with `evidence_query`.

Authentication details, credential locations, cache behavior, and
troubleshooting are documented in [Google Ads Authentication](docs/google-ads-auth.md).

MCP is not yet distributed as a runnable server. See [MCP installation status](docs/mcp-installation.md)
before configuring an external MCP host.
