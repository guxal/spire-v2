from __future__ import annotations

import io
import json
from types import SimpleNamespace

from mcp.types import CallToolResult

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

    def geo_targets_suggest(self, customer_id, names, country_code, **kwargs):
        return {
            "geo_targets": [
                {
                    "id": "100",
                    "resource_name": "geoTargetConstants/100",
                    "name": names[0],
                    "canonical_name": f"{names[0]}, {country_code}",
                    "country_code": country_code,
                    "target_type": "City",
                    "status": "ENABLED",
                    "search_term": names[0],
                    "reach": 1000,
                }
            ]
        }

    def account_refresh(self, customer_id, **kwargs):
        return {"customer_id": customer_id, "status": "COMPLETE"}

    def campaigns_discover(self, customer_id):
        return {"customer_id": customer_id, "campaigns": []}

    def evidence_query(self, customer_id, campaign_ids, dataset, **kwargs):
        return {"customer_id": customer_id, "dataset": dataset, "rows": []}

    def evidence_datasets(self, customer_id, campaign_id):
        return {"customer_id": customer_id, "campaign_id": campaign_id, "datasets": []}

    def change_budget(self, customer_id, campaign_id, daily_budget, **kwargs):
        return {"customer_id": customer_id, "campaign_id": campaign_id, "run_id": "run_budget"}

    def negative_keyword_candidates(self, customer_id, campaign_id):
        return {"customer_id": customer_id, "campaign_id": campaign_id, "candidates": []}

    def change_negative_keyword(self, customer_id, campaign_id, text, match_type, **kwargs):
        return {"customer_id": customer_id, "campaign_id": campaign_id, "run_id": "run_negative"}

    def create_search_campaign(self, customer_id, request, **kwargs):
        return {"customer_id": customer_id, "run_id": "run_campaign"}

    def runs_list(self, **filters):
        self.runs_filters = filters
        runs = [{"run_id": "run_test", "state": "WAITING_FOR_APPROVAL"}]
        return runs[0] if filters.get("latest") else runs

    def run_get(self, run_id):
        return {"run_id": run_id, "state": "WAITING_FOR_APPROVAL"}

    def run_resume(self, run_id):
        return {"run_id": run_id, "state": "VERIFIED"}


def _mcp_call(server, name, arguments=None):
    return server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        }
    )["result"]


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
    refresh = next(tool for tool in listed["result"]["tools"] if tool["name"] == "account_refresh")
    assert refresh["inputSchema"]["required"] == ["customer_id", "date_range"]
    assert refresh["inputSchema"]["properties"]["date_range"]["required"] == ["start", "end"]
    assert "change_budget" in names
    assert "geo_targets_suggest" in names
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


def test_mcp_collection_results_wrap_application_lists_and_preserve_text_content():
    api = FakeApi()
    server = McpServer(api)

    assert isinstance(api.accounts_list(), list)
    accounts = _mcp_call(server, "accounts_list")
    assert accounts["structuredContent"] == {
        "accounts": [{"customer_id": "1234567890", "name": "Example"}]
    }
    assert json.loads(accounts["content"][0]["text"]) == accounts["structuredContent"]

    assert isinstance(api.campaigns_list("1234567890"), list)
    campaigns_result = _mcp_call(server, "campaigns_list", {"customer_id": "1234567890"})
    assert campaigns_result["structuredContent"] == {
        "campaigns": [{"campaign_id": "101", "name": "Search", "status": "ENABLED"}]
    }


def test_mcp_accounts_list_wraps_an_empty_application_result(monkeypatch):
    api = FakeApi()
    monkeypatch.setattr(api, "accounts_list", list)

    result = _mcp_call(McpServer(api), "accounts_list")

    assert result["structuredContent"] == {"accounts": []}


def test_mcp_runs_list_has_a_stable_plural_envelope_for_both_modes():
    api = FakeApi()
    server = McpServer(api)

    normal = _mcp_call(server, "runs_list")
    latest = _mcp_call(server, "runs_list", {"latest": True})

    expected_runs = [{"run_id": "run_test", "state": "WAITING_FOR_APPROVAL"}]
    assert normal["structuredContent"] == {"runs": expected_runs}
    assert latest["structuredContent"] == {"runs": expected_runs}


def test_every_published_successful_mcp_result_has_object_structured_content():
    server = McpServer(FakeApi())
    calls = (
        ("auth_status", {}),
        ("accounts_list", {}),
        ("account_refresh", {"customer_id": "1234567890"}),
        ("campaigns_discover", {"customer_id": "1234567890"}),
        ("campaigns_list", {"customer_id": "1234567890"}),
        ("campaigns_get", {"customer_id": "1234567890", "campaign_id": "101"}),
        (
            "geo_targets_suggest",
            {
                "customer_id": "1234567890",
                "names": ["Pamplona"],
                "country_code": "ES",
                "locale": "es",
            },
        ),
        (
            "evidence_query",
            {"customer_id": "1234567890", "campaign_ids": ["101"], "dataset": "campaign_daily"},
        ),
        ("evidence_datasets", {"customer_id": "1234567890", "campaign_id": "101"}),
        (
            "change_budget",
            {
                "customer_id": "1234567890",
                "campaign_id": "101",
                "daily_budget": 10,
                "environment": "production",
            },
        ),
        ("negative_keyword_candidates", {"customer_id": "1234567890", "campaign_id": "101"}),
        (
            "change_negative_keyword",
            {
                "customer_id": "1234567890",
                "campaign_id": "101",
                "text": "term",
                "match_type": "EXACT",
                "environment": "production",
            },
        ),
        (
            "create_search_campaign",
            {"customer_id": "1234567890", "request": {}, "environment": "production"},
        ),
        ("runs_list", {}),
        ("run_get", {"run_id": "run_test"}),
        ("run_resume", {"run_id": "run_test"}),
    )

    for name, arguments in calls:
        result = _mcp_call(server, name, arguments)
        assert result["isError"] is False, name
        assert isinstance(result["structuredContent"], dict), name
        assert json.loads(result["content"][0]["text"]) == result["structuredContent"], name


def test_mcp_response_is_accepted_by_the_installed_mcp_call_tool_result_model():
    response = _mcp_call(McpServer(FakeApi()), "accounts_list")

    parsed = CallToolResult.model_validate(response)

    assert parsed.structuredContent == {
        "accounts": [{"customer_id": "1234567890", "name": "Example"}]
    }


def test_mcp_geo_target_suggestions_are_object_shaped_and_preserve_errors():
    arguments = {
        "customer_id": "1234567890",
        "names": ["Pamplona"],
        "country_code": "ES",
        "locale": "es",
    }
    response = _mcp_call(McpServer(FakeApi()), "geo_targets_suggest", arguments)

    parsed = CallToolResult.model_validate(response)
    assert parsed.structuredContent == response["structuredContent"]
    assert response["structuredContent"]["geo_targets"][0]["canonical_name"] == "Pamplona, ES"

    class ProviderUnavailableApi(FakeApi):
        def geo_targets_suggest(self, *args, **kwargs):
            raise OSError("unavailable")

    failed = _mcp_call(McpServer(ProviderUnavailableApi()), "geo_targets_suggest", arguments)
    assert failed["isError"] is True
    assert failed["structuredContent"] == {"error": "PROVIDER_UNAVAILABLE"}


def test_mcp_stdio_is_json_rpc_and_uses_structured_content():
    incoming = io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}) + "\n")
    outgoing = io.StringIO()
    serve(FakeApplication(), input_stream=incoming, output_stream=outgoing)
    response = json.loads(outgoing.getvalue())
    assert response["result"]["protocolVersion"] == "2024-11-05"


def test_mcp_schemas_have_explicit_scope_for_reads():
    schemas = {name: schema for name, _, schema in TOOLS}
    assert schemas["campaigns_get"]["required"] == ["customer_id", "campaign_id"]
    assert schemas["geo_targets_suggest"]["required"] == ["customer_id", "names", "country_code"]
    assert schemas["evidence_query"]["required"] == ["customer_id", "campaign_ids", "dataset"]
    assert schemas["change_negative_keyword"]["required"] == ["customer_id", "campaign_id", "text", "match_type", "environment"]
    assert schemas["create_search_campaign"]["required"] == ["customer_id", "request", "environment"]


def test_public_api_clean_workspace_refresh_and_frozen_reads(fake_runtime):
    workspace, provider, _calls = fake_runtime
    application = Application(workspace, provider_factory=lambda _workspace, _customer_id: provider)
    api = PublicApi(application)

    refreshed = api.account_refresh(
        "1234567890",
        campaign_id="101",
        date_range={"start": "2026-08-01", "end": "2026-08-02"},
    )
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


def test_evidence_datasets_resolves_compatible_finalized_snapshot_across_campaign_switches(fake_runtime):
    workspace, provider, _calls = fake_runtime
    api = PublicApi(Application(workspace, provider_factory=lambda _workspace, _customer_id: provider))

    api.account_refresh(
        "1234567890",
        campaign_id="101",
        date_range={"start": "2026-08-01", "end": "2026-08-02"},
    )
    api.account_refresh(
        "1234567890",
        campaign_id="202",
        date_range={"start": "2026-08-01", "end": "2026-08-02"},
    )

    for campaign_id in ("101", "202", "101"):
        datasets = api.evidence_datasets("1234567890", campaign_id)
        assert datasets["campaign_id"] == campaign_id
        assert {dataset["dataset"] for dataset in datasets["datasets"]} >= {"campaigns", "campaign_daily"}


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
