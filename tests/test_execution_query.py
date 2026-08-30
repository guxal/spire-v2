from __future__ import annotations

import json

import pytest

from spire.application import Application
from spire.core import ArtifactNotFoundError
from spire.execution import (
    ChangeKind,
    ChangeSpec,
    ExecutionMode,
    ExecutionRun,
    ExecutionRunQueryService,
    ExecutionRunState,
)
from spire.execution.store import ExecutionStore
from spire.google_ads import RefreshSpec, ScopedRefreshService
from spire.surfaces import PublicApi
from spire.truth import AccountSnapshotService


def _snapshot(workspace, provider, customer_id: str):
    ScopedRefreshService(provider, workspace).refresh(
        RefreshSpec(customer_id, ("101", "202"))
    )
    return AccountSnapshotService(workspace).current(customer_id)


def _save_run(
    workspace,
    snapshot,
    *,
    run_id: str,
    campaign_id: str,
    state: ExecutionRunState,
    created_at: str,
    updated_at: str,
    proposed: str,
    request_sent: bool = False,
) -> ExecutionRun:
    customer_id = snapshot.customer_id
    snapshot_ref = {
        "snapshot_id": snapshot.snapshot_id,
        "content_hash": snapshot.content_hash,
        "extraction_id": snapshot.extraction_id,
        "source": snapshot.source.value,
        "scope": dict(snapshot.scope),
    }
    spec = ChangeSpec(
        spec_id=f"spec_{run_id}",
        customer_id=customer_id,
        account_id=customer_id,
        kind=ChangeKind.UPDATE_BUDGET,
        target={"campaign_id": campaign_id},
        requested_change={"daily_budget": proposed},
        snapshot_ref=snapshot_ref,
    )
    has_approval = state in {
        ExecutionRunState.WAITING_FOR_APPROVAL,
        ExecutionRunState.APPROVED,
        ExecutionRunState.APPLYING,
        ExecutionRunState.VERIFIED,
        ExecutionRunState.RECONCILING,
    }
    consumed = state in {
        ExecutionRunState.APPLYING,
        ExecutionRunState.VERIFIED,
        ExecutionRunState.RECONCILING,
    }
    authority = (
        {
            "source": "human_run_approval" if state is not ExecutionRunState.WAITING_FOR_APPROVAL else "none",
            "consumed": consumed,
        }
        if has_approval
        else None
    )
    run = ExecutionRun(
        run_id=run_id,
        spec_id=spec.spec_id,
        customer_id=customer_id,
        account_id=customer_id,
        mode=ExecutionMode.PRODUCTION,
        state=state,
        spec_hash=spec.content_hash,
        snapshot_ref=snapshot_ref,
        compiled_operation={
            "kind": ChangeKind.UPDATE_BUDGET.value,
            "campaign_id": campaign_id,
            "daily_budget_micros": int(proposed) * 1_000_000,
            "content_hash": f"sha256:{run_id}",
        },
        preview={"status": "PASSED", "operation_hash": f"sha256:{run_id}"},
        policy={"status": "ALLOWED"},
        authority=authority,
        approval_fingerprint=f"sha256:fingerprint-{run_id}" if has_approval else "",
        approval_request_id=f"approval_{run_id}" if has_approval else "",
        request_sent={"status": "REQUEST_SENT", "sent_at": updated_at}
        if request_sent
        else None,
        verification={"status": "VERIFIED"}
        if state is ExecutionRunState.VERIFIED
        else None,
        created_at=created_at,
        updated_at=updated_at,
    )
    store = ExecutionStore(workspace, customer_id)
    store.save_spec(spec)
    store.save_run(run)
    return run


@pytest.fixture
def discovered_runs(fake_runtime):
    workspace, provider, _calls = fake_runtime
    first = _snapshot(workspace, provider, "1234567890")
    second = _snapshot(workspace, provider, "9876543210")
    waiting = _save_run(
        workspace,
        first,
        run_id="run_waiting",
        campaign_id="101",
        state=ExecutionRunState.WAITING_FOR_APPROVAL,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-04T00:00:00Z",
        proposed="13",
    )
    verified = _save_run(
        workspace,
        first,
        run_id="run_verified",
        campaign_id="202",
        state=ExecutionRunState.VERIFIED,
        created_at="2026-01-02T00:00:00Z",
        updated_at="2026-01-02T00:00:00Z",
        proposed="21",
        request_sent=True,
    )
    failed = _save_run(
        workspace,
        second,
        run_id="run_failed",
        campaign_id="101",
        state=ExecutionRunState.FAILED,
        created_at="2026-01-03T00:00:00Z",
        updated_at="2026-01-03T00:00:00Z",
        proposed="14",
    )
    return workspace, provider, waiting, verified, failed


def test_list_all_runs_and_filter_by_customer_campaign_and_state(discovered_runs):
    workspace, _provider, waiting, verified, failed = discovered_runs
    queries = ExecutionRunQueryService(workspace)

    assert [item["run_id"] for item in queries.list_runs()] == [
        failed.run_id,
        verified.run_id,
        waiting.run_id,
    ]
    assert [item["run_id"] for item in queries.list_runs(customer_id="1234567890")] == [
        verified.run_id,
        waiting.run_id,
    ]
    assert [item["run_id"] for item in queries.list_runs(campaign_id="202")] == [
        verified.run_id
    ]
    selected = queries.list_runs(state="waiting_for_approval")
    assert [item["run_id"] for item in selected] == [waiting.run_id]
    assert selected[0]["current_value"] == "12.5"
    assert selected[0]["proposed_value"] == "13"
    assert selected[0]["currency"] == "USD"


def test_order_limit_terminal_and_request_sent_are_deterministic(discovered_runs):
    workspace, provider, waiting, verified, failed = discovered_runs
    queries = ExecutionRunQueryService(workspace)

    by_update = queries.list_runs(order_by="updated_at", limit=2)
    assert [item["run_id"] for item in by_update] == [waiting.run_id, failed.run_id]
    assert queries.get_run(waiting.run_id)["terminal"] is False
    assert queries.get_run(waiting.run_id)["request_sent"] is False
    assert queries.get_run(verified.run_id)["terminal"] is True
    assert queries.get_run(verified.run_id)["request_sent"] is True
    assert queries.get_run(failed.run_id)["terminal"] is True

    api = PublicApi(
        Application(workspace, provider_factory=lambda _workspace, _customer_id: provider)
    )
    latest = api.runs_list(customer_id="1234567890", latest=True)
    assert latest["run_id"] == verified.run_id


def test_safe_projection_and_stable_not_found(discovered_runs, tmp_path):
    workspace, _provider, waiting, _verified, _failed = discovered_runs
    queries = ExecutionRunQueryService(workspace)
    payload = queries.get_run(waiting.run_id)
    serialized = json.dumps(payload, sort_keys=True)

    assert str(tmp_path) not in serialized
    assert "resource_name" not in serialized
    assert "compiled_operation" not in serialized
    assert "spec_id" not in serialized
    assert payload["approval_required"] is True
    assert payload["approval_state"] == "PENDING"
    assert payload["verification_state"] == "NOT_STARTED"
    with pytest.raises(ArtifactNotFoundError, match="EXECUTION_RUN_NOT_FOUND"):
        queries.list_runs(customer_id="1111111111")
