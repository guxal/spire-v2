# @file Deterministic budget-change compiler.
# @domain execution
# @status stable
# @adr [[0011-canonical-execution-lifecycle]]
# @adr [[0016-public-currency-units-and-internal-micros]]
# @adr [[0018-bounded-execution-operation-extension]]
# @tested-by [[test_budget_compiler.py]]
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
        if snapshot.source is not SnapshotSource.LIVE:
            raise ScopeMismatchError("EXECUTION_SOURCE_NOT_ALLOWED")
        if snapshot.freshness.get("status") != "FRESH":
            raise ScopeMismatchError("REQUIRED_TRUTH_STALE")
        if spec.snapshot_ref.get("content_hash") != snapshot.content_hash:
            raise ScopeMismatchError("SNAPSHOT_REFERENCE_MISMATCH")
        if spec.kind is ChangeKind.UPDATE_BUDGET:
            return self._compile_budget(spec, snapshot, customer_id)
        if spec.kind is ChangeKind.ADD_NEGATIVE_KEYWORD:
            return self._compile_negative_keyword(spec, snapshot, customer_id)
        if spec.kind is ChangeKind.CREATE_SEARCH_CAMPAIGN:
            return self._compile_search_campaign(spec, snapshot, customer_id)
        raise ValueError("UNSUPPORTED_CHANGE_KIND")

    def _campaign_row(self, spec: ChangeSpec, snapshot: AccountSnapshot, customer_id: str) -> tuple[str, dict]:
        campaign_id = validate_google_ads_id(spec.target.get("campaign_id", ""), field="campaign_id")
        resolved_scope = {str(value) for value in snapshot.scope.get("resolved_campaign_ids", ())}
        if campaign_id not in resolved_scope:
            raise ScopeMismatchError("CAMPAIGN_SCOPE_NOT_CERTIFIED")
        resolver = self._resolver_factory(self.workspace, customer_id)
        dataset = resolver.resolve_dataset(snapshot.extraction_id, "campaigns", campaign_ids=(campaign_id,))
        row = next((row for row in dataset.rows if str(row.get("campaign_id")) == campaign_id), None)
        if row is None:
            raise ArtifactNotFoundError("CAMPAIGN_NOT_IN_FROZEN_TRUTH")
        return campaign_id, row

    def _compile_budget(self, spec: ChangeSpec, snapshot: AccountSnapshot, customer_id: str) -> CompiledOperation:
        campaign_id, row = self._campaign_row(spec, snapshot, customer_id)
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

    def _compile_negative_keyword(
        self, spec: ChangeSpec, snapshot: AccountSnapshot, customer_id: str
    ) -> CompiledOperation:
        campaign_id, _ = self._campaign_row(spec, snapshot, customer_id)
        text = " ".join(str(spec.requested_change.get("text") or "").split())
        match_type = str(spec.requested_change.get("match_type") or "").upper()
        scope = str(spec.requested_change.get("scope") or "CAMPAIGN").upper()
        ad_group_id = str(spec.requested_change.get("ad_group_id") or "")
        if not text or match_type not in {"EXACT", "PHRASE", "BROAD"} or scope not in {"CAMPAIGN", "AD_GROUP"}:
            raise ValueError("NEGATIVE_KEYWORD_REQUEST_INVALID")
        if scope == "AD_GROUP":
            ad_group_id = validate_google_ads_id(ad_group_id, field="ad_group_id")
            groups = DatasetResolver(self.workspace, customer_id).resolve_dataset(
                snapshot.extraction_id, "campaign_ad_groups", campaign_ids=(campaign_id,)
            )
            if ad_group_id not in {str(row.get("ad_group_id")) for row in groups.rows}:
                raise ScopeMismatchError("AD_GROUP_NOT_IN_FROZEN_TRUTH")
        inventory = DatasetResolver(self.workspace, customer_id).resolve_dataset(
            snapshot.extraction_id, "negative_keywords", campaign_ids=(campaign_id,)
        )
        normalized_text = " ".join(text.casefold().split())
        if any(
            " ".join(str(row.get("text") or "").casefold().split()) == normalized_text
            and str(row.get("match_type") or "").upper() == match_type
            and str(row.get("scope") or "") in {scope, "ACCOUNT", "SHARED_LIST"}
            for row in inventory.rows
        ):
            raise ValueError("NEGATIVE_KEYWORD_ALREADY_EXISTS")
        return CompiledOperation(
            operation_id=f"operation_{spec.content_hash.split(':', 1)[-1][:24]}",
            customer_id=customer_id,
            campaign_id=campaign_id,
            kind=spec.kind,
            budget_resource_name="",
            daily_budget_micros=0,
            snapshot_hash=snapshot.content_hash,
            payload={"text": text, "match_type": match_type, "scope": scope, "ad_group_id": ad_group_id},
            compiler_version="spire-v2.negative-keyword.v1",
        )

    def _compile_search_campaign(
        self, spec: ChangeSpec, snapshot: AccountSnapshot, customer_id: str
    ) -> CompiledOperation:
        request = dict(spec.requested_change)
        micros = _to_micros(request.get("daily_budget"))
        ad_groups = list(request.get("ad_groups") or ())
        if not ad_groups:
            raise ValueError("SEARCH_CAMPAIGN_AD_GROUPS_REQUIRED")
        payload = {
            "campaign_name": str(request.get("campaign_name") or "").strip(),
            "bidding_strategy": str(request.get("bidding_strategy") or "").upper(),
            "geo_target_ids": list(request.get("geo_target_ids") or ()),
            "language_criterion_ids": list(request.get("language_criterion_ids") or ()),
            "ad_groups": ad_groups,
            "budget_resource_name": f"customers/{customer_id}/campaignBudgets/-1",
            "campaign_resource_name": f"customers/{customer_id}/campaigns/-2",
        }
        if not payload["campaign_name"] or payload["bidding_strategy"] not in {"MAXIMIZE_CONVERSIONS", "MAXIMIZE_CLICKS"}:
            raise ValueError("SEARCH_CAMPAIGN_REQUEST_INVALID")
        return CompiledOperation(
            operation_id=f"operation_{spec.content_hash.split(':', 1)[-1][:24]}",
            customer_id=customer_id,
            campaign_id="",
            kind=spec.kind,
            budget_resource_name="",
            snapshot_hash=snapshot.content_hash,
            daily_budget_micros=micros,
            payload=payload,
            compiler_version="spire-v2.create-search-campaign.v1",
        )


def _to_micros(value: object) -> int:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("DAILY_BUDGET_INVALID") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError("DAILY_BUDGET_INVALID")
    return int(amount * Decimal(1_000_000))
