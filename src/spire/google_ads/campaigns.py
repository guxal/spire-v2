# @file Frozen campaign read service.
# @domain google-ads
# @status stable
# @adr [[0009-capability-projection]]
# @adr [[0016-public-currency-units-and-internal-micros]]
# @tested-by [[test_truth_pipeline.py]]
"""Canonical campaign read surface."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from spire.core import ArtifactNotFoundError, validate_customer_id, validate_google_ads_id
from spire.truth import AccountSnapshotService, DatasetResolver

from .discovery import AccountDiscoveryService, DiscoveryResult


class CampaignReadService:
    """Thin composition of live discovery and frozen local reads."""

    def __init__(
        self,
        discovery: AccountDiscoveryService,
        snapshots: AccountSnapshotService,
        resolver_factory=DatasetResolver,
    ) -> None:
        self.discovery = discovery
        self.snapshots = snapshots
        self._resolver_factory = resolver_factory

    def discover(self, customer_id: str) -> DiscoveryResult:
        return self.discovery.discover(validate_customer_id(customer_id))

    def list(
        self,
        customer_id: str,
        *,
        status: str | None = None,
        channel: str | None = None,
    ) -> tuple[dict[str, Any], ...]:
        campaigns = self.discovery.list_local(validate_customer_id(customer_id))
        selected = campaigns
        if status:
            wanted = status.upper()
            selected = tuple(row for row in selected if str(row.get("status", "")).upper() == wanted)
        if channel:
            wanted = channel.upper()
            selected = tuple(row for row in selected if str(row.get("channel", "")).upper() == wanted)
        return tuple(_public_campaign(row) for row in selected)

    def get(self, customer_id: str, campaign_id: str) -> dict[str, Any]:
        customer_id = validate_customer_id(customer_id)
        campaign_id = validate_google_ads_id(campaign_id, field="campaign_id")
        snapshot = self.snapshots.current(customer_id, campaign_ids=(campaign_id,))
        resolver = self._resolver_factory(self.snapshots.workspace, customer_id)
        resolved = resolver.resolve_dataset(
            snapshot.extraction_id,
            "campaigns",
            campaign_ids=(campaign_id,),
        )
        for row in resolved.rows:
            if str(row.get("campaign_id")) == campaign_id:
                return {
                    "campaign_id": campaign_id,
                    "name": row.get("name", ""),
                    "status": row.get("status"),
                    "serving_status": row.get("serving_status"),
                    "channel": row.get("channel"),
                    "daily_budget": _currency_units(row.get("daily_budget")),
                    "currency": row.get("currency"),
                    "observed_at": snapshot.observed_at,
                    "freshness": dict(snapshot.freshness),
                    "scope": dict(snapshot.scope),
                    "evidence_id": snapshot.extraction_id,
                }
        raise ArtifactNotFoundError("CAMPAIGN_NOT_IN_CURRENT_SNAPSHOT")


def _public_campaign(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "campaign_id": row.get("campaign_id"),
        "name": row.get("name", ""),
        "status": row.get("status"),
        "serving_status": row.get("serving_status"),
        "channel": row.get("channel"),
        "daily_budget": _currency_units(row.get("daily_budget")),
        "currency": row.get("currency"),
    }


def _currency_units(value: Any) -> int | float | None:
    if value in (None, ""):
        return None
    amount = Decimal(str(value)) / Decimal(1_000_000)
    if amount == amount.to_integral_value():
        return int(amount)
    return float(amount)
