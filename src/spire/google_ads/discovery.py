"""Small live account/campaign discovery service and local catalog writer."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from spire.core import (
    canonical_hash,
    initialize_customer_workspace,
    safe_child,
    validate_google_ads_id,
)

from .provider import GoogleAdsClientProvider


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    customer_id: str
    catalog_id: str
    campaigns: tuple[dict[str, Any], ...]


class AccountDiscoveryService:
    def __init__(self, provider: GoogleAdsClientProvider, workspace) -> None:
        self.provider = provider
        self.workspace = workspace

    def discover(self, customer_id: str) -> DiscoveryResult:
        initialize_customer_workspace(self.workspace, customer_id)
        rows = query_rows(self.provider.get_client(), customer_id, campaign_discovery_query())
        campaigns = tuple(normalize_campaign(row, customer_id) for row in rows)
        catalog_id = _new_id("catalog")
        _publish_catalog(self.workspace.truth(customer_id), customer_id, catalog_id, campaigns)
        return DiscoveryResult(customer_id, catalog_id, campaigns)

    def list_local(self, customer_id: str) -> tuple[dict[str, Any], ...]:
        """Read the newest finalized catalog without contacting Google Ads."""
        root = self.workspace.truth(customer_id) / "catalogs"
        if not root.is_dir():
            return ()
        candidates = []
        for directory in root.iterdir():
            if not directory.is_dir() or directory.name.startswith("."):
                continue
            manifest = directory / "manifest.json"
            catalog = directory / "catalog.json"
            if manifest.exists() and catalog.exists():
                candidates.append(directory)
        if not candidates:
            return ()
        selected = max(candidates, key=lambda path: path.name)
        manifest_payload = json.loads((selected / "manifest.json").read_text(encoding="utf-8"))
        if manifest_payload.get("status") != "FINALIZED":
            raise ValueError("CATALOG_NOT_FINALIZED")
        payload = json.loads((selected / "catalog.json").read_text(encoding="utf-8"))
        if payload.get("customer_id") != customer_id:
            raise ValueError("CATALOG_CUSTOMER_MISMATCH")
        content_hash = payload.pop("content_hash", None)
        if content_hash != canonical_hash(payload):
            raise ValueError("CATALOG_HASH_MISMATCH")
        return tuple(payload.get("campaigns", ()))


def campaign_discovery_query() -> str:
    return (
        "SELECT customer.id, customer.descriptive_name, customer.currency_code, "
        "customer.time_zone, campaign.id, campaign.name, campaign.status, "
        "campaign.serving_status, campaign.advertising_channel_type, "
        "campaign.campaign_budget, campaign_budget.amount_micros "
        "FROM campaign WHERE campaign.status != 'REMOVED' ORDER BY campaign.id"
    )


def normalize_campaign(row: Any, customer_id: str) -> dict[str, Any]:
    campaign_id = validate_google_ads_id(_value(row, "campaign.id", "id"), field="campaign_id")
    return {
        "customer_id": customer_id,
        "campaign_id": campaign_id,
        "name": str(_value(row, "campaign.name", "name") or ""),
        "status": _enum_value(_value(row, "campaign.status", "status")),
        "serving_status": _enum_value(
            _value(row, "campaign.serving_status", "serving_status")
        ),
        "channel": _enum_value(
            _value(row, "campaign.advertising_channel_type", "advertising_channel_type")
        ),
        "budget_id": _resource_id(_value(row, "campaign.campaign_budget", "budget_id")),
        "daily_budget": _int_value(
            _value(row, "campaign_budget.amount_micros", "daily_budget", "amount_micros")
        ),
        "currency": str(_value(row, "customer.currency_code", "currency_code") or ""),
        "time_zone": str(_value(row, "customer.time_zone", "time_zone") or ""),
    }


def query_rows(client: Any, customer_id: str, query: str) -> list[Any]:
    service = client.get_service("GoogleAdsService")
    rows: list[Any] = []
    for batch in service.search_stream(customer_id=customer_id, query=query):
        rows.extend(batch.results)
    return rows


def _publish_catalog(truth_root: Path, customer_id: str, catalog_id: str, campaigns: Iterable[dict]) -> None:
    catalogs_root = truth_root / "catalogs"
    final_dir = safe_child(catalogs_root, catalog_id, field="catalog_id")
    staging = catalogs_root / f".{catalog_id}.tmp"
    staging.mkdir(parents=True, exist_ok=False)
    payload = {
        "schema_version": "spire.campaign-catalog.v1",
        "catalog_id": catalog_id,
        "customer_id": customer_id,
        "observed_at": _now(),
        "campaigns": list(campaigns),
    }
    payload["content_hash"] = canonical_hash({key: value for key, value in payload.items()})
    (staging / "catalog.json").write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    (staging / "manifest.json").write_text(
        json.dumps({"catalog_id": catalog_id, "customer_id": customer_id, "status": "FINALIZED"}),
        encoding="utf-8",
    )
    staging.replace(final_dir)


def _value(row: Any, *names: str) -> Any:
    for name in names:
        if isinstance(row, dict) and name in row:
            return row[name]
        current = row
        try:
            for part in name.split("."):
                current = current[part] if isinstance(current, dict) else getattr(current, part)
            return current
        except (AttributeError, KeyError, TypeError):
            continue
    return None


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "name", value)).split(".")[-1]


def _int_value(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _resource_id(value: Any) -> str | None:
    if not value:
        return None
    text = str(value)
    return text.rsplit("/", 1)[-1]


def _new_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:12]}"


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
