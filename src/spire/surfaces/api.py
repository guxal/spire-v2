"""Storage-independent public operations shared by CLI and MCP."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from spire.application import Application
from spire.core import validate_customer_id, validate_google_ads_id
from spire.execution.store import ExecutionStore
from spire.google_ads import RefreshSpec
from spire.interfaces import DATASET_SCHEMAS, DateRange, EvidenceQueryRequest
from spire.truth import DatasetResolver


class PublicApi:
    def __init__(self, application: Application) -> None:
        self.application = application

    def accounts_list(self) -> list[dict[str, str]]:
        return self.application.auth.list_accessible_accounts()

    def account_refresh(
        self,
        customer_id: str,
        *,
        campaign_id: str | None = None,
        enabled_only: bool = False,
        date_range: dict[str, str] | DateRange | None = None,
    ) -> dict[str, Any]:
        customer_id = validate_customer_id(customer_id)
        services = self.application.for_customer(customer_id)
        if campaign_id is not None:
            campaign_ids = (validate_google_ads_id(campaign_id, field="campaign_id"),)
        else:
            discovered = services.campaigns.discover(customer_id)
            campaigns = list(discovered.campaigns)
            if enabled_only:
                campaigns = [row for row in campaigns if str(row.get("status", "")).upper() == "ENABLED"]
            campaign_ids = tuple(str(row["campaign_id"]) for row in campaigns)
        if not campaign_ids:
            raise ValueError("NO_CAMPAIGNS_AVAILABLE")
        if date_range is not None and not isinstance(date_range, DateRange):
            date_range = DateRange(**date_range)
        result = services.refresh.refresh(RefreshSpec(customer_id, campaign_ids, date_range))
        return {
            "status": "COMPLETE",
            "customer_id": customer_id,
            "campaign_count": len(campaign_ids),
            "campaign_ids": list(campaign_ids),
            "snapshot": "CURRENT",
            "evidence_ref": result.extraction_id,
        }

    def campaigns_discover(self, customer_id: str) -> dict[str, Any]:
        customer_id = validate_customer_id(customer_id)
        result = self.application.for_customer(customer_id).campaigns.discover(customer_id)
        return {
            "customer_id": customer_id,
            "catalog_id": result.catalog_id,
            "campaigns": [_public_campaign(row) for row in result.campaigns],
        }

    def campaigns_list(self, customer_id: str) -> list[dict[str, Any]]:
        customer_id = validate_customer_id(customer_id)
        return list(self.application.for_customer(customer_id).campaigns.list(customer_id))

    def campaigns_get(self, customer_id: str, campaign_id: str) -> dict[str, Any]:
        customer_id = validate_customer_id(customer_id)
        campaign_id = validate_google_ads_id(campaign_id, field="campaign_id")
        return self.application.for_customer(customer_id).campaigns.get(customer_id, campaign_id)

    def evidence_query(
        self,
        customer_id: str,
        campaign_ids: list[str] | tuple[str, ...],
        dataset: str,
        *,
        date_range: dict[str, str] | DateRange | None = None,
        dimensions: list[str] | tuple[str, ...] = (),
        metrics: list[str] | tuple[str, ...] = (),
        filters: dict[str, Any] | None = None,
        limit: int = 100,
        order_by: str | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        customer_id = validate_customer_id(customer_id)
        request = EvidenceQueryRequest(
            customer_id=customer_id,
            campaign_ids=tuple(campaign_ids),
            dataset=dataset,
            date_range=date_range,
            dimensions=tuple(dimensions),
            metrics=tuple(metrics),
            filters=filters or {},
            limit=limit,
            order_by=order_by,
        )
        return self.application.for_customer(customer_id).evidence.query(request)

    def evidence_datasets(self, customer_id: str, campaign_id: str) -> dict[str, Any]:
        customer_id = validate_customer_id(customer_id)
        campaign_id = validate_google_ads_id(campaign_id, field="campaign_id")
        snapshot = self.application.for_customer(customer_id).evidence.snapshots.current(
            customer_id, campaign_ids=(campaign_id,)
        )
        return {
            "customer_id": customer_id,
            "campaign_id": campaign_id,
            "snapshot": "CURRENT",
            "datasets": [
                {
                    "dataset": name,
                    "state": snapshot.coverage.get(name, "NOT_REQUESTED").value
                    if hasattr(snapshot.coverage.get(name, "NOT_REQUESTED"), "value")
                    else str(snapshot.coverage.get(name, "NOT_REQUESTED")),
                }
                for name in DATASET_SCHEMAS
                if name in snapshot.coverage
            ],
        }

    def change_budget(
        self,
        customer_id: str,
        campaign_id: str,
        daily_budget: object,
        *,
        environment: str = "production",
    ) -> dict[str, Any]:
        customer_id = validate_customer_id(customer_id)
        campaign_id = validate_google_ads_id(campaign_id, field="campaign_id")
        prepared = self.application.for_customer(customer_id).execution.prepare_change_budget(
            customer_id,
            campaign_id,
            daily_budget,
            environment=environment,
        )
        return {**prepared, **self.run_approval_preview(prepared["run_id"])}

    def run_get(self, run_id: str) -> dict[str, Any]:
        store, run = ExecutionStore.find(self.application.workspace, run_id)
        payload = run.to_dict()
        compiled = dict(payload.get("compiled_operation") or {})
        compiled.pop("budget_resource_name", None)
        payload["compiled_operation"] = compiled or None
        payload["customer_id"] = store.customer_id
        return payload

    def run_approval_preview(self, run_id: str) -> dict[str, Any]:
        store, run = ExecutionStore.find(self.application.workspace, run_id)
        spec = store.load_spec(run.spec_id)
        operation = dict(run.compiled_operation or {})
        resolver = DatasetResolver(self.application.workspace, store.customer_id)
        dataset = resolver.resolve_dataset(
            str(run.snapshot_ref["extraction_id"]),
            "campaigns",
            campaign_ids=(str(spec.target["campaign_id"]),),
        )
        current_micros = next(
            (
                int(row["daily_budget"])
                for row in dataset.rows
                if str(row.get("campaign_id")) == str(spec.target["campaign_id"])
                and row.get("daily_budget") is not None
            ),
            None,
        )
        proposed = str(spec.requested_change["daily_budget"])
        current = _currency_units(current_micros)
        return {
            "customer_id": store.customer_id,
            "campaign_id": str(spec.target["campaign_id"]),
            "current": current,
            "proposed": proposed,
            "delta": _subtract_currency(proposed, current),
            "environment": run.mode.value,
            "dry_run": "REMOTE_VALIDATED" if (run.preview or {}).get("status") == "PASSED" else "NOT_VALIDATED",
            "policy": (run.policy or {}).get("status"),
            "authority": "HUMAN_APPROVAL_REQUIRED",
            "run_id": run.run_id,
            "fingerprint": run.approval_fingerprint,
            "operation": {
                "kind": operation.get("kind"),
                "campaign_id": operation.get("campaign_id"),
                "daily_budget_micros": operation.get("daily_budget_micros"),
            },
        }

    def run_approve(self, run_id: str, *, principal_id: str) -> dict[str, Any]:
        store, _run = ExecutionStore.find(self.application.workspace, run_id)
        return self.application.for_customer(store.customer_id).execution.approve_human(
            run_id,
            customer_id=store.customer_id,
            principal_id=principal_id,
            affirmation=True,
        )

    def run_resume(self, run_id: str) -> dict[str, Any]:
        store, _ = ExecutionStore.find(self.application.workspace, run_id)
        return self.application.for_customer(store.customer_id).execution.execute_approved(
            run_id,
            customer_id=store.customer_id,
        )


def _public_campaign(row: dict[str, Any]) -> dict[str, Any]:
    amount = row.get("daily_budget")
    return {
        "campaign_id": row.get("campaign_id"),
        "name": row.get("name", ""),
        "status": row.get("status"),
        "serving_status": row.get("serving_status"),
        "channel": row.get("channel"),
        "daily_budget": _currency_units(amount),
        "currency": row.get("currency"),
    }


def _currency_units(micros: Any) -> int | float | None:
    if micros in (None, ""):
        return None
    amount = Decimal(str(micros)) / Decimal(1_000_000)
    return int(amount) if amount == amount.to_integral_value() else float(amount)


def _subtract_currency(proposed: str, current: float | None) -> int | float | None:
    if current is None:
        return None
    value = Decimal(proposed) - Decimal(str(current))
    return int(value) if value == value.to_integral_value() else float(value)
