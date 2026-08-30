"""Deterministic compilation of business budget changes from frozen truth."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from spire.core import (
    ArtifactNotFoundError,
    ScopeMismatchError,
    validate_customer_id,
    validate_google_ads_id,
)
from spire.truth import AccountSnapshot, DatasetResolver, SnapshotSource

from .contracts import ChangeKind, ChangeSpec, CompiledOperation


class BudgetCompiler:
    def __init__(self, workspace, *, resolver_factory=DatasetResolver) -> None:
        self.workspace = workspace
        self._resolver_factory = resolver_factory

    def compile(self, spec: ChangeSpec, snapshot: AccountSnapshot) -> CompiledOperation:
        customer_id = validate_customer_id(spec.customer_id)
        if snapshot.customer_id != customer_id or spec.account_id != customer_id:
            raise ScopeMismatchError("EXECUTION_CUSTOMER_SCOPE_MISMATCH")
        if spec.kind is not ChangeKind.UPDATE_BUDGET:
            raise ValueError("UNSUPPORTED_CHANGE_KIND")
        if snapshot.source is not SnapshotSource.LIVE:
            raise ScopeMismatchError("EXECUTION_SOURCE_NOT_ALLOWED")
        if snapshot.freshness.get("status") != "FRESH":
            raise ScopeMismatchError("REQUIRED_TRUTH_STALE")
        if spec.snapshot_ref.get("content_hash") != snapshot.content_hash:
            raise ScopeMismatchError("SNAPSHOT_REFERENCE_MISMATCH")
        campaign_id = validate_google_ads_id(spec.target.get("campaign_id", ""), field="campaign_id")
        resolved_scope = {str(value) for value in snapshot.scope.get("resolved_campaign_ids", ())}
        if campaign_id not in resolved_scope:
            raise ScopeMismatchError("CAMPAIGN_SCOPE_NOT_CERTIFIED")
        resolver = self._resolver_factory(self.workspace, customer_id)
        dataset = resolver.resolve_dataset(snapshot.extraction_id, "campaigns", campaign_ids=(campaign_id,))
        row = next((row for row in dataset.rows if str(row.get("campaign_id")) == campaign_id), None)
        if row is None:
            raise ArtifactNotFoundError("CAMPAIGN_NOT_IN_FROZEN_TRUTH")
        resource_name = str(row.get("campaign_budget_resource_name", ""))
        expected_prefix = f"customers/{customer_id}/campaignBudgets/"
        if not resource_name.startswith(expected_prefix) or resource_name == expected_prefix:
            raise ScopeMismatchError("CAMPAIGN_BUDGET_IDENTITY_MISSING")
        micros = _to_micros(spec.requested_change.get("daily_budget"))
        operation_id = f"operation_{spec.content_hash.split(':', 1)[-1][:24]}"
        return CompiledOperation(
            operation_id=operation_id,
            customer_id=customer_id,
            campaign_id=campaign_id,
            kind=spec.kind,
            budget_resource_name=resource_name,
            daily_budget_micros=micros,
            snapshot_hash=snapshot.content_hash,
        )


def _to_micros(value: object) -> int:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("DAILY_BUDGET_INVALID") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError("DAILY_BUDGET_INVALID")
    return int(amount * Decimal(1_000_000))
