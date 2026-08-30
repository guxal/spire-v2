# @file Google Ads execution transport and semantic read-back.
# @domain execution
# @status stable
# @adr [[0013-provider-boundary-and-semantic-verification]]
# @adr [[0018-bounded-execution-operation-extension]]
# @tested-by [[test_execution_runtime.py]]
"""Google Ads transport and semantic read-back adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .contracts import CompiledOperation, PreviewResult, VerificationResult


class ProviderUnavailableError(RuntimeError):
    reason_code = "GOOGLE_ADS_PROVIDER_UNAVAILABLE"


class GoogleAdsGateway:
    def __init__(self, client_provider) -> None:
        self.client_provider = client_provider

    def validate_only(self, operation: CompiledOperation) -> PreviewResult:
        try:
            self._mutate(operation, validate_only=True)
        except Exception as exc:  # noqa: BLE001 - provider boundary normalizes failures
            return PreviewResult(
                status="REJECTED",
                operation_hash=operation.content_hash,
                observed_at=_now(),
                provider_code=type(exc).__name__,
                message=str(exc),
            )
        return PreviewResult("PASSED", operation.content_hash, _now())

    def mutate(self, operation: CompiledOperation) -> dict[str, Any]:
        try:
            response = self._mutate(operation, validate_only=False)
        except Exception as exc:
            raise ProviderUnavailableError(str(exc)) from exc
        return {
            "status": "SENT",
            "provider_response_type": type(response).__name__,
            "resource_names": _response_resource_names(response),
        }

    def _service(self):
        return self.client_provider.get_client().get_service("GoogleAdsService")

    def _mutate(self, operation: CompiledOperation, *, validate_only: bool):
        client = self.client_provider.get_client()
        request = client.get_type("MutateGoogleAdsRequest")
        request.customer_id = operation.customer_id
        request.mutate_operations.extend(self._api_operations(operation))
        request.partial_failure = False
        request.validate_only = validate_only
        return self._service().mutate(request=request)

    def _api_operations(self, operation: CompiledOperation) -> list[Any]:
        client = self.client_provider.get_client()
        if operation.kind.value == "UPDATE_BUDGET":
            api_operation = client.get_type("MutateOperation")
            budget_operation = api_operation.campaign_budget_operation
            update = budget_operation.update
            update.resource_name = operation.budget_resource_name
            update.amount_micros = operation.daily_budget_micros
            budget_operation.update_mask.paths.append("amount_micros")
            return [api_operation]
        if operation.kind.value == "ADD_NEGATIVE_KEYWORD":
            return [_negative_keyword_operation(client, operation)]
        if operation.kind.value == "CREATE_SEARCH_CAMPAIGN":
            return _search_campaign_operations(client, operation)
        raise ValueError("UNSUPPORTED_CHANGE_KIND")


class SemanticReadBack:
    def __init__(self, client_provider) -> None:
        self.client_provider = client_provider

    def verify(self, operation: CompiledOperation, transport: dict[str, Any] | None = None) -> VerificationResult:
        if operation.kind.value == "UPDATE_BUDGET":
            return self.verify_budget(operation)
        if operation.kind.value == "ADD_NEGATIVE_KEYWORD":
            return self.verify_negative_keyword(operation)
        if operation.kind.value == "CREATE_SEARCH_CAMPAIGN":
            return self.verify_search_campaign(operation, transport or {})
        raise ValueError("UNSUPPORTED_CHANGE_KIND")

    def verify_budget(self, operation: CompiledOperation) -> VerificationResult:
        query = (
            "SELECT campaign.id, campaign_budget.amount_micros "
            f"FROM campaign WHERE campaign.id = {operation.campaign_id}"
        )
        try:
            rows = []
            service = self.client_provider.get_client().get_service("GoogleAdsService")
            for batch in service.search_stream(customer_id=operation.customer_id, query=query):
                rows.extend(batch.results)
        except Exception as exc:  # noqa: BLE001 - post-send uncertainty is reconciliation
            return VerificationResult(
                "RECONCILING",
                {"daily_budget_micros": operation.daily_budget_micros},
                {},
                _now(),
                type(exc).__name__,
            )
        observed = _find_budget(rows, operation.campaign_id)
        if observed is None:
            return VerificationResult(
                "RECONCILING",
                {"daily_budget_micros": operation.daily_budget_micros},
                {},
                _now(),
                "READ_BACK_MISSING",
            )
        result = {"campaign_id": operation.campaign_id, "daily_budget_micros": observed}
        status = "VERIFIED" if observed == operation.daily_budget_micros else "FAILED"
        return VerificationResult(
            status,
            {"daily_budget_micros": operation.daily_budget_micros},
            result,
            _now(),
            "" if status == "VERIFIED" else "BUDGET_MISMATCH",
        )

    def verify_negative_keyword(self, operation: CompiledOperation) -> VerificationResult:
        payload = operation.payload
        scope = str(payload["scope"])
        resource = "ad_group_criterion" if scope == "AD_GROUP" else "campaign_criterion"
        source = "ad_group_criterion" if scope == "AD_GROUP" else "campaign_criterion"
        where = f"campaign.id = {operation.campaign_id}"
        if scope == "AD_GROUP":
            where += f" AND ad_group.id = {payload['ad_group_id']}"
        query = (
            f"SELECT {resource}.keyword.text, {resource}.keyword.match_type, {resource}.negative "
            f"FROM {source} WHERE {where} AND {resource}.negative = TRUE"
        )
        expected = {"campaign_id": operation.campaign_id, "scope": scope, "text": payload["text"], "match_type": payload["match_type"]}
        try:
            rows = _search_rows(self.client_provider, operation.customer_id, query)
        except Exception as exc:  # noqa: BLE001
            return VerificationResult("RECONCILING", expected, {}, _now(), type(exc).__name__)
        for row in rows:
            if (
                _normal_text(_value(row, f"{resource}.keyword.text", "text")) == _normal_text(payload["text"])
                and str(_enum_name(_value(row, f"{resource}.keyword.match_type", "match_type"))) == str(payload["match_type"])
                and bool(_value(row, f"{resource}.negative", "negative"))
            ):
                return VerificationResult("VERIFIED", expected, expected, _now())
        return VerificationResult("FAILED", expected, {}, _now(), "NEGATIVE_KEYWORD_MISSING")

    def verify_search_campaign(self, operation: CompiledOperation, transport: dict[str, Any]) -> VerificationResult:
        campaign_id = _campaign_id_from_transport(transport)
        expected = {"campaign_name": operation.payload["campaign_name"], "daily_budget_micros": operation.daily_budget_micros, "status": "PAUSED"}
        if not campaign_id:
            return VerificationResult("RECONCILING", expected, {}, _now(), "CREATE_CAMPAIGN_ID_MISSING")
        query = (
            "SELECT campaign.id, campaign.name, campaign.status, campaign.campaign_budget, "
            "campaign_budget.amount_micros FROM campaign "
            f"WHERE campaign.id = {campaign_id}"
        )
        try:
            rows = _search_rows(self.client_provider, operation.customer_id, query)
        except Exception as exc:  # noqa: BLE001
            return VerificationResult("RECONCILING", expected, {}, _now(), type(exc).__name__)
        if len(rows) != 1:
            return VerificationResult("RECONCILING", expected, {"campaign_id": campaign_id}, _now(), "CREATED_CAMPAIGN_MISSING")
        row = rows[0]
        observed = {
            "campaign_id": campaign_id,
            "campaign_name": _value(row, "campaign.name", "name"),
            "status": _enum_name(_value(row, "campaign.status", "status")),
            "daily_budget_micros": _value(row, "campaign_budget.amount_micros", "amount_micros"),
        }
        if observed["campaign_name"] != expected["campaign_name"] or observed["status"] != "PAUSED" or int(observed["daily_budget_micros"] or 0) != operation.daily_budget_micros:
            return VerificationResult("FAILED", expected, observed, _now(), "SEARCH_CAMPAIGN_CORE_MISMATCH")
        if not _verify_campaign_children(self.client_provider, operation.customer_id, campaign_id, operation.payload):
            return VerificationResult("FAILED", expected, observed, _now(), "SEARCH_CAMPAIGN_CHILDREN_MISMATCH")
        return VerificationResult("VERIFIED", expected, observed, _now())


class ProductionRuntime:
    supports_transport_readback = True

    def __init__(self, client_provider, *, gateway=None, read_back=None) -> None:
        self.client_provider = client_provider
        self.gateway = gateway or GoogleAdsGateway(client_provider)
        self.read_back = read_back or SemanticReadBack(client_provider)

    def validate_only(self, operation: CompiledOperation) -> PreviewResult:
        return self.gateway.validate_only(operation)

    def mutate(self, operation: CompiledOperation) -> dict[str, Any]:
        return self.gateway.mutate(operation)

    def verify(self, operation: CompiledOperation, transport: dict[str, Any] | None = None) -> VerificationResult:
        return self.read_back.verify(operation, transport)


def _find_budget(rows: list[Any], campaign_id: str) -> int | None:
    for row in rows:
        value = _value(row, "campaign.id", "id")
        if value is not None and str(value) != campaign_id:
            continue
        budget = _value(row, "campaign_budget.amount_micros", "amount_micros", "daily_budget")
        if budget not in (None, ""):
            return int(budget)
    return None


def _negative_keyword_operation(client: Any, operation: CompiledOperation) -> Any:
    api_operation = client.get_type("MutateOperation")
    payload = operation.payload
    if payload["scope"] == "AD_GROUP":
        create = api_operation.ad_group_criterion_operation.create
        create.ad_group = f"customers/{operation.customer_id}/adGroups/{payload['ad_group_id']}"
    else:
        create = api_operation.campaign_criterion_operation.create
        create.campaign = f"customers/{operation.customer_id}/campaigns/{operation.campaign_id}"
    create.negative = True
    create.keyword.text = str(payload["text"])
    create.keyword.match_type = getattr(client.enums.KeywordMatchTypeEnum, str(payload["match_type"]))
    return api_operation


def _search_campaign_operations(client: Any, operation: CompiledOperation) -> list[Any]:
    payload = operation.payload
    result: list[Any] = []
    budget = client.get_type("MutateOperation")
    budget_create = budget.campaign_budget_operation.create
    budget_create.resource_name = payload["budget_resource_name"]
    budget_create.amount_micros = operation.daily_budget_micros
    budget_create.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
    result.append(budget)

    campaign = client.get_type("MutateOperation")
    create = campaign.campaign_operation.create
    create.resource_name = payload["campaign_resource_name"]
    create.name = payload["campaign_name"]
    create.status = client.enums.CampaignStatusEnum.PAUSED
    create.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.SEARCH
    create.campaign_budget = payload["budget_resource_name"]
    create.network_settings.target_google_search = True
    create.network_settings.target_search_network = False
    create.network_settings.target_content_network = False
    create.network_settings.target_partner_search_network = False
    if payload["bidding_strategy"] == "MAXIMIZE_CONVERSIONS":
        create.maximize_conversions = {}
    else:
        create.target_spend = {}
    result.append(campaign)

    for target_id in payload["geo_target_ids"]:
        criterion = client.get_type("MutateOperation")
        item = criterion.campaign_criterion_operation.create
        item.campaign = payload["campaign_resource_name"]
        item.location.geo_target_constant = f"geoTargetConstants/{target_id}"
        result.append(criterion)
    for language_id in payload["language_criterion_ids"]:
        criterion = client.get_type("MutateOperation")
        item = criterion.campaign_criterion_operation.create
        item.campaign = payload["campaign_resource_name"]
        item.language.language_constant = f"languageConstants/{language_id}"
        result.append(criterion)
    for index, group in enumerate(payload["ad_groups"], start=3):
        group_resource = f"customers/{operation.customer_id}/adGroups/-{index}"
        group_operation = client.get_type("MutateOperation")
        group_create = group_operation.ad_group_operation.create
        group_create.resource_name = group_resource
        group_create.campaign = payload["campaign_resource_name"]
        group_create.name = group["name"]
        group_create.status = client.enums.AdGroupStatusEnum.ENABLED
        group_create.type_ = client.enums.AdGroupTypeEnum.SEARCH_STANDARD
        result.append(group_operation)
        for keyword in group["keywords"]:
            keyword_operation = client.get_type("MutateOperation")
            keyword_create = keyword_operation.ad_group_criterion_operation.create
            keyword_create.ad_group = group_resource
            keyword_create.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
            keyword_create.keyword.text = keyword["text"]
            keyword_create.keyword.match_type = getattr(client.enums.KeywordMatchTypeEnum, keyword["match_type"])
            result.append(keyword_operation)
        ad_operation = client.get_type("MutateOperation")
        ad_create = ad_operation.ad_group_ad_operation.create
        ad_create.ad_group = group_resource
        ad_create.status = client.enums.AdGroupAdStatusEnum.ENABLED
        ad_create.ad.final_urls.append(group["final_url"])
        for text in group["headlines"]:
            asset = client.get_type("AdTextAsset")
            asset.text = text
            ad_create.ad.responsive_search_ad.headlines.append(asset)
        for text in group["descriptions"]:
            asset = client.get_type("AdTextAsset")
            asset.text = text
            ad_create.ad.responsive_search_ad.descriptions.append(asset)
        result.append(ad_operation)
    return result


def _search_rows(provider: Any, customer_id: str, query: str) -> list[Any]:
    rows: list[Any] = []
    service = provider.get_client().get_service("GoogleAdsService")
    for batch in service.search_stream(customer_id=customer_id, query=query):
        rows.extend(batch.results)
    return rows


def _response_resource_names(response: Any) -> list[str]:
    result: list[str] = []
    for item in getattr(response, "mutate_operation_responses", ()):
        kind = getattr(getattr(item, "_pb", None), "WhichOneof", lambda _: None)("response")
        if kind:
            value = str(getattr(getattr(item, kind), "resource_name", ""))
            if value:
                result.append(value)
    return result


def _campaign_id_from_transport(transport: dict[str, Any]) -> str:
    for resource_name in transport.get("resource_names") or ():
        parts = str(resource_name).rstrip("/").split("/")
        if len(parts) >= 2 and parts[-2] == "campaigns" and parts[-1].isdigit():
            return parts[-1]
    return ""


def _verify_campaign_children(provider: Any, customer_id: str, campaign_id: str, payload: Any) -> bool:
    targeting = _search_rows(
        provider,
        customer_id,
        "SELECT campaign_criterion.location.geo_target_constant, "
        "campaign_criterion.language.language_constant "
        f"FROM campaign_criterion WHERE campaign.id = {campaign_id}",
    )
    locations = {
        str(_value(row, "campaign_criterion.location.geo_target_constant", "geo_target_constant") or "")
        for row in targeting
    }
    languages = {
        str(_value(row, "campaign_criterion.language.language_constant", "language_constant") or "")
        for row in targeting
    }
    if not all(f"geoTargetConstants/{value}" in locations for value in payload["geo_target_ids"]):
        return False
    if not all(f"languageConstants/{value}" in languages for value in payload["language_criterion_ids"]):
        return False
    groups = _search_rows(
        provider,
        customer_id,
        f"SELECT ad_group.name FROM ad_group WHERE campaign.id = {campaign_id} AND ad_group.status != 'REMOVED'",
    )
    names = {_value(row, "ad_group.name", "name") for row in groups}
    if any(group["name"] not in names for group in payload["ad_groups"]):
        return False
    criteria = _search_rows(
        provider,
        customer_id,
        f"SELECT ad_group_criterion.keyword.text FROM ad_group_criterion WHERE campaign.id = {campaign_id} AND ad_group_criterion.status != 'REMOVED'",
    )
    keywords = {_normal_text(_value(row, "ad_group_criterion.keyword.text", "keyword_text", "text")) for row in criteria}
    if any(_normal_text(keyword["text"]) not in keywords for group in payload["ad_groups"] for keyword in group["keywords"]):
        return False
    ads = _search_rows(
        provider,
        customer_id,
        f"SELECT ad_group_ad.ad.final_urls FROM ad_group_ad WHERE campaign.id = {campaign_id} AND ad_group_ad.status != 'REMOVED'",
    )
    urls = {url for row in ads for url in (_value(row, "ad_group_ad.ad.final_urls", "final_urls") or ())}
    return all(group["final_url"] in urls for group in payload["ad_groups"])


def _normal_text(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _enum_name(value: Any) -> str | None:
    return getattr(value, "name", value)


def _value(row: Any, *names: str) -> Any:
    for name in names:
        if isinstance(row, dict) and name in row:
            return row[name]
        current = row
        try:
            for part in name.split("."):
                current = current[part] if isinstance(current, dict) else getattr(current, part)
            return current
        except (AttributeError, KeyError, TypeError):
            continue
    return None


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
