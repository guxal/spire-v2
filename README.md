# Spire v2

## Quick Start

1. Install: `uv sync` (or `python -m pip install -e ".[dev]"`).
2. Configure and authenticate: `cp config/google-ads.example.yaml config/google-ads.yaml`, edit it, then run `spire auth google-ads login`.
3. Verify: `spire auth google-ads verify` and select an account from the MCC picker, or use `--customer-id <customer_id>` for a direct check.
4. Discover: `spire campaigns discover`.
5. Refresh frozen truth: `spire account refresh`.
6. Read a campaign: `spire campaigns get`.
7. Query evidence: `spire evidence query --dataset campaign_daily`.

Authentication details, credential locations, cache behavior, and
troubleshooting are documented in [Google Ads Authentication](docs/google-ads-auth.md).

## CLI interaction

All commands accept explicit identifiers. Safe read commands can offer a
picker when an ID is omitted in an interactive terminal. `--no-input` and
non-interactive execution never wait for input. Use `--json` for automation.
The complete policy is [ADR-0015](docs/adr/0015-cli-interaction-policy.md).

## MCP

Start the real stdio server with `spire mcp`. Installation and host
configuration are documented in [MCP installation](docs/mcp-installation.md).
