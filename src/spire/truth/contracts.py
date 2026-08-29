"""Immutable contracts for finalized Google Ads truth."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from spire.core import canonical_hash, validate_artifact_id, validate_customer_id


class DatasetState(StrEnum):
    PRESENT = "PRESENT"
    EMPTY = "EMPTY"
    FAILED = "FAILED"
    NOT_REQUESTED = "NOT_REQUESTED"


class SnapshotSource(StrEnum):
    LIVE = "LIVE"


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


@dataclass(frozen=True, slots=True)
class ExtractionManifest:
    extraction_id: str
    customer_id: str
    source: SnapshotSource
    scope: Mapping[str, Any]
    observed_at: str
    status: str
    datasets: Mapping[str, Mapping[str, Any]]
    provenance: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = "spire.extraction-manifest.v1"
    content_hash: str = ""

    def __post_init__(self) -> None:
        validate_artifact_id(self.extraction_id, field="extraction_id")
        validate_customer_id(self.customer_id)
        _parse_timestamp(self.observed_at)
        if self.status != "FINALIZED":
            raise ValueError("EXTRACTION_MANIFEST_NOT_FINALIZED")
        object.__setattr__(self, "source", SnapshotSource(self.source))
        object.__setattr__(self, "scope", _freeze_mapping(self.scope))
        object.__setattr__(self, "datasets", _freeze_mapping(self.datasets))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))
        expected = canonical_hash(self._hash_material())
        if self.content_hash and self.content_hash != expected:
            raise ValueError("EXTRACTION_MANIFEST_HASH_MISMATCH")
        object.__setattr__(self, "content_hash", expected)

    def _hash_material(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "extraction_id": self.extraction_id,
            "customer_id": self.customer_id,
            "source": self.source.value,
            "scope": dict(self.scope),
            "observed_at": self.observed_at,
            "status": self.status,
            "datasets": {key: dict(value) for key, value in self.datasets.items()},
            "provenance": dict(self.provenance),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._hash_material(), "content_hash": self.content_hash}


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    snapshot_id: str
    customer_id: str
    source: SnapshotSource
    scope: Mapping[str, Any]
    observed_at: str
    freshness: Mapping[str, Any]
    coverage: Mapping[str, DatasetState]
    dataset_hashes: Mapping[str, str]
    extraction_id: str
    provenance: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = "spire.account-snapshot.v1"
    content_hash: str = ""

    def __post_init__(self) -> None:
        validate_artifact_id(self.snapshot_id, field="snapshot_id")
        validate_customer_id(self.customer_id)
        validate_artifact_id(self.extraction_id, field="extraction_id")
        _parse_timestamp(self.observed_at)
        object.__setattr__(self, "source", SnapshotSource(self.source))
        object.__setattr__(self, "scope", _freeze_mapping(self.scope))
        object.__setattr__(self, "freshness", _freeze_mapping(self.freshness))
        object.__setattr__(
            self,
            "coverage",
            MappingProxyType({key: DatasetState(value) for key, value in self.coverage.items()}),
        )
        object.__setattr__(self, "dataset_hashes", _freeze_mapping(self.dataset_hashes))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))
        expected = canonical_hash(self._hash_material())
        if self.content_hash and self.content_hash != expected:
            raise ValueError("ACCOUNT_SNAPSHOT_HASH_MISMATCH")
        object.__setattr__(self, "content_hash", expected)

    def _hash_material(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id,
            "customer_id": self.customer_id,
            "source": self.source.value,
            "scope": dict(self.scope),
            "observed_at": self.observed_at,
            "freshness": dict(self.freshness),
            "coverage": {key: value.value for key, value in self.coverage.items()},
            "dataset_hashes": dict(self.dataset_hashes),
            "extraction_id": self.extraction_id,
            "provenance": dict(self.provenance),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._hash_material(), "content_hash": self.content_hash}


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("TRUTH_TIMESTAMP_INVALID")
    return parsed
