from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from spire.core import ArtifactNotFoundError, ScopeMismatchError
from spire.google_ads import (
    AccountDiscoveryService,
    CampaignReadService,
    RefreshSpec,
    ScopedRefreshService,
)
from spire.google_ads.evidence_datasets import (
    EVIDENCE_DATASETS,
    HISTORICAL_EVIDENCE_DATASETS,
    auction_summary_query,
    evidence_query,
)
from spire.google_ads.extraction import REFRESH_EVIDENCE_DATASETS
from spire.interfaces import DateRange
from spire.truth import AccountSnapshotService, DatasetResolver, DatasetState

REFRESH_RANGE = DateRange("2026-08-01", "2026-08-02")


def test_refresh_snapshot_resolver_and_campaign_reads(fake_runtime):
    workspace, provider, calls = fake_runtime
    discovery = AccountDiscoveryService(provider, workspace)
    reads = CampaignReadService(discovery, AccountSnapshotService(workspace))

    discovered = reads.discover("1234567890")
    assert discovered.campaigns[0]["daily_budget"] == 12500000
    assert len(calls) == 1
    assert reads.list("1234567890")[0]["campaign_id"] == "101"
    assert len(calls) == 1

    refreshed = ScopedRefreshService(provider, workspace).refresh(
        RefreshSpec("1234567890", ("101",), REFRESH_RANGE)
    )
    assert refreshed.manifest.status == "FINALIZED"
    assert refreshed.manifest.datasets["campaigns"]["state"] == DatasetState.PRESENT
    assert "auction_insights" not in refreshed.manifest.datasets
    assert "auction_insights" in EVIDENCE_DATASETS
    assert "auction_insights" not in REFRESH_EVIDENCE_DATASETS
    assert not any("auction_insight" in query for query in calls)
    assert len(calls) == 20

    snapshot = AccountSnapshotService(workspace).current("1234567890", campaign_ids=("101",))
    assert snapshot.source.value == "LIVE"
    assert snapshot.scope["date_range"] == {"start": "2026-08-01", "end": "2026-08-02"}
    assert snapshot.coverage["campaigns"] is DatasetState.PRESENT
    resolved = DatasetResolver(workspace, "1234567890").resolve_dataset(
        snapshot.extraction_id, "campaigns", campaign_ids=("101",)
    )
    assert resolved.rows[0]["campaign_id"] == "101"

    before_read = len(calls)
    campaign = reads.get("1234567890", "101")
    assert len(calls) == before_read
    assert campaign["campaign_id"] == "101"
    assert campaign["daily_budget"] == 12.5
    assert campaign["observed_at"] == snapshot.observed_at
    assert campaign["scope"] == dict(snapshot.scope)
    assert campaign["evidence_id"] == snapshot.extraction_id
    assert campaign["freshness"]["status"] == "FRESH"
    assert "resource_name" not in campaign
    assert not list((workspace.truth("1234567890") / "extractions").glob("*.tmp"))


def test_refresh_requires_explicit_nonempty_scope():
    with pytest.raises(ValueError, match="EXPLICIT_CAMPAIGN_SCOPE_REQUIRED"):
        RefreshSpec("1234567890", (), REFRESH_RANGE)


def test_refresh_requires_a_finite_evidence_date_range_before_provider_reads(fake_runtime):
    workspace, provider, calls = fake_runtime

    with pytest.raises(ValueError, match="FINITE_EVIDENCE_DATE_RANGE_REQUIRED"):
        ScopedRefreshService(provider, workspace).refresh(RefreshSpec("1234567890", ("101",)))

    assert calls == []
    assert not workspace.truth("1234567890").exists()


def test_historical_evidence_queries_are_bounded_and_configuration_queries_are_not_rewritten():
    for dataset in HISTORICAL_EVIDENCE_DATASETS:
        query = evidence_query(dataset, ("101",), REFRESH_RANGE)
        assert "segments.date BETWEEN '2026-08-01' AND '2026-08-02'" in query

    assert "segments.date BETWEEN '2026-08-01' AND '2026-08-02'" in auction_summary_query(
        ("101",), REFRESH_RANGE
    )

    for dataset in ("campaign_ad_groups", "campaign_ads", "campaign_assets"):
        query = evidence_query(dataset, ("101",), REFRESH_RANGE)
        assert "segments.date" not in query

    with pytest.raises(ValueError, match="FINITE_EVIDENCE_DATE_RANGE_REQUIRED"):
        evidence_query("campaign_daily", ("101",), None)


def test_snapshot_is_immutable(fake_runtime):
    workspace, provider, _ = fake_runtime
    ScopedRefreshService(provider, workspace).refresh(RefreshSpec("1234567890", ("101",), REFRESH_RANGE))
    snapshot = AccountSnapshotService(workspace).current("1234567890")
    with pytest.raises(FrozenInstanceError):
        snapshot.extraction_id = "other"
    with pytest.raises(TypeError):
        snapshot.coverage["new"] = DatasetState.EMPTY


def test_resolver_has_no_v1_or_archive_fallback(fake_runtime):
    workspace, _, _ = fake_runtime
    legacy = workspace.customer_root("1234567890") / "101" / "_extract"
    legacy.mkdir(parents=True)
    (legacy / "manifest.json").write_text("{}", encoding="utf-8")
    resolver = DatasetResolver(workspace, "1234567890")
    with pytest.raises(ArtifactNotFoundError):
        resolver.extraction_manifest("101")


def test_missing_dataset_is_not_empty(fake_runtime):
    workspace, provider, _ = fake_runtime
    result = ScopedRefreshService(provider, workspace).refresh(
        RefreshSpec("1234567890", ("101",), REFRESH_RANGE)
    )
    dataset = workspace.truth("1234567890") / "extractions" / result.extraction_id / "datasets/campaigns.jsonl"
    dataset.unlink()
    with pytest.raises(ArtifactNotFoundError):
        DatasetResolver(workspace, "1234567890").resolve_dataset(result.extraction_id, "campaigns")


def test_current_does_not_fallback_to_another_scope(fake_runtime):
    workspace, provider, _ = fake_runtime
    service = ScopedRefreshService(provider, workspace)
    service.refresh(RefreshSpec("1234567890", ("101",), REFRESH_RANGE))
    service.refresh(RefreshSpec("1234567890", ("202",), REFRESH_RANGE))
    snapshots = AccountSnapshotService(workspace)
    with pytest.raises(ArtifactNotFoundError):
        snapshots.current("1234567890", campaign_ids=("101",))
    assert snapshots.latest_exact("1234567890", ("101",)).scope["resolved_campaign_ids"] == ["101"]


def test_unknown_dataset_is_rejected(fake_runtime):
    workspace, provider, _ = fake_runtime
    ScopedRefreshService(provider, workspace).refresh(RefreshSpec("1234567890", ("101",), REFRESH_RANGE))
    with pytest.raises(ScopeMismatchError):
        DatasetResolver(workspace, "1234567890").resolve_dataset(
            "extract_missing", "not-a-dataset"
        )
