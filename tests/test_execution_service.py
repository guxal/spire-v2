from spire.execution import BudgetCompiler
from spire.execution.authority import AuthorityService
from spire.execution.policy import HardPolicyService
from spire.execution.service import ExecutionRunService
from spire.google_ads import RefreshSpec, ScopedRefreshService
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
    ScopedRefreshService(provider, workspace).refresh(RefreshSpec("1234567890", ("101",)))
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


def test_trusted_approval_reuses_exact_operation_and_verifies(fake_runtime):
    from spire.interfaces import McpExecutionSurface, TrustedExecutionCli

    workspace, provider, _ = fake_runtime
    ScopedRefreshService(provider, workspace).refresh(RefreshSpec("1234567890", ("101",)))
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
