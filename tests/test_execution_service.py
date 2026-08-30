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
