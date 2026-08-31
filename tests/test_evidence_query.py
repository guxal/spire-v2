from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from spire.core import ScopeMismatchError
from spire.google_ads import GoogleAdsClientProvider, RefreshSpec, ScopedRefreshService
from spire.google_ads.evidence_datasets import _strings
from spire.interfaces import DateRange, EvidenceQueryRequest
from spire.truth import EvidenceQueryService
from spire.truth.evidence import _dimension_group_key, _normalize_dimension_value


@dataclass
class _Batch:
    results: list[dict]


class _EvidenceService:
    def __init__(self, campaign_rows, *, participant_query_unavailable: bool = False):
        self.campaign_rows = campaign_rows
        self.participant_query_unavailable = participant_query_unavailable
        self.calls: list[str] = []
        self.rows = {
            "campaign_daily": [
                {"campaign_id": "101", "date": "2026-08-01", "impressions": 100, "clicks": 10, "cost_micros": 1_000_000, "conversions": 2},
                {"campaign_id": "101", "date": "2026-08-02", "impressions": 200, "clicks": 20, "cost_micros": 3_000_000, "conversions": 4},
            ],
            "search_terms": [
                {"campaign_id": "101", "date": "2026-08-01", "ad_group_id": "11", "search_term": "red shoes", "keyword_text": "shoes", "match_type": "EXACT", "impressions": 80, "clicks": 8, "cost_micros": 800_000, "conversions": 2},
                {"campaign_id": "101", "date": "2026-08-02", "ad_group_id": "11", "search_term": "blue shoes", "keyword_text": "shoes", "match_type": "EXACT", "impressions": 60, "clicks": 3, "cost_micros": 600_000, "conversions": 0},
            ],
            "keyword_daily": [
                {"campaign_id": "101", "date": "2026-08-01", "ad_group_id": "11", "keyword_id": "21", "keyword_text": "shoes", "match_type": "EXACT", "status": "ENABLED", "impressions": 80, "clicks": 8, "cost_micros": 800_000, "conversions": 2},
            ],
            "campaign_ad_groups": [{"campaign_id": "101", "ad_group_id": "11", "ad_group_name": "Core", "status": "ENABLED", "type": "SEARCH_STANDARD"}],
            "campaign_ads": [{"campaign_id": "101", "ad_group_id": "11", "ad_id": "31", "status": "ENABLED", "type": "RESPONSIVE_SEARCH_AD", "headlines": [{"text": "Buy shoes", "asset_performance_label": "PENDING"}], "descriptions": ["Comfortable shoes"], "final_urls": []}],
            "ad_performance": [{"campaign_id": "101", "ad_group_id": "11", "ad_id": "31", "status": "ENABLED", "type": "RESPONSIVE_SEARCH_AD", "impressions": 90, "clicks": 9, "cost_micros": 900_000, "conversions": 2}],
            "campaign_assets": [{"campaign_id": "101", "asset_id": "41", "field_type": "SITELINK", "status": "ENABLED", "type": "SITELINK", "name": "Sizes", "link_text": "See sizes"}],
            "campaign_asset_performance": [{"campaign_id": "101", "asset_id": "41", "field_type": "SITELINK", "status": "ENABLED", "type": "SITELINK", "name": "Sizes", "impressions": 70, "clicks": 7, "cost_micros": 700_000, "conversions": 1}],
            "rsa_asset_performance": [{"campaign_id": "101", "ad_group_id": "11", "ad_id": "31", "asset_id": "51", "asset_text": "Buy shoes", "field_type": "HEADLINE", "performance_label": "BEST", "pinned_field": "HEADLINE_1", "impressions": 80, "clicks": 8, "cost_micros": 800_000, "conversions": 2}],
            "geo_daily": [{"campaign_id": "101", "date": "2026-08-01", "country_criterion_id": "100", "location_type": "LOCATION_OF_PRESENCE", "geo_city": "geoTargetConstants/200", "geo_region": "geoTargetConstants/300", "impressions": 50, "clicks": 5, "cost_micros": 500_000, "conversions": 1}],
            "schedule_day": [{"campaign_id": "101", "day_of_week": "MONDAY", "impressions": 100, "clicks": 10, "cost_micros": 1_000_000, "conversions": 2}],
            "schedule_hour": [{"campaign_id": "101", "hour": 9, "impressions": 100, "clicks": 10, "cost_micros": 1_000_000, "conversions": 2}],
            "auction_insights": [{"campaign_id": "101", "date": "2026-08-01", "auction_participant_domain": "competitor.example", "auction_insight_search_impression_share": 0.35, "auction_insight_search_overlap_rate": 0.2, "auction_insight_search_position_above_rate": 0.1, "auction_insight_search_outranking_share": 0.7, "auction_insight_search_top_impression_percentage": 0.4, "auction_insight_search_absolute_top_impression_percentage": 0.15}],
        }
        self.auction_summary_rows = [
            {"campaign_id": "101", "date": "2026-08-01", "search_impression_share": 0.5, "search_top_impression_share": 0.4, "search_absolute_top_impression_share": 0.2, "search_rank_lost_impression_share": 0.3, "search_budget_lost_impression_share": 0.2}
        ]

    def search_stream(self, *, customer_id: str, query: str):
        self.calls.append(query)
        if "FROM customer LIMIT" in query:
            yield _Batch([{"customer.id": customer_id, "customer.descriptive_name": "Example", "customer.currency_code": "USD", "customer.time_zone": "UTC"}])
            return
        if "segments.auction_insight_domain" in query:
            if self.participant_query_unavailable:
                raise RuntimeError("restricted auction participant metrics")
            yield _Batch(self.rows["auction_insights"])
            return
        if "metrics.search_impression_share" in query and "FROM campaign WHERE" in query:
            yield _Batch(self.auction_summary_rows)
            return
        if "FROM ad_group_ad_asset_view " in query:
            yield _Batch(self.rows["rsa_asset_performance"])
            return
        if "metrics.impressions" in query and "FROM ad_group_ad " in query:
            yield _Batch(self.rows["ad_performance"])
            return
        if "metrics.impressions" in query and "FROM campaign_asset " in query:
            yield _Batch(self.rows["campaign_asset_performance"])
            return
        if "metrics.impressions" not in query and "FROM campaign WHERE" in query:
            yield _Batch(self.campaign_rows)
            return
        if "FROM geo_target_constant " in query:
            yield _Batch(
                [
                    {"geo_target_constant.id": "100", "geo_target_constant.name": "Colombia", "geo_target_constant.canonical_name": "Colombia", "geo_target_constant.country_code": "CO", "geo_target_constant.target_type": "Country"},
                    {"geo_target_constant.id": "200", "geo_target_constant.name": "Bogota", "geo_target_constant.canonical_name": "Bogota, Bogota D.C., Colombia", "geo_target_constant.country_code": "CO", "geo_target_constant.target_type": "City"},
                    {"geo_target_constant.id": "300", "geo_target_constant.name": "Bogota D.C.", "geo_target_constant.canonical_name": "Bogota D.C., Colombia", "geo_target_constant.country_code": "CO", "geo_target_constant.target_type": "Region"},
                ]
            )
            return
        for dataset, rows in self.rows.items():
            if f"FROM {self._view(dataset)} " in query:
                yield _Batch(rows)
                return
        raise AssertionError(f"unexpected query: {query}")

    @staticmethod
    def _view(dataset: str) -> str:
        return {
            "campaign_daily": "campaign",
            "search_terms": "search_term_view",
            "keyword_daily": "keyword_view",
            "campaign_ad_groups": "ad_group",
            "campaign_ads": "ad_group_ad",
            "ad_performance": "ad_group_ad",
            "campaign_assets": "campaign_asset",
            "campaign_asset_performance": "campaign_asset",
            "rsa_asset_performance": "ad_group_ad_asset_view",
            "geo_daily": "geographic_view",
            "schedule_day": "campaign",
            "schedule_hour": "campaign",
            "auction_insights": "campaign",
        }[dataset]


class _EvidenceClient:
    def __init__(self, service):
        self.service = service

    def get_service(self, name: str):
        assert name == "GoogleAdsService"
        return self.service


def test_evidence_query_returns_analysis_ready_frozen_evidence(tmp_path, campaign_rows):
    assert not (tmp_path / ".spire/customers/1234567890").exists()
    transport = _EvidenceService(campaign_rows)
    provider = GoogleAdsClientProvider(
        {"developer_token": "test", "login_customer_id": "123-456-7890"},
        client_factory=lambda _: _EvidenceClient(transport),
    )
    from spire.core import WorkspacePaths

    workspace = WorkspacePaths(tmp_path)
    refresh = ScopedRefreshService(provider, workspace)
    refresh.refresh(RefreshSpec("1234567890", ("101",), DateRange("2026-08-01", "2026-08-02")))
    service = EvidenceQueryService(workspace)

    response = service.query(
        EvidenceQueryRequest(
            customer_id="1234567890",
            campaign_ids=("101",),
            dataset="campaign_daily",
            date_range=DateRange("2026-08-01", "2026-08-02"),
            dimensions=("date",),
            metrics=("impressions", "clicks", "cost_micros", "conversions", "ctr", "cpc_micros", "cpa_micros"),
        )
    )
    assert response["aggregates"] == [
        {"date": "2026-08-01", "impressions": 100, "clicks": 10, "cost_micros": 1_000_000, "conversions": 2, "ctr": 0.1, "cpc_micros": 100_000.0, "cpa_micros": 500_000.0},
        {"date": "2026-08-02", "impressions": 200, "clicks": 20, "cost_micros": 3_000_000, "conversions": 4, "ctr": 0.1, "cpc_micros": 150_000.0, "cpa_micros": 750_000.0},
    ]
    assert response["scope"]["campaign_ids"] == ["101"]
    assert response["freshness"]["status"] == "FRESH"
    assert response["evidence_ref"].startswith("extract_")
    assert all("path" not in key for key in response)
    assert response["semantics"]["coverage"] == "canonical_campaign_performance"
    assert response["semantics"]["comparison_baseline"] == "campaign_daily"

    totals = service.query(
        EvidenceQueryRequest(
            "1234567890", ("101",), "campaign_daily",
            DateRange("2026-08-01", "2026-08-02"), (),
            ("impressions", "clicks", "cost_micros", "conversions", "ctr", "cpc_micros", "cpa_micros"),
        )
    )
    assert totals["aggregates"] == [
        {"impressions": 300, "clicks": 30, "cost_micros": 4_000_000, "conversions": 6, "ctr": 0.1, "cpc_micros": 133333.33333333334, "cpa_micros": 666666.6666666666}
    ]

    search_terms = service.query(
        EvidenceQueryRequest(
            "1234567890", ("101",), "search_terms",
            DateRange("2026-08-01", "2026-08-02"),
            ("search_term",), ("impressions", "clicks", "cost_micros", "conversions", "ctr"),
            order_by="search_term",
        )
    )
    assert search_terms["aggregates"][0]["search_term"] == "blue shoes"
    assert search_terms["aggregates"][1]["conversions"] == 2
    assert "privacy and low-volume" in search_terms["semantics"]["limitations"][0]
    assert "totals can be lower than campaign_daily" in search_terms["limitations"][0]

    keyword = service.query(
        EvidenceQueryRequest("1234567890", ("101",), "keyword_daily", DateRange("2026-08-01", "2026-08-02"), ("keyword_text",), ("impressions", "clicks", "cost_micros", "conversions", "cpa_micros"))
    )
    assert keyword["aggregates"][0]["keyword_text"] == "shoes"
    assert keyword["aggregates"][0]["cpa_micros"] == 400_000.0
    assert "Non-keyword targeting" in keyword["semantics"]["limitations"][0]

    geo = service.query(
        EvidenceQueryRequest(
            "1234567890",
            ("101",),
            "geo_daily",
            dimensions=(
                "country",
                "region",
                "city",
                "location_name",
                "country_criterion_id",
                "region_criterion_id",
                "city_criterion_id",
            ),
            metrics=("impressions",),
        )
    )
    assert geo["aggregates"] == [
        {
            "country": "Colombia",
            "region": "Bogota D.C.",
            "city": "Bogota",
            "location_name": "Bogota",
            "country_criterion_id": "100",
            "region_criterion_id": "300",
            "city_criterion_id": "200",
            "impressions": 50,
        }
    ]
    assert "geoTargetConstants/" not in json.dumps(geo)
    assert "totals can differ from campaign_daily" in geo["semantics"]["limitations"][0]

    auction = service.query(
        EvidenceQueryRequest(
            "1234567890",
            ("101",),
            "auction_insights",
            dimensions=("row_type", "auction_participant_domain"),
            metrics=(
                "auction_insight_search_impression_share",
                "auction_insight_search_overlap_rate",
                "auction_insight_search_position_above_rate",
            ),
        )
    )
    assert auction["aggregates"] == [
        {
            "row_type": "AUCTION_PARTICIPANT",
            "auction_participant_domain": "competitor.example",
            "auction_insight_search_impression_share": 0.35,
            "auction_insight_search_overlap_rate": 0.2,
            "auction_insight_search_position_above_rate": 0.1,
        },
        {
            "row_type": "CAMPAIGN_SUMMARY",
            "auction_participant_domain": None,
            "auction_insight_search_impression_share": None,
            "auction_insight_search_overlap_rate": None,
            "auction_insight_search_position_above_rate": None,
        },
    ]
    auction_summary = service.query(
        EvidenceQueryRequest(
            "1234567890",
            ("101",),
            "auction_insights",
            filters={"row_type": "CAMPAIGN_SUMMARY"},
            metrics=("search_impression_share", "search_budget_lost_impression_share"),
        )
    )
    assert auction_summary["aggregates"] == [
        {
            "search_impression_share": 0.5,
            "search_budget_lost_impression_share": 0.2,
        }
    ]
    assert "Filter by row_type" in auction["semantics"]["aggregation_semantics"]

    ad_performance = service.query(
        EvidenceQueryRequest(
            "1234567890",
            ("101",),
            "ad_performance",
            dimensions=("ad_id", "type"),
            metrics=("impressions", "clicks", "conversions", "ctr", "cpa_micros"),
        )
    )
    assert ad_performance["aggregates"] == [
        {
            "ad_id": "31",
            "type": "RESPONSIVE_SEARCH_AD",
            "impressions": 90,
            "clicks": 9,
            "conversions": 2,
            "ctr": 0.1,
            "cpa_micros": 450_000.0,
        }
    ]
    campaign_asset_performance = service.query(
        EvidenceQueryRequest(
            "1234567890",
            ("101",),
            "campaign_asset_performance",
            dimensions=("asset_id", "field_type"),
            metrics=("impressions", "clicks", "conversions"),
        )
    )
    assert campaign_asset_performance["aggregates"] == [
        {
            "asset_id": "41",
            "field_type": "SITELINK",
            "impressions": 70,
            "clicks": 7,
            "conversions": 1,
        }
    ]
    rsa_assets = service.query(
        EvidenceQueryRequest(
            "1234567890",
            ("101",),
            "rsa_asset_performance",
            dimensions=("asset_text", "field_type", "performance_label", "pinned_field"),
            metrics=("impressions", "clicks", "conversions"),
        )
    )
    assert rsa_assets["aggregates"] == [
        {
            "asset_text": "Buy shoes",
            "field_type": "HEADLINE",
            "performance_label": "BEST",
            "pinned_field": "HEADLINE_1",
            "impressions": 80,
            "clicks": 8,
            "conversions": 2,
        }
    ]

    for dataset in ("campaign_ad_groups", "campaign_ads", "ad_performance", "campaign_assets", "campaign_asset_performance", "rsa_asset_performance", "geo_daily", "schedule_day", "schedule_hour", "auction_insights"):
        result = service.query(EvidenceQueryRequest("1234567890", ("101",), dataset))
        assert result["schema"]["dataset"] == dataset
        assert result["scope"]["extraction_id"].startswith("extract_")

    assert len(transport.calls) == 22
    assert not (tmp_path / "investigations").exists()
    assert not (tmp_path / "data").exists()


def test_auction_summary_survives_unavailable_participant_metrics(tmp_path, campaign_rows):
    transport = _EvidenceService(campaign_rows, participant_query_unavailable=True)
    provider = GoogleAdsClientProvider(
        {"developer_token": "test", "login_customer_id": "123-456-7890"},
        client_factory=lambda _: _EvidenceClient(transport),
    )
    from spire.core import WorkspacePaths

    workspace = WorkspacePaths(tmp_path)
    ScopedRefreshService(provider, workspace).refresh(
        RefreshSpec("1234567890", ("101",), DateRange("2026-08-01", "2026-08-02"))
    )

    response = EvidenceQueryService(workspace).query(
        EvidenceQueryRequest(
            "1234567890",
            ("101",),
            "auction_insights",
            dimensions=("row_type", "participant_data_status", "participant_data_limitation"),
            metrics=("search_impression_share",),
        )
    )

    assert response["aggregates"] == [
        {
            "row_type": "PARTICIPANT_AVAILABILITY",
            "participant_data_status": "QUERY_UNAVAILABLE",
            "participant_data_limitation": "Google Ads did not authorize or complete the Auction Insights participant query for this refresh.",
            "search_impression_share": None,
        },
        {
            "row_type": "CAMPAIGN_SUMMARY",
            "participant_data_status": "NOT_APPLICABLE",
            "participant_data_limitation": None,
            "search_impression_share": 0.5,
        },
    ]


def test_structured_dimensions_group_without_losing_json_shape(tmp_path, campaign_rows):
    transport = _EvidenceService(campaign_rows)
    provider = GoogleAdsClientProvider(
        {"developer_token": "test", "login_customer_id": "123-456-7890"},
        client_factory=lambda _: _EvidenceClient(transport),
    )
    from spire.core import WorkspacePaths

    workspace = WorkspacePaths(tmp_path)
    ScopedRefreshService(provider, workspace).refresh(
        RefreshSpec("1234567890", ("101",), DateRange("2026-08-01", "2026-08-02"))
    )

    response = EvidenceQueryService(workspace).query(
        EvidenceQueryRequest(
            "1234567890",
            ("101",),
            "campaign_ads",
            dimensions=("headlines", "final_urls"),
        )
    )

    assert response["aggregates"] == [
        {"headlines": ["Buy shoes"], "final_urls": []}
    ]
    repeated = EvidenceQueryService(workspace).query(
        EvidenceQueryRequest(
            "1234567890",
            ("101",),
            "campaign_ads",
            dimensions=("headlines", "final_urls"),
        )
    )
    assert response["rows"] == repeated["rows"]
    assert response["aggregates"] == repeated["aggregates"]
    assert json.loads(json.dumps(response))["aggregates"][0]["headlines"] == ["Buy shoes"]


def test_nested_structured_dimension_keys_are_deterministic():
    left = {"placements": [{"pin": "HEADLINE_1", "text": "Buy shoes"}], "labels": []}
    right = {"labels": [], "placements": [{"text": "Buy shoes", "pin": "HEADLINE_1"}]}

    assert _normalize_dimension_value(left) == right
    assert _dimension_group_key(left) == _dimension_group_key(right)
    assert json.loads(json.dumps(_normalize_dimension_value(left))) == right
    with pytest.raises(TypeError, match="UNSUPPORTED_EVIDENCE_DIMENSION_VALUE:object"):
        _normalize_dimension_value(object())


def test_ad_copy_extraction_rejects_unknown_objects_instead_of_stringifying():
    with pytest.raises(TypeError, match="UNSUPPORTED_EVIDENCE_STRING_LIST_ITEM:object"):
        _strings([object()])


def test_evidence_query_is_allowlisted_and_scope_safe(fake_runtime):
    workspace, provider, _ = fake_runtime
    ScopedRefreshService(provider, workspace).refresh(
        RefreshSpec("1234567890", ("101",), DateRange("2026-08-01", "2026-08-02"))
    )
    service = EvidenceQueryService(workspace)
    with pytest.raises(ValueError, match="UNKNOWN_EVIDENCE_DATASET"):
        service.query(EvidenceQueryRequest("1234567890", ("101",), "campaign_daily;DROP"))
    with pytest.raises(ValueError, match="UNKNOWN_EVIDENCE_DIMENSIONS"):
        service.query(EvidenceQueryRequest("1234567890", ("101",), "campaign_daily", dimensions=("resource_name",)))
    with pytest.raises(TypeError, match="COMPLEX_FILTER_NOT_ALLOWED"):
        service.query(EvidenceQueryRequest("1234567890", ("101",), "campaign_daily", filters={"campaign_id": {"$gt": "1"}}))


def test_evidence_query_never_reads_legacy_extraction(fake_runtime):
    workspace, _, _ = fake_runtime
    legacy = workspace.customer_root("1234567890") / "old-extraction"
    legacy.mkdir(parents=True)
    service = EvidenceQueryService(workspace)
    with pytest.raises(Exception) as failure:
        service.query(EvidenceQueryRequest("1234567890", ("101",), "campaign_daily"))
    assert "CURRENT_EXTRACTION_NOT_FOUND" in str(failure.value)


def test_date_range_and_order_are_certified_contracts(fake_runtime):
    workspace, provider, _ = fake_runtime
    ScopedRefreshService(provider, workspace).refresh(
        RefreshSpec("1234567890", ("101",), DateRange("2026-08-01", "2026-08-02"))
    )
    service = EvidenceQueryService(workspace)
    with pytest.raises(ScopeMismatchError, match="EVIDENCE_DATE_RANGE_NOT_CERTIFIED"):
        service.query(
            EvidenceQueryRequest(
                "1234567890", ("101",), "campaign_daily", DateRange("2026-01-01", "2026-01-02")
            )
        )
    with pytest.raises(ValueError, match="UNKNOWN_EVIDENCE_ORDER_FIELDS"):
        service.query(
            EvidenceQueryRequest("1234567890", ("101",), "campaign_daily", order_by="secret")
        )
