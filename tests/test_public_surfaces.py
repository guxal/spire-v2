from __future__ import annotations

import io
import json

from spire.application import Application
from spire.cli_commands import campaigns
from spire.cli_commands.common import CommandContext, require_customer
from spire.mcp_server import TOOLS, McpServer, serve
from spire.surfaces import PublicApi


class FakeAuth:
    def status(self):
        return {"configured": "NO", "refresh_token": "MISSING"}


class FakeApplication:
    auth = FakeAuth()


class FakeApi:
    application = FakeApplication()

    def __init__(self):
        self.accounts_calls = 0

    def accounts_list(self):
        self.accounts_calls += 1
        return [{"customer_id": "1234567890", "name": "Example"}]

    def campaigns_list(self, customer_id):
        return [{"campaign_id": "101", "name": "Search", "status": "ENABLED"}]

    def campaigns_get(self, customer_id, campaign_id):
        return {"campaign_id": campaign_id, "name": "Search", "daily_budget": 10, "currency": "USD"}


def test_picker_selects_account_and_explicit_id_skips_picker(monkeypatch):
    api = FakeApi()
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    selected = require_customer(CommandContext(api, input_fn=lambda _: "1"), None)
    assert selected == "1234567890"
    assert api.accounts_calls == 1
    assert require_customer(CommandContext(api), "1234567890") == "1234567890"
    assert api.accounts_calls == 1


def test_campaign_picker_rejects_invalid_selection(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    context = CommandContext(FakeApi(), input_fn=lambda _: "9")
    args = type("Args", (), {"customer_id": "1234567890", "campaign_id": None})()
    try:
        campaigns.get_campaign(context, args)
    except ValueError as exc:
        assert str(exc) == "CAMPAIGN_SELECTION_INVALID"
    else:
        raise AssertionError("invalid picker selection should fail")


def test_missing_id_is_non_interactive_failure():
    context = CommandContext(FakeApi(), no_input=True)
    try:
        require_customer(context, None)
    except ValueError as exc:
        assert str(exc) == "CUSTOMER_ID_REQUIRED_NON_INTERACTIVE"
    else:
        raise AssertionError("non-interactive command should not pick")


def test_mcp_handshake_tools_and_no_approval_tool():
    server = McpServer(FakeApi())
    initialized = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert initialized["result"]["serverInfo"]["name"] == "spire"
    listed = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert "change_budget" in names
    assert "approve_run" not in names
    assert "grant_authority" not in names


def test_mcp_stdio_is_json_rpc_and_uses_structured_content():
    incoming = io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}) + "\n")
    outgoing = io.StringIO()
    serve(FakeApplication(), input_stream=incoming, output_stream=outgoing)
    response = json.loads(outgoing.getvalue())
    assert response["result"]["protocolVersion"] == "2024-11-05"


def test_mcp_schemas_have_explicit_scope_for_reads():
    schemas = {name: schema for name, _, schema in TOOLS}
    assert schemas["campaigns_get"]["required"] == ["customer_id", "campaign_id"]
    assert schemas["evidence_query"]["required"] == ["customer_id", "campaign_ids", "dataset"]


def test_public_api_clean_workspace_refresh_and_frozen_reads(fake_runtime):
    workspace, provider, _calls = fake_runtime
    application = Application(workspace, provider_factory=lambda _workspace, _customer_id: provider)
    api = PublicApi(application)

    refreshed = api.account_refresh("1234567890", campaign_id="101")
    assert refreshed["status"] == "COMPLETE"
    assert api.campaigns_get("1234567890", "101")["daily_budget"] == 12.5
    evidence = api.evidence_query(
        "1234567890",
        ["101"],
        "campaign_daily",
        dimensions=["date"],
        metrics=["impressions", "clicks", "ctr", "cpc_micros", "cpa_micros"],
    )
    assert evidence["scope"]["campaign_ids"] == ["101"]
    assert "campaign_daily" in evidence["evidence_ref"]
