# @file Hard production execution policy.
# @domain execution
# @status stable
# @adr [[0011-canonical-execution-lifecycle]]
# @adr [[0018-bounded-execution-operation-extension]]
# @tested-by [[test_execution_policy.py]]
"""Pure hard safety policy for production execution."""

from __future__ import annotations

from datetime import UTC, datetime

from spire.truth import AccountSnapshot, SnapshotSource

from .contracts import ChangeKind, ChangeSpec, CompiledOperation, ExecutionMode, HardPolicyDecision


class HardPolicyService:
    def __init__(self, *, mutations_enabled: bool = True) -> None:
        self.mutations_enabled = mutations_enabled

    def evaluate(
        self,
        spec: ChangeSpec,
        snapshot: AccountSnapshot,
        operation: CompiledOperation,
        *,
        mode: ExecutionMode = ExecutionMode.PRODUCTION,
        now: datetime | None = None,
    ) -> HardPolicyDecision:
        reasons: list[str] = []
        if not self.mutations_enabled:
            reasons.append("MUTATIONS_DISABLED")
        if spec.customer_id != snapshot.customer_id or spec.account_id != snapshot.customer_id:
            reasons.append("CUSTOMER_ACCOUNT_MISMATCH")
        if operation.customer_id != spec.customer_id:
            reasons.append("OPERATION_CUSTOMER_MISMATCH")
        if spec.snapshot_ref.get("content_hash") != snapshot.content_hash:
            reasons.append("SNAPSHOT_REFERENCE_MISMATCH")
        if operation.snapshot_hash != snapshot.content_hash:
            reasons.append("OPERATION_SNAPSHOT_MISMATCH")
        if mode is not ExecutionMode.PRODUCTION or snapshot.source is not SnapshotSource.LIVE:
            reasons.append("SOURCE_MODE_NOT_COMPATIBLE")
        if snapshot.freshness.get("status") != "FRESH":
            reasons.append("REQUIRED_TRUTH_STALE")
        if spec.kind is not operation.kind or spec.kind not in set(ChangeKind):
            reasons.append("UNSUPPORTED_CHANGE_KIND")
        if spec.kind in {ChangeKind.UPDATE_BUDGET, ChangeKind.CREATE_SEARCH_CAMPAIGN} and operation.daily_budget_micros <= 0:
            reasons.append("INVALID_BUDGET_PRECONDITION")
        if spec.kind is ChangeKind.ADD_NEGATIVE_KEYWORD and not str(operation.payload.get("text", "")):
            reasons.append("INVALID_NEGATIVE_KEYWORD_PRECONDITION")
        if spec.kind is ChangeKind.CREATE_SEARCH_CAMPAIGN and operation.payload.get("campaign_name") != spec.target.get("campaign_name"):
            reasons.append("CAMPAIGN_NAME_PRECONDITION")
        return HardPolicyDecision(
            status="ALLOWED" if not reasons else "DENIED",
            reason_codes=tuple(reasons),
            evaluated_at=(now or datetime.now(UTC)).isoformat().replace("+00:00", "Z"),
        )
