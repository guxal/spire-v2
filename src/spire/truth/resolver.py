# @file Logical resolver for finalized truth datasets.
# @domain truth
# @status stable
# @adr [[0005-dataset-resolver-boundary]]
# @tested-by [[test_truth_pipeline.py]]
"""Logical access to finalized truth datasets; physical layout stays private."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spire.core import (
    ArtifactNotFoundError,
    ScopeMismatchError,
    assert_loaded_scope,
    canonical_hash,
    safe_child,
    validate_customer_id,
    validate_google_ads_id,
)
from spire.interfaces import DATASET_SCHEMAS, DateRange

from .contracts import DatasetState, ExtractionManifest


@dataclass(frozen=True, slots=True)
class ResolvedDataset:
    dataset: str
    rows: tuple[dict[str, Any], ...]
    state: DatasetState
    content_hash: str
    extraction_id: str


class DatasetResolver:
    """Resolve only logical finalized datasets for one customer."""

    _known_datasets = frozenset({"account", *DATASET_SCHEMAS})

    def __init__(self, workspace, customer_id: str) -> None:
        self.workspace = workspace
        self.customer_id = validate_customer_id(customer_id)

    def extraction_manifest(self, extraction_id: str) -> ExtractionManifest:
        manifest_payload = self._load_manifest(extraction_id)
        return ExtractionManifest(**manifest_payload)

    def resolve_dataset(
        self,
        extraction_id: str,
        dataset_name: str,
        *,
        campaign_ids: tuple[str, ...] | list[str] | None = None,
    ) -> ResolvedDataset:
        if dataset_name not in self._known_datasets:
            raise ScopeMismatchError(f"UNKNOWN_DATASET:{dataset_name}")
        manifest = self.extraction_manifest(extraction_id)
        entry = manifest.datasets.get(dataset_name)
        if entry is None:
            raise ScopeMismatchError(f"DATASET_NOT_REQUESTED:{dataset_name}")
        state = DatasetState(entry.get("state"))
        if state in {DatasetState.FAILED, DatasetState.NOT_REQUESTED}:
            raise ScopeMismatchError(f"DATASET_UNAVAILABLE:{dataset_name}:{state.value}")
        requested = _normalize_campaign_ids(campaign_ids)
        resolved_scope = tuple(str(value) for value in manifest.scope.get("resolved_campaign_ids", ()))
        if requested and not set(requested).issubset(set(resolved_scope)):
            raise ScopeMismatchError("CAMPAIGN_SCOPE_NOT_CERTIFIED")
        path = self._dataset_file(extraction_id, dataset_name)
        if not path.exists():
            raise ArtifactNotFoundError(f"DATASET_FILE_MISSING:{dataset_name}")
        content = path.read_text(encoding="utf-8")
        if canonical_hash(content) != entry.get("content_hash"):
            raise ScopeMismatchError(f"DATASET_HASH_MISMATCH:{dataset_name}")
        rows = tuple(json.loads(line) for line in content.splitlines() if line.strip())
        if state is DatasetState.EMPTY:
            if rows:
                raise ScopeMismatchError(f"DATASET_STATE_MISMATCH:{dataset_name}")
            return ResolvedDataset(dataset_name, (), state, str(entry["content_hash"]), extraction_id)
        if len(rows) != int(entry.get("row_count", -1)):
            raise ScopeMismatchError(f"DATASET_ROW_COUNT_MISMATCH:{dataset_name}")
        if requested and dataset_name == "campaigns":
            rows = tuple(row for row in rows if str(row.get("campaign_id")) in requested)
        return ResolvedDataset(dataset_name, rows, state, str(entry["content_hash"]), extraction_id)

    def current_extraction_id(self) -> str:
        path = self.workspace.truth(self.customer_id) / "current.json"
        if not path.exists():
            raise ArtifactNotFoundError("CURRENT_EXTRACTION_NOT_FOUND")
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert_loaded_scope(payload, {"customer_id": self.customer_id}, artifact_name="current")
        extraction_id = str(payload.get("extraction_id", ""))
        manifest = self.extraction_manifest(extraction_id)
        if payload.get("content_hash") != manifest.content_hash:
            raise ScopeMismatchError("CURRENT_EXTRACTION_HASH_MISMATCH")
        return extraction_id

    def latest_extraction_for_selection(self, campaign_ids: tuple[str, ...] | list[str]) -> str:
        wanted = _normalize_campaign_ids(campaign_ids)
        candidates: list[tuple[str, str]] = []
        root = self.workspace.truth(self.customer_id) / "extractions"
        if root.is_dir():
            for directory in root.iterdir():
                if not directory.is_dir() or directory.name.startswith("."):
                    continue
                try:
                    manifest = self.extraction_manifest(directory.name)
                except (ArtifactNotFoundError, ValueError, ScopeMismatchError):
                    continue
                scope = tuple(str(value) for value in manifest.scope.get("resolved_campaign_ids", ()))
                if manifest.scope.get("scope_type") == "CAMPAIGNS" and scope == wanted:
                    candidates.append((manifest.observed_at, manifest.extraction_id))
        if not candidates:
            raise ArtifactNotFoundError("EXACT_SCOPED_EXTRACTION_NOT_FOUND")
        return max(candidates)[1]

    def latest_extraction_for_compatible_scope(
        self,
        campaign_ids: tuple[str, ...] | list[str],
        *,
        date_range: DateRange | None = None,
    ) -> str:
        """Select the latest finalized extraction that certifies a read request."""

        wanted = _normalize_campaign_ids(campaign_ids)
        scope_candidates: list[tuple[str, str]] = []
        compatible_candidates: list[tuple[str, str]] = []
        root = self.workspace.truth(self.customer_id) / "extractions"
        if root.is_dir():
            for directory in root.iterdir():
                if not directory.is_dir() or directory.name.startswith("."):
                    continue
                try:
                    manifest = self.extraction_manifest(directory.name)
                except (ArtifactNotFoundError, ValueError, ScopeMismatchError):
                    continue
                scope = tuple(str(value) for value in manifest.scope.get("resolved_campaign_ids", ()))
                if (
                    manifest.scope.get("scope_type") != "CAMPAIGNS"
                    or not set(wanted).issubset(set(scope))
                ):
                    continue
                candidate = (manifest.observed_at, manifest.extraction_id)
                scope_candidates.append(candidate)
                if _certifies_date_range(manifest.scope, date_range):
                    compatible_candidates.append(candidate)
        if compatible_candidates:
            return max(compatible_candidates)[1]
        if date_range is not None and scope_candidates:
            raise ScopeMismatchError("EVIDENCE_DATE_RANGE_NOT_CERTIFIED")
        raise ArtifactNotFoundError("COMPATIBLE_SCOPED_EXTRACTION_NOT_FOUND")

    def _load_manifest(self, extraction_id: str) -> dict[str, Any]:
        validated = safe_child(
            self.workspace.truth(self.customer_id) / "extractions",
            extraction_id,
            field="extraction_id",
        )
        path = validated / "manifest.json"
        if not path.exists():
            raise ArtifactNotFoundError("FINALIZED_EXTRACTION_NOT_FOUND")
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert_loaded_scope(
            payload,
            {"customer_id": self.customer_id, "extraction_id": extraction_id},
            artifact_name="extraction_manifest",
        )
        if payload.get("status") != "FINALIZED":
            raise ArtifactNotFoundError("EXTRACTION_NOT_FINALIZED")
        return payload

    def _dataset_file(self, extraction_id: str, dataset_name: str) -> Path:
        extraction = safe_child(
            self.workspace.truth(self.customer_id) / "extractions",
            extraction_id,
            field="extraction_id",
        )
        return safe_child(extraction / "datasets", dataset_name, field="dataset_name").with_suffix(
            ".jsonl"
        )


def _normalize_campaign_ids(values: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    return tuple(sorted({validate_google_ads_id(value, field="campaign_id") for value in values}, key=int))


def _certifies_date_range(scope: dict[str, Any], requested: DateRange | None) -> bool:
    if requested is None:
        return True
    declared = scope.get("date_range")
    if not isinstance(declared, dict):
        return False
    start = declared.get("start")
    end = declared.get("end")
    return isinstance(start, str) and isinstance(end, str) and start <= requested.start and end >= requested.end
