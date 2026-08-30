import pytest

from spire.execution import BudgetCompiler, PreviewResult
from spire.execution.authority import AuthorityService
from spire.execution.policy import HardPolicyService
from spire.execution.runtime import ProviderUnavailableError
from spire.execution.service import ExecutionRunService
from spire.google_ads import RefreshSpec, ScopedRefreshService
from spire.truth import AccountSnapshotService


class _AmbiguousRuntime:
    def validate_only(self, operation):
        return PreviewResult("PASSED", operation.content_hash, "2026-01-01T00:00:00Z")

    def mutate(self, operation):
        self.mutate_count = getattr(self, "mutate_count", 0) + 1
        raise ProviderUnavailableError("connection closed after send")

    def verify(self, operation):
        raise AssertionError("ambiguous transport must not guess with read-back")


def test_ambiguous_send_is_reconciling_and_never_retried(fake_runtime):
    workspace, provider, _ = fake_runtime
    ScopedRefreshService(provider, workspace).refresh(RefreshSpec("1234567890", ("101",)))
    runtime = _AmbiguousRuntime()
    service = ExecutionRunService(
        workspace,
        snapshots=AccountSnapshotService(workspace),
        compiler=BudgetCompiler(workspace),
        policy=HardPolicyService(),
        authority=AuthorityService(),
        runtime=runtime,
    )
    prepared = service.prepare_change_budget("1234567890", "101", "13")
    service.approve_human(
        prepared["run_id"], customer_id="1234567890", principal_id="human", affirmation=True
    )
    result = service.execute_approved(prepared["run_id"], customer_id="1234567890")
    assert result["state"] == "RECONCILING"
    assert result["request_sent"]["status"] == "REQUEST_SENT"
    assert result["request_sent"]["transport"] == "AMBIGUOUS"
    assert runtime.mutate_count == 1
    with pytest.raises(ValueError, match="RUN_NOT_APPROVED"):
        service.execute_approved(prepared["run_id"], customer_id="1234567890")
