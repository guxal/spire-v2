from dataclasses import replace

from spire.execution import BudgetCompiler, ChangeKind, ChangeSpec
from spire.execution.policy import HardPolicyService
from spire.google_ads import RefreshSpec, ScopedRefreshService
from spire.interfaces import DateRange
from spire.truth import AccountSnapshotService


def test_hard_policy_allows_fresh_exact_production_operation(fake_runtime):
    workspace, provider, _ = fake_runtime
    ScopedRefreshService(provider, workspace).refresh(RefreshSpec("1234567890", ("101",), DateRange("2026-08-01", "2026-08-02")))
    snapshot = AccountSnapshotService(workspace).current("1234567890", campaign_ids=("101",))
    spec = ChangeSpec(
        "spec_policy_1", "1234567890", "1234567890", ChangeKind.UPDATE_BUDGET,
        {"campaign_id": "101"}, {"daily_budget": "13"},
        {"snapshot_id": snapshot.snapshot_id, "content_hash": snapshot.content_hash},
    )
    operation = BudgetCompiler(workspace).compile(spec, snapshot)
    decision = HardPolicyService().evaluate(spec, snapshot, operation)
    assert decision.status == "ALLOWED"
    assert decision.reason_codes == ()


def test_hard_policy_denies_stale_truth_and_disabled_mutations(fake_runtime):
    workspace, provider, _ = fake_runtime
    ScopedRefreshService(provider, workspace).refresh(RefreshSpec("1234567890", ("101",), DateRange("2026-08-01", "2026-08-02")))
    snapshot = AccountSnapshotService(workspace).current("1234567890", campaign_ids=("101",))
    spec = ChangeSpec(
        "spec_policy_2", "1234567890", "1234567890", ChangeKind.UPDATE_BUDGET,
        {"campaign_id": "101"}, {"daily_budget": "13"},
        {"snapshot_id": snapshot.snapshot_id, "content_hash": snapshot.content_hash},
    )
    operation = BudgetCompiler(workspace).compile(spec, snapshot)
    stale = replace(
        snapshot,
        freshness={**snapshot.freshness, "status": "STALE"},
        content_hash="",
    )
    decision = HardPolicyService(mutations_enabled=False).evaluate(spec, stale, operation)
    assert decision.status == "DENIED"
    assert "MUTATIONS_DISABLED" in decision.reason_codes
    assert "REQUIRED_TRUTH_STALE" in decision.reason_codes
