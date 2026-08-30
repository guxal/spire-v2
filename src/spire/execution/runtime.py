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
            self._service().mutate(
                customer_id=operation.customer_id,
                operations=[self._api_operation(operation)],
                validate_only=True,
            )
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
            response = self._service().mutate(
                customer_id=operation.customer_id,
                operations=[self._api_operation(operation)],
                validate_only=False,
            )
        except Exception as exc:
            raise ProviderUnavailableError(str(exc)) from exc
        return {"status": "SENT", "provider_response_type": type(response).__name__}

    def _service(self):
        return self.client_provider.get_client().get_service("GoogleAdsService")

    def _api_operation(self, operation: CompiledOperation):
        client = self.client_provider.get_client()
        api_operation = client.get_type("MutateOperation")
        budget_operation = api_operation.campaign_budget_operation
        update = budget_operation.update
        update.resource_name = operation.budget_resource_name
        update.amount_micros = operation.daily_budget_micros
        update_mask = getattr(budget_operation, "update_mask", None)
        if update_mask is None:  # minimal test doubles may expose it on the update resource
            update_mask = update.update_mask
        update_mask.paths.append("amount_micros")
        return api_operation


class SemanticReadBack:
    def __init__(self, client_provider) -> None:
        self.client_provider = client_provider

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


class ProductionRuntime:
    def __init__(self, client_provider, *, gateway=None, read_back=None) -> None:
        self.client_provider = client_provider
        self.gateway = gateway or GoogleAdsGateway(client_provider)
        self.read_back = read_back or SemanticReadBack(client_provider)

    def validate_only(self, operation: CompiledOperation) -> PreviewResult:
        return self.gateway.validate_only(operation)

    def mutate(self, operation: CompiledOperation) -> dict[str, Any]:
        return self.gateway.mutate(operation)

    def verify(self, operation: CompiledOperation) -> VerificationResult:
        return self.read_back.verify_budget(operation)


def _find_budget(rows: list[Any], campaign_id: str) -> int | None:
    for row in rows:
        value = _value(row, "campaign.id", "id")
        if value is not None and str(value) != campaign_id:
            continue
        budget = _value(row, "campaign_budget.amount_micros", "amount_micros", "daily_budget")
        if budget not in (None, ""):
            return int(budget)
    return None


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
