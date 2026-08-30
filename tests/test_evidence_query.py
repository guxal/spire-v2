from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from spire.core import ScopeMismatchError
from spire.google_ads import GoogleAdsClientProvider, RefreshSpec, ScopedRefreshService
from spire.interfaces import DateRange, EvidenceQueryRequest
from spire.truth import EvidenceQueryService
from spire.truth.evidence import _dimension_group_key, _normalize_dimension_value


@dataclass
class _Batch:
    results: list[dict]


class _EvidenceService:
    def __init__(self, campaign_rows):
        self.campaign_rows = campaign_rows
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
            "campaign_ads": [{"campaign_id": "101", "ad_group_id": "11", "ad_id": "31", "status": "ENABLED", "type": "RESPONSIVE_SEARCH_AD", "headlines": ["Buy shoes"], "descriptions": ["Comfortable shoes"], "final_urls": []}],
            "campaign_assets": [{"campaign_id": "101", "asset_id": "41", "field_type": "SITELINK", "status": "ENABLED", "type": "SITELINK", "name": "Sizes", "link_text": "See sizes"}],
            "geo_daily": [{"campaign_id": "101", "date": "2026-08-01", "country_criterion_id": "100", "location_type": "LOCATION_OF_PRESENCE", "geo_city": "geoTargetConstants/200", "geo_region": "geoTargetConstants/300", "impressions": 50, "clicks": 5, "cost_micros": 500_000, "conversions": 1}],
            "schedule_day": [{"campaign_id": "101", "day_of_week": "MONDAY", "impressions": 100, "clicks": 10, "cost_micros": 1_000_000, "conversions": 2}],
            "schedule_hour": [{"campaign_id": "101", "hour": 9, "impressions": 100, "clicks": 10, "cost_micros": 1_000_000, "conversions": 2}],
            "auction_insights": [{"campaign_id": "101", "date": "2026-08-01", "search_impression_share": 0.5, "search_top_impression_share": 0.4}],
        }

    def search_stream(self, *, customer_id: str, query: str):
        self.calls.append(query)
        if "FROM customer LIMIT" in query:
            yield _Batch([{"customer.id": customer_id, "customer.descriptive_name": "Example", "customer.currency_code": "USD", "customer.time_zone": "UTC"}])
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
            "campaign_assets": "campaign_asset",
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

    keyword = service.query(
        EvidenceQueryRequest("1234567890", ("101",), "keyword_daily", DateRange("2026-08-01", "2026-08-02"), ("keyword_text",), ("impressions", "clicks", "cost_micros", "conversions", "cpa_micros"))
    )
    assert keyword["aggregates"][0]["keyword_text"] == "shoes"
    assert keyword["aggregates"][0]["cpa_micros"] == 400_000.0

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

    for dataset in ("campaign_ad_groups", "campaign_ads", "campaign_assets", "geo_daily", "schedule_day", "schedule_hour", "auction_insights"):
        result = service.query(EvidenceQueryRequest("1234567890", ("101",), dataset))
        assert result["schema"]["dataset"] == dataset
        assert result["scope"]["extraction_id"].startswith("extract_")

    assert len(transport.calls) == 13
    assert not (tmp_path / "investigations").exists()
    assert not (tmp_path / "data").exists()


def test_structured_dimensions_group_without_losing_json_shape(tmp_path, campaign_rows):
    transport = _EvidenceService(campaign_rows)
    provider = GoogleAdsClientProvider(
        {"developer_token": "test", "login_customer_id": "123-456-7890"},
        client_factory=lambda _: _EvidenceClient(transport),
    )
    from spire.core import WorkspacePaths

    workspace = WorkspacePaths(tmp_path)
    ScopedRefreshService(provider, workspace).refresh(RefreshSpec("1234567890", ("101",)))

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


def test_evidence_query_is_allowlisted_and_scope_safe(fake_runtime):
    workspace, provider, _ = fake_runtime
    ScopedRefreshService(provider, workspace).refresh(RefreshSpec("1234567890", ("101",)))
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
    ScopedRefreshService(provider, workspace).refresh(RefreshSpec("1234567890", ("101",)))
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
