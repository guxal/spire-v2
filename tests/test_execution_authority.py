from spire.execution import (
    AuthoritySource,
    ExecutionMode,
    ExecutionRun,
    ExecutionRunState,
)
from spire.execution.authority import AuthorityService, approval_fingerprint
from spire.execution.store import ExecutionStore


def _run():
    return ExecutionRun(
        "run_approval_1", "spec_approval_1", "1234567890", "1234567890",
        ExecutionMode.PRODUCTION, ExecutionRunState.VALIDATED, "sha256:spec",
        {"snapshot_id": "snapshot_1", "content_hash": "sha256:snapshot"},
        compiled_operation={"content_hash": "sha256:operation"},
        preview={"operation_hash": "sha256:operation", "status": "PASSED"},
        created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z",
    )


def test_approval_is_exactly_bound_and_single_use(tmp_path):
    from spire.core import WorkspacePaths

    store = ExecutionStore(WorkspacePaths(tmp_path), "1234567890")
    run = _run()
    store.save_run(run)
    service = AuthorityService()
    waiting, request = service.request_human_approval(store, run)
    assert waiting.state is ExecutionRunState.WAITING_FOR_APPROVAL
    assert request["fingerprint"] == approval_fingerprint(waiting)
    approved = service.approve_human(
        store, waiting.run_id, principal_id="human@example.test", affirmation=True
    )
    assert approved.state is ExecutionRunState.APPROVED
    assert service.coverage(approved).source is AuthoritySource.HUMAN_RUN_APPROVAL
    consumed = service.consume(store, approved)
    assert consumed.state is ExecutionRunState.APPLYING
    assert service.coverage(consumed).consumed is True
