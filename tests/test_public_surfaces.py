from __future__ import annotations

import io
import json
from types import SimpleNamespace

from spire.application import Application
from spire.cli_commands import auth, campaigns, execution
from spire.cli_commands.common import CommandContext, require_customer
from spire.execution import CompiledOperation, GoogleAdsGateway
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

    def runs_list(self, **filters):
        self.runs_filters = filters
        return [{"run_id": "run_test", "state": "WAITING_FOR_APPROVAL"}]


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


def test_auth_and_approval_never_prompt_without_terminal():
    context = CommandContext(FakeApi(), no_input=True)
    try:
        auth.login(context, type("Args", (), {"port": 8080})())
    except ValueError as exc:
        assert str(exc) == "INTERACTIVE_AUTH_REQUIRED"
    else:
        raise AssertionError("OAuth must not prompt without a terminal")

    class ApprovalApi(FakeApi):
        def run_approval_preview(self, run_id):
            return {"run_id": run_id, "fingerprint": "sha256:test"}

    try:
        execution.approve(
            CommandContext(ApprovalApi(), no_input=True),
            type("Args", (), {"run_id": "run_test123", "yes": False, "principal": None})(),
        )
    except ValueError as exc:
        assert str(exc) == "APPROVAL_REQUIRED_INTERACTIVE"
    else:
        raise AssertionError("approval must not prompt without a terminal")


def test_mcp_handshake_tools_and_no_approval_tool():
    server = McpServer(FakeApi())
    initialized = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert initialized["result"]["serverInfo"]["name"] == "spire"
    listed = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert "change_budget" in names
    assert "negative_keyword_candidates" in names
    assert "change_negative_keyword" in names
    assert "create_search_campaign" in names
    assert "runs_list" in names
    assert "approve_run" not in names
    assert "grant_authority" not in names


def test_mcp_runs_list_delegates_safe_filters_to_public_api():
    api = FakeApi()
    server = McpServer(api)
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "runs_list",
                "arguments": {
                    "customer_id": "1234567890",
                    "campaign_id": "101",
                    "status": "waiting_for_approval",
                    "limit": 3,
                    "latest": True,
                    "order_by": "updated_at",
                },
            },
        }
    )
    assert response["result"]["isError"] is False
    assert api.runs_filters == {
        "customer_id": "1234567890",
        "campaign_id": "101",
        "state": "waiting_for_approval",
        "limit": 3,
        "latest": True,
        "order_by": "updated_at",
    }


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
    assert schemas["change_negative_keyword"]["required"] == ["customer_id", "campaign_id", "text", "match_type", "environment"]
    assert schemas["create_search_campaign"]["required"] == ["customer_id", "request", "environment"]


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


def test_google_ads_budget_operation_places_update_mask_on_operation():
    operation = CompiledOperation(
        operation_id="operation_test123",
        customer_id="1234567890",
        campaign_id="101",
        kind="UPDATE_BUDGET",
        budget_resource_name="customers/1234567890/campaignBudgets/9001",
        daily_budget_micros=13_000_000,
        snapshot_hash="sha256:snapshot",
    )
    api_operation = SimpleNamespace(
        campaign_budget_operation=SimpleNamespace(
            update=SimpleNamespace(), update_mask=SimpleNamespace(paths=[])
        )
    )

    class Service:
        def mutate(self, **kwargs):
            self.kwargs = kwargs

    service = Service()

    class Client:
        def get_type(self, name):
            if name == "MutateOperation":
                return api_operation
            assert name == "MutateGoogleAdsRequest"
            return SimpleNamespace(customer_id="", mutate_operations=[], validate_only=False)

        def get_service(self, name):
            assert name == "GoogleAdsService"
            return service

    gateway = GoogleAdsGateway(SimpleNamespace(get_client=lambda: Client()))
    result = gateway.validate_only(operation)
    assert result.status == "PASSED"
    assert api_operation.campaign_budget_operation.update_mask.paths == ["amount_micros"]
