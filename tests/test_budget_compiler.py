import pytest

from spire.execution import ChangeKind, ChangeSpec
from spire.execution.compiler import BudgetCompiler
from spire.google_ads import RefreshSpec, ScopedRefreshService
from spire.interfaces import DateRange
from spire.truth import AccountSnapshotService


def _spec(snapshot, daily_budget="12.345601"):
    return ChangeSpec(
        spec_id="spec_budget_1",
        customer_id="1234567890",
        account_id="1234567890",
        kind=ChangeKind.UPDATE_BUDGET,
        target={"campaign_id": "101"},
        requested_change={"daily_budget": daily_budget},
        snapshot_ref={
            "snapshot_id": snapshot.snapshot_id,
            "content_hash": snapshot.content_hash,
            "extraction_id": snapshot.extraction_id,
        },
        provenance={"producer": "test"},
    )


def test_budget_compilation_is_deterministic_and_uses_frozen_identity(fake_runtime):
    workspace, provider, calls = fake_runtime
    ScopedRefreshService(provider, workspace).refresh(
        RefreshSpec(customer_id="1234567890", campaign_ids=("101",), date_range=DateRange("2026-08-01", "2026-08-02"))
    )
    snapshot = AccountSnapshotService(workspace).current("1234567890", campaign_ids=("101",))
    spec = _spec(snapshot)
    before = len(calls)
    first = BudgetCompiler(workspace).compile(spec, snapshot)
    second = BudgetCompiler(workspace).compile(spec, snapshot)
    assert len(calls) == before
    assert first == second
    assert first.daily_budget_micros == 12_345_601
    assert first.budget_resource_name == "customers/1234567890/campaignBudgets/9001"
    assert first.content_hash == second.content_hash


def test_budget_compilation_fails_when_frozen_identity_is_missing(fake_runtime):
    workspace, provider, _ = fake_runtime
    ScopedRefreshService(provider, workspace).refresh(
        RefreshSpec(customer_id="1234567890", campaign_ids=("101",), date_range=DateRange("2026-08-01", "2026-08-02"))
    )
    snapshot = AccountSnapshotService(workspace).current("1234567890", campaign_ids=("101",))
    path = workspace.truth("1234567890") / "extractions" / snapshot.extraction_id / "datasets" / "campaigns.jsonl"
    path.write_text(path.read_text().replace('"campaign_budget_resource_name": "customers/1234567890/campaignBudgets/9001",', '"campaign_budget_resource_name": "",'), encoding="utf-8")
    with pytest.raises(Exception, match="DATASET_HASH_MISMATCH:campaigns"):
        BudgetCompiler(workspace).compile(_spec(snapshot), snapshot)
