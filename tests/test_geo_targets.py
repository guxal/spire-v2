from __future__ import annotations

from types import SimpleNamespace

import pytest

from spire.application import Application
from spire.core import WorkspacePaths
from spire.google_ads.geo_targets import GeoTargetSuggestionService
from spire.surfaces import PublicApi


def _suggestion(
    criterion_id: int,
    name: str,
    canonical_name: str,
    *,
    country_code: str = "ES",
    target_type: str = "City",
    status: str = "ENABLED",
    search_term: str = "Pamplona",
    reach: int = 123,
):
    return SimpleNamespace(
        search_term=search_term,
        reach=reach,
        geo_target_constant=SimpleNamespace(
            id=criterion_id,
            resource_name=f"geoTargetConstants/{criterion_id}",
            name=name,
            canonical_name=canonical_name,
            country_code=country_code,
            target_type=target_type,
            status=SimpleNamespace(name=status),
        ),
    )


class _GeoService:
    def __init__(self, suggestions):
        self.suggestions = suggestions
        self.requests = []

    def suggest_geo_target_constants(self, *, request):
        self.requests.append(request)
        return SimpleNamespace(geo_target_constant_suggestions=self.suggestions)


class _GeoClient:
    def __init__(self, service):
        self.service = service
        self.request = SimpleNamespace(
            location_names=SimpleNamespace(names=[]), country_code="", locale=""
        )

    def get_type(self, name):
        assert name == "SuggestGeoTargetConstantsRequest"
        return self.request

    def get_service(self, name):
        assert name == "GeoTargetConstantService"
        return self.service


class _GeoProvider:
    def __init__(self, client):
        self.client = client

    def get_client(self):
        return self.client


def test_geo_target_suggestions_preserve_google_fields_and_request_scope():
    service = _GeoService([_suggestion(100, "Pamplona", "Pamplona, Comunidad Foral de Navarra, Spain")])
    client = _GeoClient(service)

    result = GeoTargetSuggestionService(_GeoProvider(client)).suggest(
        ["Pamplona"], country_code="es", locale="es"
    )

    assert service.requests == [client.request]
    assert client.request.location_names.names == ["Pamplona"]
    assert client.request.country_code == "ES"
    assert client.request.locale == "es"
    assert result == {
        "geo_targets": [
            {
                "id": "100",
                "resource_name": "geoTargetConstants/100",
                "name": "Pamplona",
                "canonical_name": "Pamplona, Comunidad Foral de Navarra, Spain",
                "country_code": "ES",
                "target_type": "City",
                "status": "ENABLED",
                "search_term": "Pamplona",
                "reach": 123,
            }
        ]
    }


def test_geo_target_suggestions_preserve_multiple_candidates_and_allow_no_match():
    service = _GeoService(
        [
            _suggestion(100, "Pamplona", "Pamplona, Spain"),
            _suggestion(200, "Pamplona", "Pamplona, Colombia", country_code="CO"),
        ]
    )
    resolver = GeoTargetSuggestionService(_GeoProvider(_GeoClient(service)))

    assert [target["id"] for target in resolver.suggest(["Pamplona"], country_code="ES")["geo_targets"]] == [
        "100",
        "200",
    ]
    service.suggestions = []
    assert resolver.suggest(["Unknown"], country_code="ES") == {"geo_targets": []}


def test_geo_target_suggestions_reject_invalid_location_parameters_before_provider_access():
    provider = _GeoProvider(_GeoClient(_GeoService([])))
    resolver = GeoTargetSuggestionService(provider)

    with pytest.raises(ValueError, match="GEO_TARGET_NAMES_REQUIRED"):
        resolver.suggest([], country_code="ES")
    with pytest.raises(ValueError, match="INVALID_COUNTRY_CODE"):
        resolver.suggest(["Pamplona"], country_code="Spain")
    with pytest.raises(ValueError, match="INVALID_LOCALE"):
        resolver.suggest(["Pamplona"], country_code="ES", locale=" ")


def test_public_api_projects_geo_target_suggestions_without_mutation(tmp_path):
    service = _GeoService([_suggestion(100, "Pamplona", "Pamplona, Spain")])
    provider = _GeoProvider(_GeoClient(service))
    api = PublicApi(Application(WorkspacePaths(tmp_path), provider_factory=lambda *_: provider))

    result = api.geo_targets_suggest("1234567890", ["Pamplona"], "ES", locale="es")

    assert result["geo_targets"][0]["id"] == "100"
    assert not list(tmp_path.iterdir())
