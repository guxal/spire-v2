# @file Typed public requests for bounded execution operations.
# @domain execution
# @status stable
# @adr [[0018-bounded-execution-operation-extension]]
# @tested-by [[test_execution_requests.py]]
"""Business-level request validation for supported execution operations."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

from spire.core import validate_google_ads_id

MATCH_TYPES = {"EXACT", "PHRASE", "BROAD"}
SUPPORTED_BIDDING_STRATEGIES = {"MAXIMIZE_CONVERSIONS", "MAXIMIZE_CLICKS"}


def normalize_keyword(text: object, match_type: object) -> dict[str, str]:
    value = " ".join(str(text or "").split())
    normalized_match_type = str(match_type or "").upper()
    if not value or normalized_match_type not in MATCH_TYPES:
        raise ValueError("KEYWORD_INPUT_INVALID")
    return {"text": value, "match_type": normalized_match_type}


def normalize_search_campaign_request(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("SEARCH_CAMPAIGN_REQUEST_INVALID")
    campaign_name = " ".join(str(value.get("campaign_name") or "").split())
    if not campaign_name:
        raise ValueError("CAMPAIGN_NAME_INVALID")
    daily_budget = _decimal_text(value.get("daily_budget"))
    strategy = str(value.get("bidding_strategy") or "MAXIMIZE_CONVERSIONS").upper()
    if strategy not in SUPPORTED_BIDDING_STRATEGIES:
        raise ValueError("BIDDING_STRATEGY_UNSUPPORTED")
    geo_target_ids = _ids(value.get("geo_target_ids"), field="geo_target_id")
    language_criterion_ids = _ids(value.get("language_criterion_ids"), field="language_criterion_id")
    if not geo_target_ids or not language_criterion_ids:
        raise ValueError("SEARCH_CAMPAIGN_TARGETING_REQUIRED")
    groups = tuple(_ad_group(item) for item in value.get("ad_groups") or ())
    if not groups:
        raise ValueError("SEARCH_CAMPAIGN_AD_GROUPS_REQUIRED")
    return {
        "campaign_name": campaign_name,
        "daily_budget": daily_budget,
        "bidding_strategy": strategy,
        "geo_target_ids": geo_target_ids,
        "language_criterion_ids": language_criterion_ids,
        "ad_groups": groups,
    }


def _ad_group(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("SEARCH_AD_GROUP_INVALID")
    name = " ".join(str(value.get("name") or "").split())
    if not name:
        raise ValueError("SEARCH_AD_GROUP_NAME_INVALID")
    keywords = tuple(
        normalize_keyword(item.get("text"), item.get("match_type"))
        for item in value.get("keywords") or ()
        if isinstance(item, Mapping)
    )
    if not keywords:
        raise ValueError("SEARCH_AD_GROUP_KEYWORDS_REQUIRED")
    headlines = tuple(" ".join(str(item).split()) for item in value.get("headlines") or () if str(item).strip())
    descriptions = tuple(" ".join(str(item).split()) for item in value.get("descriptions") or () if str(item).strip())
    if not 3 <= len(headlines) <= 15 or not 2 <= len(descriptions) <= 4:
        raise ValueError("RSA_ASSET_COUNT_INVALID")
    if any(len(item) > 30 for item in headlines) or any(len(item) > 90 for item in descriptions):
        raise ValueError("RSA_ASSET_LENGTH_INVALID")
    final_url = str(value.get("final_url") or "").strip()
    parsed = urlparse(final_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("RSA_FINAL_URL_INVALID")
    return {
        "name": name,
        "keywords": keywords,
        "headlines": headlines,
        "descriptions": descriptions,
        "final_url": final_url,
    }


def _ids(value: object, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError("SEARCH_CAMPAIGN_TARGETING_REQUIRED")
    return tuple(sorted({validate_google_ads_id(str(item), field=field) for item in value}, key=int))


def _decimal_text(value: object) -> str:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("DAILY_BUDGET_INVALID") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError("DAILY_BUDGET_INVALID")
    normalized = format(amount.normalize(), "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized
