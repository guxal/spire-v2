"""Allowlisted extraction queries and canonical row normalization."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from spire.core import validate_google_ads_id
from spire.interfaces import DateRange

EVIDENCE_DATASETS = (
    "campaign_daily",
    "search_terms",
    "keyword_daily",
    "campaign_ad_groups",
    "campaign_ads",
    "campaign_assets",
    "geo_daily",
    "schedule_day",
    "schedule_hour",
    "auction_insights",
)


def evidence_query(dataset: str, campaign_ids: tuple[str, ...], date_range: DateRange | None) -> str:
    if dataset not in EVIDENCE_DATASETS:
        raise ValueError(f"UNSUPPORTED_EVIDENCE_DATASET:{dataset}")
    ids = ", ".join(campaign_ids)
    date_clause = ""
    if date_range is not None:
        date_clause = f" AND segments.date BETWEEN '{date_range.start}' AND '{date_range.end}'"
    queries = {
        "campaign_daily": "SELECT customer.id, campaign.id, campaign.name, segments.date, metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions, metrics.conversions_value FROM campaign WHERE campaign.id IN ({ids}){date_clause} ORDER BY segments.date, campaign.id",
        "search_terms": "SELECT campaign.id, ad_group.id, search_term_view.search_term, segments.date, metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions, metrics.conversions_value FROM search_term_view WHERE campaign.id IN ({ids}){date_clause} ORDER BY segments.date, campaign.id, ad_group.id, search_term_view.search_term",
        "keyword_daily": "SELECT campaign.id, ad_group.id, ad_group_criterion.criterion_id, ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type, ad_group_criterion.status, segments.date, metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions, metrics.conversions_value FROM keyword_view WHERE campaign.id IN ({ids}){date_clause} AND ad_group_criterion.status != 'REMOVED' ORDER BY segments.date, campaign.id, ad_group.id, ad_group_criterion.criterion_id",
        "campaign_ad_groups": "SELECT campaign.id, ad_group.id, ad_group.name, ad_group.status, ad_group.type, ad_group.cpc_bid_micros FROM ad_group WHERE campaign.id IN ({ids}) AND ad_group.status != 'REMOVED' ORDER BY campaign.id, ad_group.id",
        "campaign_ads": "SELECT campaign.id, ad_group.id, ad_group_ad.ad.id, ad_group_ad.status, ad_group_ad.ad.type, ad_group_ad.ad.final_urls, ad_group_ad.ad.responsive_search_ad.headlines, ad_group_ad.ad.responsive_search_ad.descriptions, ad_group_ad.ad.responsive_search_ad.path1, ad_group_ad.ad.responsive_search_ad.path2 FROM ad_group_ad WHERE campaign.id IN ({ids}) AND ad_group_ad.status != 'REMOVED' ORDER BY campaign.id, ad_group.id, ad_group_ad.ad.id",
        "campaign_assets": "SELECT campaign.id, campaign_asset.field_type, campaign_asset.status, asset.id, asset.name, asset.type, asset.sitelink_asset.link_text, asset.callout_asset.callout_text, asset.image_asset.mime_type FROM campaign_asset WHERE campaign.id IN ({ids}) AND campaign_asset.status != 'REMOVED' ORDER BY campaign.id, campaign_asset.field_type, asset.id",
        "geo_daily": "SELECT campaign.id, geographic_view.country_criterion_id, geographic_view.location_type, segments.date, segments.geo_target_city, segments.geo_target_region, metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions, metrics.conversions_value FROM geographic_view WHERE campaign.id IN ({ids}){date_clause} ORDER BY segments.date, campaign.id",
        "schedule_day": "SELECT campaign.id, segments.day_of_week, metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions, metrics.conversions_value FROM campaign WHERE campaign.id IN ({ids}){date_clause} ORDER BY campaign.id, segments.day_of_week",
        "schedule_hour": "SELECT campaign.id, segments.hour, metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions, metrics.conversions_value FROM campaign WHERE campaign.id IN ({ids}){date_clause} ORDER BY campaign.id, segments.hour",
        "auction_insights": "SELECT campaign.id, segments.date, segments.auction_insight_domain, metrics.auction_insight_search_impression_share, metrics.auction_insight_search_overlap_rate, metrics.auction_insight_search_position_above_rate, metrics.auction_insight_search_outranking_share, metrics.auction_insight_search_top_impression_percentage, metrics.auction_insight_search_absolute_top_impression_percentage FROM campaign WHERE campaign.id IN ({ids}){date_clause} ORDER BY segments.date, campaign.id, segments.auction_insight_domain",
    }
    return queries[dataset].format(ids=ids, date_clause=date_clause)


def normalize_evidence_row(dataset: str, row: Any, customer_id: str) -> dict[str, Any]:
    campaign_id = validate_google_ads_id(_value(row, "campaign.id", "campaign_id") or "0", field="campaign_id")
    result: dict[str, Any] = {"customer_id": customer_id, "campaign_id": campaign_id}
    if dataset in {"campaign_daily", "search_terms", "keyword_daily", "geo_daily"}:
        result["date"] = _string(_value(row, "segments.date", "date"))
    if dataset == "campaign_daily":
        result["campaign_name"] = _string(_value(row, "campaign.name", "campaign_name"))
        return _metrics(result, row)
    if dataset == "search_terms":
        result.update(
            search_term=_string(_value(row, "search_term_view.search_term", "search_term")),
            ad_group_id=_string(_value(row, "ad_group.id", "ad_group_id")),
            keyword_text=_string(_value(row, "ad_group_criterion.keyword.text", "keyword_text")),
            match_type=_enum(_value(row, "ad_group_criterion.keyword.match_type", "match_type")),
        )
        return _metrics(result, row)
    if dataset == "keyword_daily":
        result.update(
            ad_group_id=_string(_value(row, "ad_group.id", "ad_group_id")),
            keyword_id=_string(_value(row, "ad_group_criterion.criterion_id", "keyword_id")),
            keyword_text=_string(_value(row, "ad_group_criterion.keyword.text", "keyword_text")),
            match_type=_enum(_value(row, "ad_group_criterion.keyword.match_type", "match_type")),
            status=_enum(_value(row, "ad_group_criterion.status", "status")),
        )
        return _metrics(result, row)
    if dataset == "campaign_ad_groups":
        result.update(
            ad_group_id=_string(_value(row, "ad_group.id", "ad_group_id")),
            ad_group_name=_string(_value(row, "ad_group.name", "ad_group_name")),
            status=_enum(_value(row, "ad_group.status", "status")),
            type=_enum(_value(row, "ad_group.type", "type")),
            cpc_bid_micros=_int(_value(row, "ad_group.cpc_bid_micros", "cpc_bid_micros")),
        )
        return result
    if dataset == "campaign_ads":
        result.update(
            ad_group_id=_string(_value(row, "ad_group.id", "ad_group_id")),
            ad_id=_string(_value(row, "ad_group_ad.ad.id", "ad_id")),
            status=_enum(_value(row, "ad_group_ad.status", "status")),
            type=_enum(_value(row, "ad_group_ad.ad.type", "type")),
            headlines=_strings(_value(row, "ad_group_ad.ad.responsive_search_ad.headlines", "headlines")),
            descriptions=_strings(_value(row, "ad_group_ad.ad.responsive_search_ad.descriptions", "descriptions")),
            path1=_string(_value(row, "ad_group_ad.ad.responsive_search_ad.path1", "path1")),
            path2=_string(_value(row, "ad_group_ad.ad.responsive_search_ad.path2", "path2")),
            final_urls=_strings(_value(row, "ad_group_ad.ad.final_urls", "final_urls")),
        )
        return result
    if dataset == "campaign_assets":
        result.update(
            asset_id=_string(_value(row, "asset.id", "asset_id")),
            field_type=_enum(_value(row, "campaign_asset.field_type", "field_type")),
            status=_enum(_value(row, "campaign_asset.status", "status")),
            type=_enum(_value(row, "asset.type", "type")),
            name=_string(_value(row, "asset.name", "name")),
            link_text=_string(_value(row, "asset.sitelink_asset.link_text", "link_text")),
            callout_text=_string(_value(row, "asset.callout_asset.callout_text", "callout_text")),
            mime_type=_string(_value(row, "asset.image_asset.mime_type", "mime_type")),
        )
        return result
    if dataset == "geo_daily":
        country_criterion_id = _criterion_id(
            _value(row, "geographic_view.country_criterion_id", "country_criterion_id")
        )
        city_criterion_id = _criterion_id(
            _value(row, "segments.geo_target_city", "city_criterion_id", "geo_city")
        )
        region_criterion_id = _criterion_id(
            _value(row, "segments.geo_target_region", "region_criterion_id", "geo_region")
        )
        result.update(
            country=None,
            country_code=None,
            region=None,
            city=None,
            location_name=None,
            location_canonical_name=None,
            location_target_type=None,
            country_criterion_id=country_criterion_id,
            region_criterion_id=region_criterion_id,
            city_criterion_id=city_criterion_id,
            location_type=_enum(_value(row, "geographic_view.location_type", "location_type")),
            geo_city=None,
            geo_region=None,
        )
        return _metrics(result, row)
    if dataset == "schedule_day":
        result["day_of_week"] = _enum(_value(row, "segments.day_of_week", "day_of_week"))
        return _metrics(result, row)
    if dataset == "schedule_hour":
        result["hour"] = _int(_value(row, "segments.hour", "hour"))
        return _metrics(result, row)
    result.update(
        date=_string(_value(row, "segments.date", "date")),
        row_type="AUCTION_PARTICIPANT",
        auction_participant_domain=_string(
            _value(row, "segments.auction_insight_domain", "auction_participant_domain")
        ),
    )
    return {
        **result,
        **{
            name: _number(_value(row, f"metrics.{name}", name))
            for name in (
                "auction_insight_search_impression_share",
                "auction_insight_search_overlap_rate",
                "auction_insight_search_position_above_rate",
                "auction_insight_search_outranking_share",
                "auction_insight_search_top_impression_percentage",
                "auction_insight_search_absolute_top_impression_percentage",
            )
        },
    }


def auction_summary_query(
    campaign_ids: tuple[str, ...], date_range: DateRange | None
) -> str:
    ids = ", ".join(campaign_ids)
    date_clause = ""
    if date_range is not None:
        date_clause = (
            f" AND segments.date BETWEEN '{date_range.start}' AND '{date_range.end}'"
        )
    return (
        "SELECT campaign.id, segments.date, metrics.search_impression_share, "
        "metrics.search_top_impression_share, "
        "metrics.search_absolute_top_impression_share, "
        "metrics.search_rank_lost_impression_share, "
        "metrics.search_budget_lost_impression_share "
        f"FROM campaign WHERE campaign.id IN ({ids}){date_clause} "
        "ORDER BY segments.date, campaign.id"
    )


def normalize_auction_summary_row(row: Any, customer_id: str) -> dict[str, Any]:
    campaign_id = validate_google_ads_id(
        _value(row, "campaign.id", "campaign_id") or "0",
        field="campaign_id",
    )
    result: dict[str, Any] = {
        "customer_id": customer_id,
        "campaign_id": campaign_id,
        "date": _string(_value(row, "segments.date", "date")),
        "row_type": "CAMPAIGN_SUMMARY",
        "auction_participant_domain": None,
    }
    result.update(
        {
            name: _number(_value(row, f"metrics.{name}", name))
            for name in (
                "search_impression_share",
                "search_top_impression_share",
                "search_absolute_top_impression_share",
                "search_rank_lost_impression_share",
                "search_budget_lost_impression_share",
            )
        }
    )
    return result


def _metrics(result: dict[str, Any], row: Any) -> dict[str, Any]:
    result.update(
        impressions=_int(_value(row, "metrics.impressions", "impressions")) or 0,
        clicks=_int(_value(row, "metrics.clicks", "clicks")) or 0,
        cost_micros=_int(_value(row, "metrics.cost_micros", "cost_micros")) or 0,
        conversions=_number(_value(row, "metrics.conversions", "conversions")) or 0,
        conversions_value=_number(_value(row, "metrics.conversions_value", "conversions_value")) or 0,
    )
    return result


def _value(row: Any, *names: str) -> Any:
    for name in names:
        if isinstance(row, Mapping) and name in row:
            return row[name]
        current = row
        try:
            for part in name.split("."):
                current = current[part] if isinstance(current, Mapping) else getattr(current, part)
            return current
        except (AttributeError, KeyError, TypeError):
            continue
    return None


def _string(value: Any) -> str | None:
    return None if value is None else str(value)


def _enum(value: Any) -> str | None:
    return None if value is None else str(getattr(value, "name", value)).split(".")[-1]


def _int(value: Any) -> int | None:
    return None if value in (None, "") else int(value)


def _number(value: Any) -> float | int | None:
    return None if value in (None, "") else float(value)


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [str(value)]
    return [str(item) for item in value]


def geo_target_query(rows: list[Mapping[str, Any]]) -> str | None:
    """Build one deterministic refresh-time lookup for reported geo identities."""

    criterion_ids = {
        criterion_id
        for row in rows
        for field in (
            "country_criterion_id",
            "region_criterion_id",
            "city_criterion_id",
        )
        if (criterion_id := _criterion_id(row.get(field))) is not None
    }
    if not criterion_ids:
        return None
    resources = ", ".join(
        f"'geoTargetConstants/{criterion_id}'"
        for criterion_id in sorted(criterion_ids, key=lambda value: (len(value), value))
    )
    return (
        "SELECT geo_target_constant.resource_name, geo_target_constant.id, "
        "geo_target_constant.name, geo_target_constant.canonical_name, "
        "geo_target_constant.country_code, geo_target_constant.target_type "
        "FROM geo_target_constant "
        f"WHERE geo_target_constant.resource_name IN ({resources}) "
        "ORDER BY geo_target_constant.id"
    )


def normalize_geo_target_row(row: Any) -> dict[str, Any]:
    criterion_id = _criterion_id(
        _value(row, "geo_target_constant.id", "id")
        or _value(row, "geo_target_constant.resource_name", "resource_name")
    )
    return {
        "criterion_id": criterion_id,
        "name": _string(_value(row, "geo_target_constant.name", "name")),
        "canonical_name": _string(
            _value(row, "geo_target_constant.canonical_name", "canonical_name")
        ),
        "country_code": _string(
            _value(row, "geo_target_constant.country_code", "country_code")
        ),
        "target_type": _string(
            _value(row, "geo_target_constant.target_type", "target_type")
        ),
    }


def enrich_geo_rows(
    rows: list[dict[str, Any]], geo_targets: list[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Attach readable frozen location names while retaining criterion IDs."""

    targets = {
        str(target["criterion_id"]): target
        for target in geo_targets
        if target.get("criterion_id") is not None
    }
    enriched: list[dict[str, Any]] = []
    for source in rows:
        row = dict(source)
        country = targets.get(str(row.get("country_criterion_id")))
        region = targets.get(str(row.get("region_criterion_id")))
        city = targets.get(str(row.get("city_criterion_id")))
        location = city or region or country
        row.update(
            country=country.get("name") if country else None,
            country_code=(location or country or {}).get("country_code"),
            region=region.get("name") if region else None,
            city=city.get("name") if city else None,
            location_name=location.get("name") if location else None,
            location_canonical_name=(location or {}).get("canonical_name"),
            location_target_type=(location or {}).get("target_type"),
            geo_city=city.get("name") if city else None,
            geo_region=region.get("name") if region else None,
        )
        enriched.append(row)
    return enriched


def _criterion_id(value: Any) -> str | None:
    if value in (None, ""):
        return None
    token = str(value).rsplit("/", maxsplit=1)[-1]
    return token if token.isdigit() else None
