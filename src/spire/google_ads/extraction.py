# @file Scoped refresh and atomic frozen-truth publication.
# @domain google-ads
# @status stable
# @adr [[0001-deterministic-frozen-truth]]
# @adr [[0017-finite-resolved-refresh-scope]]
# @adr [[0018-bounded-execution-operation-extension]]
# @tested-by [[test_truth_pipeline.py]]
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
from spire.interfaces import DateRange
from spire.truth import DatasetState, ExtractionManifest, SnapshotSource

from .discovery import normalize_campaign, query_rows
from .evidence_datasets import (
    EVIDENCE_DATASETS,
    auction_participant_availability_rows,
    auction_summary_query,
    enrich_geo_rows,
    evidence_query,
    geo_target_query,
    negative_keyword_queries,
    normalize_auction_summary_row,
    normalize_evidence_row,
    normalize_geo_target_row,
    normalize_negative_keyword_row,
)
from .provider import GoogleAdsClientProvider


@dataclass(frozen=True, slots=True)
class RefreshSpec:
    customer_id: str
    campaign_ids: tuple[str, ...]
    date_range: DateRange | None = None

    def __post_init__(self) -> None:
        normalized = tuple(
            sorted({validate_google_ads_id(value, field="campaign_id") for value in self.campaign_ids}, key=int)
        )
        if not normalized:
            raise ValueError("EXPLICIT_CAMPAIGN_SCOPE_REQUIRED")
        object.__setattr__(self, "campaign_ids", normalized)

    @property
    def scope(self) -> dict[str, Any]:
        scope = {
            "scope_type": "CAMPAIGNS",
            "requested_campaign_ids": list(self.campaign_ids),
            "resolved_campaign_ids": list(self.campaign_ids),
            "scope_fingerprint": canonical_hash(
                {
                    "campaign_ids": list(self.campaign_ids),
                    "date_range": (
                        {"start": self.date_range.start, "end": self.date_range.end}
                        if self.date_range
                        else None
                    ),
                }
            ),
        }
        if self.date_range is not None:
            scope["date_range"] = {
                "start": self.date_range.start,
                "end": self.date_range.end,
            }
        return scope


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
        for dataset in EVIDENCE_DATASETS:
            try:
                if dataset == "negative_keywords":
                    rows = self._negative_keyword_rows(spec, observed_at)
                elif dataset == "auction_insights":
                    query = evidence_query(dataset, spec.campaign_ids, spec.date_range)
                    try:
                        rows = [
                            normalize_evidence_row(dataset, row, spec.customer_id)
                            for row in query_rows(
                                self.provider.get_client(),
                                spec.customer_id,
                                query,
                            )
                        ]
                    except Exception:  # noqa: BLE001 - restricted report stays explicit
                        rows = auction_participant_availability_rows(
                            spec.customer_id,
                            spec.campaign_ids,
                            status="QUERY_UNAVAILABLE",
                        )
                    if not rows:
                        rows = auction_participant_availability_rows(
                            spec.customer_id,
                            spec.campaign_ids,
                            status="NO_PARTICIPANT_ROWS",
                        )
                else:
                    query = evidence_query(dataset, spec.campaign_ids, spec.date_range)
                    rows = [
                        normalize_evidence_row(dataset, row, spec.customer_id)
                        for row in query_rows(
                            self.provider.get_client(),
                            spec.customer_id,
                            query,
                        )
                    ]
                if dataset == "geo_daily" and (metadata_query := geo_target_query(rows)):
                    geo_targets = [
                        normalize_geo_target_row(row)
                        for row in query_rows(
                            self.provider.get_client(),
                            spec.customer_id,
                            metadata_query,
                        )
                    ]
                    rows = enrich_geo_rows(rows, geo_targets)
                if dataset == "auction_insights":
                    summary_query = auction_summary_query(
                        spec.campaign_ids,
                        spec.date_range,
                    )
                    rows.extend(
                        normalize_auction_summary_row(row, spec.customer_id)
                        for row in query_rows(
                            self.provider.get_client(),
                            spec.customer_id,
                            summary_query,
                        )
                    )
            except Exception as exc:  # noqa: BLE001 - failed optional datasets stay explicit
                datasets[dataset] = {
                    "state": DatasetState.FAILED.value,
                    "row_count": 0,
                    "content_hash": canonical_hash(""),
                    "error": str(exc),
                }
            else:
                datasets[dataset] = self._write_dataset(staging, dataset, rows)
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

    def _negative_keyword_rows(self, spec: RefreshSpec, observed_at: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        failures = 0
        queries = negative_keyword_queries(spec.campaign_ids)
        fetched: dict[str, list[Any]] = {}
        for source, query in queries.items():
            try:
                fetched[source] = query_rows(self.provider.get_client(), spec.customer_id, query)
            except Exception:  # noqa: BLE001 - each optional provider view is independently explicit
                failures += 1
        if failures == len(queries):
            raise RuntimeError("NEGATIVE_KEYWORD_INVENTORY_UNAVAILABLE")
        for source, scope in (("campaign", "CAMPAIGN"), ("ad_group", "AD_GROUP")):
            rows.extend(
                normalize_negative_keyword_row(scope, row, spec.customer_id, observed_at=observed_at)
                for row in fetched.get(source, ())
            )
        shared_criteria: dict[str, list[Any]] = {}
        for row in fetched.get("shared_criteria", ()):
            shared_criteria.setdefault(
                str(_field(row, "shared_criterion.shared_set", "shared_set", "shared_set.resource_name")), []
            ).append(row)
        for association in fetched.get("shared_associations", ()):
            shared_set = str(_field(association, "campaign_shared_set.shared_set", "shared_set"))
            for criterion in _matching_shared_criteria(shared_criteria, shared_set):
                merged = {**_row_mapping(association), **_row_mapping(criterion)}
                rows.append(normalize_negative_keyword_row("SHARED_LIST", merged, spec.customer_id, observed_at=observed_at))
        account_sets = {
            str(_field(row, "customer_negative_criterion.negative_keyword_list.shared_set", "shared_set"))
            for row in fetched.get("account_lists", ())
        }
        for shared_set in account_sets:
            for criterion in _matching_shared_criteria(shared_criteria, shared_set):
                for campaign_id in spec.campaign_ids:
                    rows.append(
                        normalize_negative_keyword_row(
                            "ACCOUNT", criterion, spec.customer_id, campaign_id=campaign_id, observed_at=observed_at
                        )
                    )
        return [row for row in rows if row["text"] and row["match_type"]]

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


def _field(row: Any, *names: str) -> Any:
    return _value(row, *names)


def _row_mapping(row: Any) -> dict[str, Any]:
    return dict(row) if isinstance(row, dict) else {}


def _matching_shared_criteria(rows: dict[str, list[Any]], shared_set: str) -> list[Any]:
    if shared_set in rows:
        return rows[shared_set]
    return [
        row
        for resource_name, values in rows.items()
        if resource_name.rstrip("/").split("/")[-1] == shared_set.rstrip("/").split("/")[-1]
        for row in values
    ]


def _new_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:12]}"


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    temporary.replace(path)
