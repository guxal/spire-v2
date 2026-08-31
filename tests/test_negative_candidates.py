from __future__ import annotations

from dataclasses import dataclass

from spire.core import WorkspacePaths
from spire.google_ads import GoogleAdsClientProvider, RefreshSpec, ScopedRefreshService
from spire.interfaces import DateRange
from spire.truth import NegativeKeywordCandidateService


@dataclass
class _Batch:
    results: list[dict]


class _Service:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def search_stream(self, *, customer_id: str, query: str):
        self.calls.append(query)
        if "FROM customer LIMIT" in query:
            yield _Batch([{"customer.id": customer_id, "customer.descriptive_name": "Example", "customer.currency_code": "USD", "customer.time_zone": "UTC"}])
        elif "FROM search_term_view" in query:
            yield _Batch(
                [
                    {"campaign.id": "101", "search_term_view.search_term": "wasted query", "metrics.impressions": 20, "metrics.clicks": 2, "metrics.cost_micros": 1_000_000, "metrics.conversions": 0},
                    {"campaign.id": "101", "search_term_view.search_term": "protected query", "metrics.impressions": 10, "metrics.clicks": 1, "metrics.cost_micros": 500_000, "metrics.conversions": 0},
                ]
            )
        elif "FROM keyword_view" in query:
            yield _Batch([{"campaign.id": "101", "ad_group.id": "11", "ad_group_criterion.keyword.text": "protected query", "ad_group_criterion.keyword.match_type": "EXACT", "ad_group_criterion.criterion_id": "99", "ad_group_criterion.status": "ENABLED"}])
        elif "FROM campaign_criterion" in query and "negative = TRUE" in query:
            yield _Batch([{"campaign.id": "101", "campaign.name": "Search", "campaign_criterion.keyword.text": "wasted query", "campaign_criterion.keyword.match_type": "EXACT"}])
        elif "FROM campaign" in query:
            yield _Batch([{"customer.id": customer_id, "customer.descriptive_name": "Example", "customer.currency_code": "USD", "customer.time_zone": "UTC", "campaign.id": "101", "campaign.name": "Search", "campaign.status": "ENABLED", "campaign.serving_status": "SERVING", "campaign.advertising_channel_type": "SEARCH", "campaign.campaign_budget": "customers/1234567890/campaignBudgets/9", "campaign_budget.amount_micros": 1_000_000}])
        else:
            yield _Batch([])


class _Client:
    def __init__(self) -> None:
        self.service = _Service()

    def get_service(self, name: str):
        assert name == "GoogleAdsService"
        return self.service


def test_candidates_are_deterministic_frozen_evidence_only(tmp_path):
    client = _Client()
    workspace = WorkspacePaths(tmp_path)
    provider = GoogleAdsClientProvider({"developer_token": "test"}, client_factory=lambda _: client)
    ScopedRefreshService(provider, workspace).refresh(
        RefreshSpec("1234567890", ("101",), DateRange("2026-08-01", "2026-08-02"))
    )

    result = NegativeKeywordCandidateService(workspace).candidates("1234567890", "101")

    candidates = {item["search_term"]: item for item in result["candidates"]}
    assert candidates["wasted query"]["reason_codes"] == ["SPEND_WITHOUT_CONVERSIONS", "ALREADY_COVERED_NEGATIVE"]
    assert candidates["wasted query"]["eligible"] is False
    assert candidates["protected query"]["reason_codes"] == ["SPEND_WITHOUT_CONVERSIONS", "POSITIVE_KEYWORD_CONFLICT"]
    assert all(ref.startswith(("snapshot:", "evidence:")) for ref in candidates["wasted query"]["evidence_refs"])
    assert not any("path" in value for value in result["limitations"])
