# @file Deterministic negative-keyword candidate projection.
# @domain evidence
# @status stable
# @adr [[0010-safe-evidence-query]]
# @adr [[0018-bounded-execution-operation-extension]]
# @tested-by [[test_negative_candidates.py]]
"""Derive read-only negative-keyword candidates from one frozen snapshot."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from spire.core import canonical_hash, validate_customer_id, validate_google_ads_id

from .resolver import DatasetResolver
from .snapshot import AccountSnapshotService


class NegativeKeywordCandidateService:
    def __init__(self, workspace, *, snapshots: AccountSnapshotService | None = None) -> None:
        self.workspace = workspace
        self.snapshots = snapshots or AccountSnapshotService(workspace)

    def candidates(self, customer_id: str, campaign_id: str) -> dict[str, Any]:
        customer_id = validate_customer_id(customer_id)
        campaign_id = validate_google_ads_id(campaign_id, field="campaign_id")
        snapshot = self.snapshots.current(customer_id, campaign_ids=(campaign_id,))
        resolver = DatasetResolver(self.workspace, customer_id)
        search_terms = resolver.resolve_dataset(snapshot.extraction_id, "search_terms", campaign_ids=(campaign_id,)).rows
        keywords = resolver.resolve_dataset(snapshot.extraction_id, "keyword_daily", campaign_ids=(campaign_id,)).rows
        negatives = resolver.resolve_dataset(snapshot.extraction_id, "negative_keywords", campaign_ids=(campaign_id,)).rows
        positive_terms = {_normalized(row.get("keyword_text")) for row in keywords if row.get("keyword_text")}
        existing = {_normalized(row.get("text")) for row in negatives if row.get("text")}
        grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"impressions": 0, "clicks": 0, "cost_micros": 0, "conversions": 0.0, "conversions_value": 0.0})
        for row in search_terms:
            term = _normalized(row.get("search_term"))
            if not term:
                continue
            totals = grouped[term]
            for metric in totals:
                value = row.get(metric)
                if value not in (None, ""):
                    totals[metric] += float(value) if metric.startswith("conversions") else int(value)
        result = []
        for term, metrics in sorted(grouped.items()):
            reasons = []
            if metrics["cost_micros"] > 0 and metrics["conversions"] <= 0:
                reasons.append("SPEND_WITHOUT_CONVERSIONS")
            if term in existing:
                reasons.append("ALREADY_COVERED_NEGATIVE")
            if term in positive_terms:
                reasons.append("POSITIVE_KEYWORD_CONFLICT")
            if not reasons:
                continue
            result.append(
                {
                    "candidate_id": f"negative_{canonical_hash({'campaign_id': campaign_id, 'term': term}).split(':', 1)[-1][:24]}",
                    "campaign_id": campaign_id,
                    "search_term": term,
                    "suggested_negative": term,
                    "suggested_match_type": "EXACT",
                    "reason_codes": reasons,
                    "eligible": reasons == ["SPEND_WITHOUT_CONVERSIONS"],
                    "observed_metrics": metrics,
                    "evidence_refs": [
                        f"snapshot:{snapshot.content_hash}",
                        f"evidence:{snapshot.extraction_id}:search_terms",
                        f"evidence:{snapshot.extraction_id}:keyword_daily",
                        f"evidence:{snapshot.extraction_id}:negative_keywords",
                    ],
                }
            )
        return {
            "customer_id": customer_id,
            "campaign_id": campaign_id,
            "snapshot_ref": f"snapshot:{snapshot.content_hash}",
            "candidates": result,
            "limitations": [
                "Candidates are deterministic evidence signals, not persisted workflow items.",
                "Irrelevance, out-of-area intent, and service mismatch require business context and are not inferred without it.",
                "Search-term reporting can omit low-volume or privacy-thresholded queries.",
            ],
        }


def _normalized(value: object) -> str:
    return " ".join(str(value or "").casefold().split())
