import pytest

from spire.core import ArtifactNotFoundError
from spire.execution import BudgetCompiler
from spire.execution.authority import AuthorityService
from spire.execution.policy import HardPolicyService
from spire.execution.service import ExecutionRunService
from spire.google_ads import RefreshSpec, ScopedRefreshService
from spire.interfaces import DateRange
from spire.truth import AccountSnapshotService


class _PreviewRuntime:
    def __init__(self):
        self.preview_calls = 0
        self.mutate_calls = 0

    def validate_only(self, operation):
        from spire.execution import PreviewResult

        self.preview_calls += 1
        return PreviewResult("PASSED", operation.content_hash, "2026-01-01T00:00:00Z")

    def mutate(self, operation):
        self.mutate_calls += 1
        raise AssertionError("preview must not mutate")


class _FullRuntime(_PreviewRuntime):
    def __init__(self):
        super().__init__()
        self.mutated_hashes = []

    def mutate(self, operation):
        self.mutate_calls += 1
        self.mutated_hashes.append(operation.content_hash)
        return {"status": "SENT"}

    def verify(self, operation):
        from spire.execution import VerificationResult

        return VerificationResult(
            "VERIFIED",
            {"daily_budget_micros": operation.daily_budget_micros},
            {"campaign_id": operation.campaign_id, "daily_budget_micros": operation.daily_budget_micros},
            "2026-01-01T00:00:01Z",
        )


def _service(workspace, provider, runtime):
    return ExecutionRunService(
        workspace,
        snapshots=AccountSnapshotService(workspace),
        compiler=BudgetCompiler(workspace),
        policy=HardPolicyService(),
        authority=AuthorityService(),
        runtime=runtime,
    )


def test_prepare_stops_at_one_exact_human_approval_boundary(fake_runtime):
    workspace, provider, _ = fake_runtime
    ScopedRefreshService(provider, workspace).refresh(RefreshSpec("1234567890", ("101",), DateRange("2026-08-01", "2026-08-02")))
    runtime = _PreviewRuntime()
    result = _service(workspace, provider, runtime).prepare_change_budget(
        "1234567890", "101", "13", provenance={"producer": "test"}
    )
    assert result["state"] == "WAITING_FOR_APPROVAL"
    assert result["approval_request_id"]
    assert result["fingerprint"].startswith("sha256:")
    assert runtime.preview_calls == 1
    assert runtime.mutate_calls == 0
    assert len(list((workspace.execution("1234567890") / "runs").glob("*.json"))) == 1
    assert len(list((workspace.execution("1234567890") / "approval_requests").glob("*.json"))) == 1


def test_governed_preparation_keeps_strict_current_snapshot_scope(fake_runtime):
    workspace, provider, _ = fake_runtime
    refresh = ScopedRefreshService(provider, workspace)
    refresh.refresh(RefreshSpec("1234567890", ("101",), DateRange("2026-08-01", "2026-08-02")))
    refresh.refresh(RefreshSpec("1234567890", ("202",), DateRange("2026-08-01", "2026-08-02")))

    with pytest.raises(ArtifactNotFoundError, match="CURRENT_SNAPSHOT_SCOPE_MISMATCH"):
        _service(workspace, provider, _PreviewRuntime()).prepare_change_budget(
            "1234567890", "101", "13", provenance={"producer": "test"}
        )


def test_new_change_kinds_prepare_through_the_same_execution_run(fake_runtime):
    workspace, provider, _ = fake_runtime
    ScopedRefreshService(provider, workspace).refresh(RefreshSpec("1234567890", ("101",), DateRange("2026-08-01", "2026-08-02")))
    service = _service(workspace, provider, _PreviewRuntime())

    negative = service.prepare_add_negative_keyword("1234567890", "101", "free quote", "EXACT")
    campaign = service.prepare_create_search_campaign(
        "1234567890",
        {
            "campaign_name": "Paused Search Test",
            "daily_budget": "10",
            "geo_target_ids": ["2170"],
            "language_criterion_ids": ["1003"],
            "bidding_strategy": "MAXIMIZE_CLICKS",
            "ad_groups": [
                {
                    "name": "Core",
                    "keywords": [{"text": "roof repair", "match_type": "PHRASE"}],
                    "headlines": ["Roof repair", "Local roofers", "Request a quote"],
                    "descriptions": ["Professional roof repair.", "Request a local quote today."],
                    "final_url": "https://example.test/roof-repair",
                }
            ],
        },
    )

    assert negative["state"] == campaign["state"] == "WAITING_FOR_APPROVAL"
    store = service._store_factory(workspace, "1234567890")
    assert store.load_spec(store.load_run(negative["run_id"]).spec_id).kind.value == "ADD_NEGATIVE_KEYWORD"
    assert store.load_spec(store.load_run(campaign["run_id"]).spec_id).kind.value == "CREATE_SEARCH_CAMPAIGN"


def test_trusted_approval_reuses_exact_operation_and_verifies(fake_runtime):
    from spire.interfaces import McpExecutionSurface, TrustedExecutionCli

    workspace, provider, _ = fake_runtime
    ScopedRefreshService(provider, workspace).refresh(RefreshSpec("1234567890", ("101",), DateRange("2026-08-01", "2026-08-02")))
    runtime = _FullRuntime()
    service = _service(workspace, provider, runtime)
    mcp = McpExecutionSurface(service)
    prepared = mcp.change_budget("1234567890", "101", "13")
    assert not hasattr(mcp, "approve_run")
    cli = TrustedExecutionCli(service)
    approved = cli.approve_run(
        prepared["run_id"],
        customer_id="1234567890",
        principal_id="human@example.test",
        affirmation=True,
    )
    completed = cli.execute_run(prepared["run_id"], customer_id="1234567890")
    assert approved["state"] == "APPROVED"
    assert completed["state"] == "VERIFIED"
    assert runtime.mutated_hashes == [prepared["preview"]["operation_hash"]]
    assert completed["request_sent"]["status"] == "REQUEST_SENT"
