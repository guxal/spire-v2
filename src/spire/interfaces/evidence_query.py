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
    coverage: str = "certified_dataset_rows"
    attribution_scope: str = "The selected frozen Google Ads reporting view."
    aggregation_semantics: str = "Aggregate only within this dataset's declared dimensions."
    limitations: tuple[str, ...] = ()


DATASET_SCHEMAS: dict[str, DatasetSchema] = {
    "campaigns": DatasetSchema(
        "campaigns",
        ("campaign_id", "name", "status", "serving_status", "channel", "currency"),
        ("daily_budget",),
        coverage="current_campaign_configuration",
        attribution_scope="Configuration state for campaigns in the certified snapshot scope.",
        aggregation_semantics="daily_budget is a per-campaign configuration value, not an additive performance metric.",
        limitations=("This dataset contains configuration, not delivery performance.",),
    ),
    "campaign_daily": DatasetSchema(
        "campaign_daily", ("date", "campaign_id", "campaign_name"),
        ("impressions", "clicks", "cost_micros", "conversions", "conversions_value"),
        coverage="canonical_campaign_performance",
        attribution_scope="All performance Google Ads attributes to the selected campaigns in the certified date range.",
        aggregation_semantics="Sum additive metrics across rows; recompute ratios from summed numerators and denominators.",
        limitations=("Conversion totals remain subject to Google Ads attribution and reporting lag at refresh time.",),
    ),
    "search_terms": DatasetSchema(
        "search_terms", ("date", "campaign_id", "ad_group_id", "search_term", "keyword_text", "match_type"),
        ("impressions", "clicks", "cost_micros", "conversions", "conversions_value"),
        coverage="reported_search_queries",
        attribution_scope="Performance disclosed by Google Ads in search_term_view for the selected campaigns.",
        aggregation_semantics="Rows are additive within search_term_view, but are a disclosed subset rather than a campaign control total.",
        limitations=(
            "Google Ads privacy and low-volume thresholds can omit queries, so totals can be lower than campaign_daily.",
            "Non-search and undisclosed query traffic is outside this dataset.",
        ),
    ),
    "keyword_daily": DatasetSchema(
        "keyword_daily", ("date", "campaign_id", "ad_group_id", "keyword_id", "keyword_text", "match_type", "status"),
        ("impressions", "clicks", "cost_micros", "conversions", "conversions_value"),
        coverage="active_keyword_attributed_performance",
        attribution_scope="Performance attributed to non-removed keyword criteria in keyword_view.",
        aggregation_semantics="Rows are additive within keyword_view; compare shares with campaign_daily instead of assuming equality.",
        limitations=(
            "Non-keyword targeting and removed criteria are excluded, so totals can differ from campaign_daily.",
        ),
    ),
    "campaign_ad_groups": DatasetSchema(
        "campaign_ad_groups", ("campaign_id", "ad_group_id", "ad_group_name", "status", "type"),
        ("cpc_bid_micros",),
        coverage="non_removed_ad_group_configuration",
        attribution_scope="Current ad-group structure in the certified campaign scope.",
        aggregation_semantics="cpc_bid_micros is a configuration value and must not be summed as performance.",
        limitations=("This dataset contains structure and bid settings, not delivery performance.",),
    ),
    "campaign_ads": DatasetSchema(
        "campaign_ads", ("campaign_id", "ad_group_id", "ad_id", "status", "type", "headlines", "descriptions", "path1", "path2", "final_urls"),
        (),
        coverage="non_removed_ad_configuration",
        attribution_scope="Current ad status and creative structure, including complete RSA copy arrays.",
        aggregation_semantics="Use for creative coverage and status; join conceptually by ad_id with ad_performance.",
        limitations=("Performance metrics are intentionally exposed through ad_performance.",),
    ),
    "ad_performance": DatasetSchema(
        "ad_performance",
        ("campaign_id", "ad_group_id", "ad_id", "status", "type"),
        ("impressions", "clicks", "cost_micros", "conversions", "conversions_value"),
        coverage="ads_with_reportable_performance",
        attribution_scope="Performance attributed to each non-removed ad over the certified date range.",
        aggregation_semantics="Metrics are additive across distinct ads; recompute CTR, CPC, and CPA from totals.",
        limitations=("Ads with no reportable metrics can remain visible only in campaign_ads.",),
    ),
    "campaign_assets": DatasetSchema(
        "campaign_assets", ("campaign_id", "asset_id", "field_type", "status", "type", "name", "link_text", "callout_text", "mime_type"),
        (),
        coverage="non_removed_campaign_asset_configuration",
        attribution_scope="Current campaign-level asset associations and content-bearing fields.",
        aggregation_semantics="Use for asset coverage and status; join conceptually by asset_id and field_type with campaign_asset_performance.",
        limitations=("Performance metrics are intentionally exposed through campaign_asset_performance.",),
    ),
    "campaign_asset_performance": DatasetSchema(
        "campaign_asset_performance",
        ("campaign_id", "asset_id", "field_type", "status", "type", "name"),
        ("impressions", "clicks", "cost_micros", "conversions", "conversions_value"),
        coverage="campaign_assets_with_reportable_performance",
        attribution_scope="Performance for ads served with each campaign-level asset over the certified date range.",
        aggregation_semantics="Asset rows can overlap when several assets serve together; do not sum them to infer campaign totals.",
        limitations=(
            "Interactions can occur on another part of an ad served with the asset, so metrics are not exclusive asset credit.",
            "Zero-delivery assets can remain visible only in campaign_assets.",
        ),
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
        coverage="rsa_asset_ad_pairs_with_reportable_performance",
        attribution_scope="Performance and Google Ads performance labels for each RSA asset-ad pairing.",
        aggregation_semantics="Assets in the same served ad can share delivery; do not sum asset rows to infer ad or campaign totals.",
        limitations=(
            "Performance labels are comparative Google Ads classifications, not standalone causal measurements.",
            "Asset rows without reportable metrics may be absent.",
        ),
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
        coverage="reportable_geographic_performance",
        attribution_scope="Performance classified by geographic_view and its Google Ads location_type.",
        aggregation_semantics="Rows are additive within this geographic segmentation, not a guaranteed campaign control total.",
        limitations=(
            "Traffic without reportable geographic identity can be absent, so totals can differ from campaign_daily.",
            "location_type must be retained when interpreting presence versus interest classifications.",
        ),
    ),
    "schedule_day": DatasetSchema(
        "schedule_day", ("campaign_id", "day_of_week"),
        ("impressions", "clicks", "cost_micros", "conversions", "conversions_value"),
        coverage="campaign_performance_by_account_day",
        attribution_scope="Campaign performance segmented by day of week in the Google Ads account time zone.",
        aggregation_semantics="Sum within this day segmentation; do not combine its totals with schedule_hour totals.",
        limitations=("Late attribution can change conversion totals in a later refresh.",),
    ),
    "schedule_hour": DatasetSchema(
        "schedule_hour", ("campaign_id", "hour"),
        ("impressions", "clicks", "cost_micros", "conversions", "conversions_value"),
        coverage="campaign_performance_by_account_hour",
        attribution_scope="Campaign performance segmented by hour in the Google Ads account time zone.",
        aggregation_semantics="Sum within this hour segmentation; do not combine its totals with schedule_day totals.",
        limitations=("Late attribution can change conversion totals in a later refresh.",),
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
        coverage="eligible_search_auction_participants_and_campaign_summary",
        attribution_scope="Campaign search impression-share rows plus participant rows returned by Auction Insights.",
        aggregation_semantics="Filter by row_type; group participant metrics by auction_participant_domain. Multi-row share aggregation is an unweighted arithmetic mean.",
        limitations=(
            "CAMPAIGN_SUMMARY and AUCTION_PARTICIPANT metrics have different meanings and must not be combined.",
            "Auction Insights eligibility and reporting thresholds can omit participants or dates.",
        ),
    ),
}


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError("DATE_RANGE_DATE_INVALID") from exc
