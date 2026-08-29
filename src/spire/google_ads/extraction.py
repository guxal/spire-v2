"""Explicit scoped refresh and atomic publication of minimal truth."""

from __future__ import annotations

import json
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
from spire.truth import DatasetState, ExtractionManifest, SnapshotSource

from .discovery import normalize_campaign, query_rows
from .provider import GoogleAdsClientProvider


@dataclass(frozen=True, slots=True)
class RefreshSpec:
    customer_id: str
    campaign_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        normalized = tuple(
            sorted({validate_google_ads_id(value, field="campaign_id") for value in self.campaign_ids}, key=int)
        )
        if not normalized:
            raise ValueError("EXPLICIT_CAMPAIGN_SCOPE_REQUIRED")
        object.__setattr__(self, "campaign_ids", normalized)

    @property
    def scope(self) -> dict[str, Any]:
        return {
            "scope_type": "CAMPAIGNS",
            "requested_campaign_ids": list(self.campaign_ids),
            "resolved_campaign_ids": list(self.campaign_ids),
            "scope_fingerprint": canonical_hash({"campaign_ids": list(self.campaign_ids)}),
        }


@dataclass(frozen=True, slots=True)
class RefreshResult:
    customer_id: str
    extraction_id: str
    manifest: ExtractionManifest


class ScopedRefreshService:
    def __init__(self, provider: GoogleAdsClientProvider, workspace) -> None:
        self.provider = provider
        self.workspace = workspace

    def refresh(self, spec: RefreshSpec) -> RefreshResult:
        initialize_customer_workspace(self.workspace, spec.customer_id)
        extraction_id = _new_id("extract")
        campaign_query = scoped_campaign_query(spec.campaign_ids)
        account_query = account_query_text()
        client = self.provider.get_client()
        accounts = [normalize_account(row, spec.customer_id) for row in query_rows(client, spec.customer_id, account_query)]
        campaigns = [
            normalized
            for row in query_rows(client, spec.customer_id, campaign_query)
            if (normalized := normalize_campaign(row, spec.customer_id))["campaign_id"]
            in spec.campaign_ids
        ]
        manifest = self._publish(spec, extraction_id, accounts, campaigns, account_query, campaign_query)
        return RefreshResult(spec.customer_id, extraction_id, manifest)

    def _publish(
        self,
        spec: RefreshSpec,
        extraction_id: str,
        accounts: list[dict[str, Any]],
        campaigns: list[dict[str, Any]],
        account_query: str,
        campaign_query: str,
    ) -> ExtractionManifest:
        observed_at = _now()
        truth_root = self.workspace.truth(spec.customer_id)
        extractions_root = truth_root / "extractions"
        final_dir = safe_child(extractions_root, extraction_id, field="extraction_id")
        staging = extractions_root / f".{extraction_id}.tmp"
        staging.mkdir(parents=True, exist_ok=False)
        datasets = {
            "account": self._write_dataset(staging, "account", accounts),
            "campaigns": self._write_dataset(staging, "campaigns", campaigns),
        }
        manifest = ExtractionManifest(
            extraction_id=extraction_id,
            customer_id=spec.customer_id,
            source=SnapshotSource.LIVE,
            scope=spec.scope,
            observed_at=observed_at,
            status="FINALIZED",
            datasets=datasets,
            provenance={
                "account_query_hash": canonical_hash(account_query),
                "campaign_query_hash": canonical_hash(campaign_query),
                "provider_login_customer_id": self.provider.login_customer_id,
            },
        )
        (staging / "manifest.json").write_text(
            json.dumps(manifest.to_dict(), sort_keys=True), encoding="utf-8"
        )
        staging.replace(final_dir)
        _atomic_json_write(
            truth_root / "current.json",
            {"customer_id": spec.customer_id, "extraction_id": extraction_id, "content_hash": manifest.content_hash},
        )
        return manifest

    @staticmethod
    def _write_dataset(staging: Path, name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        path = staging / "datasets" / f"{name}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        content = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
        path.write_text(content, encoding="utf-8")
        state = DatasetState.PRESENT if rows else DatasetState.EMPTY
        return {
            "state": state.value,
            "row_count": len(rows),
            "content_hash": canonical_hash(content),
        }


def account_query_text() -> str:
    return "SELECT customer.id, customer.descriptive_name, customer.currency_code, customer.time_zone FROM customer LIMIT 1"


def scoped_campaign_query(campaign_ids: tuple[str, ...]) -> str:
    values = ", ".join(campaign_ids)
    return (
        "SELECT customer.id, customer.descriptive_name, customer.currency_code, customer.time_zone, "
        "campaign.id, campaign.name, campaign.status, campaign.serving_status, "
        "campaign.advertising_channel_type, campaign.campaign_budget, campaign_budget.amount_micros "
        f"FROM campaign WHERE campaign.id IN ({values}) ORDER BY campaign.id"
    )


def normalize_account(row: Any, customer_id: str) -> dict[str, Any]:
    return {
        "customer_id": customer_id,
        "account_id": str(_value(row, "customer.id", "id") or customer_id),
        "name": str(_value(row, "customer.descriptive_name", "descriptive_name") or ""),
        "currency": str(_value(row, "customer.currency_code", "currency_code") or ""),
        "time_zone": str(_value(row, "customer.time_zone", "time_zone") or ""),
    }


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


def _new_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:12]}"


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    temporary.replace(path)
