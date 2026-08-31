# @file Immutable AccountSnapshot construction.
# @domain truth
# @status stable
# @adr [[0001-deterministic-frozen-truth]]
# @adr [[0004-typed-immutable-truth]]
# @tested-by [[test_truth_pipeline.py]]
"""Build current immutable snapshots from finalized local truth only."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from spire.core import ArtifactNotFoundError, validate_customer_id
from spire.interfaces import DateRange

from .contracts import AccountSnapshot, DatasetState
from .resolver import DatasetResolver


class AccountSnapshotService:
    def __init__(self, workspace, *, freshness_ttl: timedelta = timedelta(hours=24)) -> None:
        self.workspace = workspace
        self.freshness_ttl = freshness_ttl

    def current(
        self,
        customer_id: str,
        *,
        campaign_ids: tuple[str, ...] | list[str] | None = None,
        now: datetime | None = None,
    ) -> AccountSnapshot:
        customer_id = validate_customer_id(customer_id)
        resolver = DatasetResolver(self.workspace, customer_id)
        extraction_id = resolver.current_extraction_id()
        manifest = resolver.extraction_manifest(extraction_id)
        requested = tuple(str(value) for value in (campaign_ids or ()))
        resolved = tuple(str(value) for value in manifest.scope.get("resolved_campaign_ids", ()))
        if requested and not set(requested).issubset(set(resolved)):
            raise ArtifactNotFoundError("CURRENT_SNAPSHOT_SCOPE_MISMATCH")
        return self._build_snapshot(manifest, now=now)

    def latest_exact(
        self,
        customer_id: str,
        campaign_ids: tuple[str, ...] | list[str],
        *,
        now: datetime | None = None,
    ) -> AccountSnapshot:
        customer_id = validate_customer_id(customer_id)
        resolver = DatasetResolver(self.workspace, customer_id)
        extraction_id = resolver.latest_extraction_for_selection(campaign_ids)
        return self._build_snapshot(resolver.extraction_manifest(extraction_id), now=now)

    def latest_compatible(
        self,
        customer_id: str,
        *,
        campaign_ids: tuple[str, ...] | list[str],
        date_range: DateRange | None = None,
        now: datetime | None = None,
    ) -> AccountSnapshot:
        customer_id = validate_customer_id(customer_id)
        resolver = DatasetResolver(self.workspace, customer_id)
        extraction_id = resolver.latest_extraction_for_compatible_scope(
            campaign_ids,
            date_range=date_range,
        )
        return self._build_snapshot(resolver.extraction_manifest(extraction_id), now=now)

    def _build_snapshot(self, manifest, *, now: datetime | None) -> AccountSnapshot:
        observed = _parse_timestamp(manifest.observed_at)
        current_time = (now or datetime.now(UTC)).astimezone(UTC)
        age_seconds = max(0.0, (current_time - observed).total_seconds())
        freshness = {
            "status": "FRESH" if age_seconds <= self.freshness_ttl.total_seconds() else "STALE",
            "observed_at": manifest.observed_at,
            "age_seconds": age_seconds,
            "ttl_seconds": self.freshness_ttl.total_seconds(),
        }
        coverage = {
            name: DatasetState(entry.get("state")) for name, entry in manifest.datasets.items()
        }
        hashes = {name: str(entry.get("content_hash", "")) for name, entry in manifest.datasets.items()}
        return AccountSnapshot(
            snapshot_id=f"snapshot_{manifest.extraction_id}",
            customer_id=manifest.customer_id,
            source=manifest.source,
            scope=manifest.scope,
            observed_at=manifest.observed_at,
            freshness=freshness,
            coverage=coverage,
            dataset_hashes=hashes,
            extraction_id=manifest.extraction_id,
            provenance={
                "manifest_hash": manifest.content_hash,
                "source": manifest.source.value,
                **dict(manifest.provenance),
            },
        )


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("TRUTH_TIMESTAMP_INVALID")
    return parsed.astimezone(UTC)
