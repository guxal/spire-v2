# @file Live Google Ads geo-target suggestions.
# @domain google-ads
# @status stable
# @adr [[0007-google-ads-provider-ownership]]
# @adr [[0009-capability-projection]]
# @tested-by [[test_geo_targets.py]]
"""Read-only Google Ads geo-target resolution."""

from __future__ import annotations

from typing import Any

from .provider import GoogleAdsClientProvider


class GeoTargetSuggestionService:
    """Resolve human-readable locations through Google's live suggestion API."""

    def __init__(self, provider: GoogleAdsClientProvider) -> None:
        self.provider = provider

    def suggest(
        self,
        names: list[str] | tuple[str, ...],
        *,
        country_code: str,
        locale: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        location_names = _location_names(names)
        normalized_country = _country_code(country_code)
        normalized_locale = _locale(locale)
        lookup_names = _lookup_names(location_names, locale=normalized_locale)
        client = self.provider.get_client()
        request = client.get_type("SuggestGeoTargetConstantsRequest")
        request.location_names.names.extend(lookup_names)
        request.country_code = normalized_country
        if normalized_locale is not None:
            request.locale = normalized_locale
        service = client.get_service("GeoTargetConstantService")
        response = service.suggest_geo_target_constants(request=request)
        return {
            "geo_targets": [
                _public_suggestion(suggestion)
                for suggestion in response.geo_target_constant_suggestions
            ]
        }


def _location_names(names: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(str(name).strip() for name in names if str(name).strip())
    if not normalized:
        raise ValueError("GEO_TARGET_NAMES_REQUIRED")
    return normalized


def _country_code(value: str) -> str:
    normalized = str(value).strip().upper()
    if len(normalized) != 2 or not normalized.isalpha():
        raise ValueError("INVALID_COUNTRY_CODE")
    return normalized


def _locale(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("INVALID_LOCALE")
    return normalized


def _lookup_names(names: tuple[str, ...], *, locale: str | None) -> tuple[str, ...]:
    """Remove a Spanish generic city qualifier before the Google lookup.

    This only normalizes the search query; Google remains authoritative for
    every returned criterion and target type.
    """

    if locale is None or locale.lower().split("-", maxsplit=1)[0] != "es":
        return names
    suffix = " ciudad"
    return tuple(
        name[: -len(suffix)].strip()
        if name.casefold().endswith(suffix) and name[: -len(suffix)].strip()
        else name
        for name in names
    )


def _public_suggestion(suggestion: Any) -> dict[str, Any]:
    target = suggestion.geo_target_constant
    return {
        "id": str(target.id),
        "resource_name": str(target.resource_name),
        "name": str(target.name),
        "canonical_name": str(target.canonical_name),
        "country_code": str(target.country_code),
        "target_type": str(target.target_type),
        "status": str(getattr(target.status, "name", target.status)).split(".")[-1],
        "search_term": str(suggestion.search_term),
        "reach": int(suggestion.reach),
    }
