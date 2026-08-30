"""Public, storage-independent evidence query contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from spire.core import validate_customer_id, validate_google_ads_id


@dataclass(frozen=True, slots=True)
class DateRange:
    start: str
    end: str

    def __post_init__(self) -> None:
        start = _iso_date(self.start)
        end = _iso_date(self.end)
        if start > end:
            raise ValueError("DATE_RANGE_START_AFTER_END")
        object.__setattr__(self, "start", start.isoformat())
        object.__setattr__(self, "end", end.isoformat())


@dataclass(frozen=True, slots=True)
class EvidenceQueryRequest:
    customer_id: str
    campaign_ids: tuple[str, ...]
    dataset: str
    date_range: DateRange | None = None
    dimensions: tuple[str, ...] = ()
    metrics: tuple[str, ...] = ()
    filters: Mapping[str, Any] = field(default_factory=dict)
    limit: int = 100
    order_by: str | tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "customer_id", validate_customer_id(self.customer_id))
        normalized_ids = tuple(
            sorted({validate_google_ads_id(value, field="campaign_id") for value in self.campaign_ids}, key=int)
        )
        if not normalized_ids:
            raise ValueError("EVIDENCE_CAMPAIGN_SCOPE_REQUIRED")
        object.__setattr__(self, "campaign_ids", normalized_ids)
        object.__setattr__(self, "dataset", str(self.dataset).strip())
        if self.date_range is not None and not isinstance(self.date_range, DateRange):
            value = self.date_range
            if isinstance(value, Mapping):
                value = DateRange(**value)
            else:
                value = DateRange(*value)
            object.__setattr__(self, "date_range", value)
        object.__setattr__(self, "dimensions", tuple(dict.fromkeys(self.dimensions)))
        object.__setattr__(self, "metrics", tuple(dict.fromkeys(self.metrics)))
        object.__setattr__(self, "filters", dict(self.filters))
        if not 1 <= int(self.limit) <= 500:
            raise ValueError("EVIDENCE_LIMIT_OUT_OF_RANGE")
        object.__setattr__(self, "limit", int(self.limit))
        if self.order_by is not None and isinstance(self.order_by, str):
            object.__setattr__(self, "order_by", (self.order_by,))


@dataclass(frozen=True, slots=True)
class DatasetSchema:
    dataset: str
    dimensions: tuple[str, ...]
    metrics: tuple[str, ...]


DATASET_SCHEMAS: dict[str, DatasetSchema] = {
    "campaigns": DatasetSchema(
        "campaigns",
        ("campaign_id", "name", "status", "serving_status", "channel", "currency"),
        ("daily_budget",),
    ),
    "campaign_daily": DatasetSchema(
        "campaign_daily", ("date", "campaign_id", "campaign_name"),
        ("impressions", "clicks", "cost_micros", "conversions", "conversions_value"),
    ),
    "search_terms": DatasetSchema(
        "search_terms", ("date", "campaign_id", "ad_group_id", "search_term", "keyword_text", "match_type"),
        ("impressions", "clicks", "cost_micros", "conversions", "conversions_value"),
    ),
    "keyword_daily": DatasetSchema(
        "keyword_daily", ("date", "campaign_id", "ad_group_id", "keyword_id", "keyword_text", "match_type", "status"),
        ("impressions", "clicks", "cost_micros", "conversions", "conversions_value"),
    ),
    "campaign_ad_groups": DatasetSchema(
        "campaign_ad_groups", ("campaign_id", "ad_group_id", "ad_group_name", "status", "type"),
        ("cpc_bid_micros",),
    ),
    "campaign_ads": DatasetSchema(
        "campaign_ads", ("campaign_id", "ad_group_id", "ad_id", "status", "type", "headlines", "descriptions", "path1", "path2", "final_urls"),
        (),
    ),
    "ad_performance": DatasetSchema(
        "ad_performance",
        ("campaign_id", "ad_group_id", "ad_id", "status", "type"),
        ("impressions", "clicks", "cost_micros", "conversions", "conversions_value"),
    ),
    "campaign_assets": DatasetSchema(
        "campaign_assets", ("campaign_id", "asset_id", "field_type", "status", "type", "name", "link_text", "callout_text", "mime_type"),
        (),
    ),
    "campaign_asset_performance": DatasetSchema(
        "campaign_asset_performance",
        ("campaign_id", "asset_id", "field_type", "status", "type", "name"),
        ("impressions", "clicks", "cost_micros", "conversions", "conversions_value"),
    ),
    "rsa_asset_performance": DatasetSchema(
        "rsa_asset_performance",
        (
            "campaign_id",
            "ad_group_id",
            "ad_id",
            "asset_id",
            "asset_text",
            "field_type",
            "performance_label",
            "pinned_field",
        ),
        ("impressions", "clicks", "cost_micros", "conversions", "conversions_value"),
    ),
    "geo_daily": DatasetSchema(
        "geo_daily",
        (
            "date",
            "campaign_id",
            "country",
            "country_code",
            "region",
            "city",
            "location_name",
            "location_canonical_name",
            "location_target_type",
            "country_criterion_id",
            "region_criterion_id",
            "city_criterion_id",
            "location_type",
            "geo_city",
            "geo_region",
        ),
        ("impressions", "clicks", "cost_micros", "conversions", "conversions_value"),
    ),
    "schedule_day": DatasetSchema(
        "schedule_day", ("campaign_id", "day_of_week"),
        ("impressions", "clicks", "cost_micros", "conversions", "conversions_value"),
    ),
    "schedule_hour": DatasetSchema(
        "schedule_hour", ("campaign_id", "hour"),
        ("impressions", "clicks", "cost_micros", "conversions", "conversions_value"),
    ),
    "auction_insights": DatasetSchema(
        "auction_insights",
        ("date", "campaign_id", "row_type", "auction_participant_domain"),
        (
            "search_impression_share",
            "search_top_impression_share",
            "search_absolute_top_impression_share",
            "search_rank_lost_impression_share",
            "search_budget_lost_impression_share",
            "auction_insight_search_impression_share",
            "auction_insight_search_overlap_rate",
            "auction_insight_search_position_above_rate",
            "auction_insight_search_outranking_share",
            "auction_insight_search_top_impression_percentage",
            "auction_insight_search_absolute_top_impression_percentage",
        ),
    ),
}


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError("DATE_RANGE_DATE_INVALID") from exc
