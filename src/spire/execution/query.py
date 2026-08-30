# @file Safe execution-run query projections.
# @domain execution
# @status stable
# @adr [[0011-canonical-execution-lifecycle]]
# @adr [[0016-public-currency-units-and-internal-micros]]
# @tested-by [[test_execution_query.py]]
"""Canonical read-only discovery and safe projection of execution runs."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from spire.core import (
    ArtifactNotFoundError,
    ScopeMismatchError,
    validate_customer_id,
    validate_google_ads_id,
)
from spire.truth import DatasetResolver

from .contracts import AuthoritySource, ChangeKind, ExecutionRun, ExecutionRunState
from .store import ExecutionStore

_TERMINAL_STATES = frozenset({ExecutionRunState.VERIFIED, ExecutionRunState.FAILED})
_ORDER_FIELDS = frozenset({"created_at", "updated_at"})
_DEFAULT_LIMIT = 100
_MAX_LIMIT = 1000


class ExecutionRunQueryService:
    """Own run discovery so public adapters never inspect execution storage."""

    def __init__(
        self,
        workspace,
        *,
        store_factory=ExecutionStore,
        resolver_factory=DatasetResolver,
    ) -> None:
        self.workspace = workspace
        self._store_factory = store_factory
        self._resolver_factory = resolver_factory

    def list_runs(
        self,
        *,
        customer_id: str | None = None,
        campaign_id: str | None = None,
        state: str | ExecutionRunState | None = None,
        order_by: str = "created_at",
        limit: int = _DEFAULT_LIMIT,
    ) -> tuple[dict[str, Any], ...]:
        customer_ids = (
            (validate_customer_id(customer_id),)
            if customer_id is not None
            else self.workspace.customer_ids()
        )
        wanted_campaign = (
            validate_google_ads_id(campaign_id, field="campaign_id")
            if campaign_id is not None
            else None
        )
        wanted_state = _normalize_state(state)
        order_field = _normalize_order(order_by)
        result_limit = _normalize_limit(limit)

        projections: list[dict[str, Any]] = []
        for scoped_customer_id in customer_ids:
            store = self._store_factory(self.workspace, scoped_customer_id)
            for run in store.list_runs():
                projection = self._project(store, run)
                if wanted_campaign and projection.get("campaign_id") != wanted_campaign:
                    continue
                if wanted_state and projection["state"] != wanted_state.value:
                    continue
                projections.append(projection)

        projections.sort(
            key=lambda item: (str(item[order_field]), str(item["run_id"])), reverse=True
        )
        selected = tuple(projections[:result_limit])
        if not selected:
            raise ArtifactNotFoundError("EXECUTION_RUN_NOT_FOUND")
        return selected

    def get_run(self, run_id: str) -> dict[str, Any]:
        store, run = self._find(run_id)
        return self._project(store, run)

    def approval_preview(self, run_id: str) -> dict[str, Any]:
        store, run = self._find(run_id)
        projection = self._project(store, run)
        operation = dict(run.compiled_operation or {})
        return {
            "customer_id": projection["customer_id"],
            "campaign_id": projection.get("campaign_id"),
            "current": projection.get("current_value"),
            "proposed": projection.get("proposed_value"),
            "delta": projection.get("delta_value"),
            "currency": projection.get("currency"),
            "environment": projection["environment"],
            "dry_run": projection["validate_only_result"],
            "policy": projection["policy"],
            "authority": "HUMAN_APPROVAL_REQUIRED",
            "approval_state": projection["approval_state"],
            "state": projection["state"],
            "run_id": projection["run_id"],
            "fingerprint": projection["fingerprint"],
            "operation": {
                "kind": operation.get("kind"),
                "campaign_id": operation.get("campaign_id"),
                "daily_budget_micros": operation.get("daily_budget_micros"),
            },
        }

    def _find(self, run_id: str) -> tuple[ExecutionStore, ExecutionRun]:
        store, run = self._store_factory.find(self.workspace, run_id)
        self._assert_store_scope(store, run)
        return store, run

    def _project(self, store: ExecutionStore, run: ExecutionRun) -> dict[str, Any]:
        self._assert_store_scope(store, run)
        spec = None
        try:
            spec = store.load_spec(run.spec_id)
        except ArtifactNotFoundError:
            pass

        operation = dict(run.compiled_operation or {})
        campaign_id = _campaign_id(spec, operation)
        change_kind = _change_kind(spec, operation)
        summary = self._budget_summary(store, run, spec, campaign_id, change_kind)
        authority = dict(run.authority or {})
        approval_state = _approval_state(run, authority)
        preview_status = str((run.preview or {}).get("status", ""))
        verification_state = str((run.verification or {}).get("status") or "NOT_STARTED")
        return {
            "run_id": run.run_id,
            "customer_id": run.customer_id,
            "campaign_id": campaign_id,
            "change_kind": change_kind,
            "state": run.state.value,
            "created_at": run.created_at,
            "updated_at": run.updated_at,
            "terminal": run.state in _TERMINAL_STATES,
            "approval_required": approval_state == "PENDING",
            "approval_state": approval_state,
            "request_sent": run.request_sent is not None,
            "verification_state": verification_state,
            "environment": run.mode.value,
            "validate_only_result": (
                "REMOTE_VALIDATED" if preview_status == "PASSED" else "NOT_VALIDATED"
            ),
            "preview": dict(run.preview or {}),
            "policy": (run.policy or {}).get("status"),
            "fingerprint": run.approval_fingerprint or None,
            **summary,
        }

    def _budget_summary(
        self,
        store: ExecutionStore,
        run: ExecutionRun,
        spec,
        campaign_id: str | None,
        change_kind: str | None,
    ) -> dict[str, Any]:
        empty = {
            "current_value": None,
            "proposed_value": None,
            "delta_value": None,
            "currency": None,
        }
        if spec is None or campaign_id is None or change_kind != ChangeKind.UPDATE_BUDGET.value:
            return empty
        proposed = _decimal_text(spec.requested_change.get("daily_budget"))
        extraction_id = str(run.snapshot_ref.get("extraction_id", ""))
        if not extraction_id:
            return {**empty, "proposed_value": proposed}
        try:
            dataset = self._resolver_factory(
                self.workspace, store.customer_id
            ).resolve_dataset(extraction_id, "campaigns", campaign_ids=(campaign_id,))
        except (ArtifactNotFoundError, ScopeMismatchError):
            return {**empty, "proposed_value": proposed}
        row = next(
            (item for item in dataset.rows if str(item.get("campaign_id")) == campaign_id),
            None,
        )
        if row is None or row.get("daily_budget") is None:
            return {**empty, "proposed_value": proposed}
        current = _micros_to_units(row["daily_budget"])
        return {
            "current_value": current,
            "proposed_value": proposed,
            "delta_value": _decimal_text(Decimal(proposed) - Decimal(current)),
            "currency": row.get("currency") or None,
        }

    @staticmethod
    def _assert_store_scope(store: ExecutionStore, run: ExecutionRun) -> None:
        if run.customer_id != store.customer_id:
            raise ScopeMismatchError("EXECUTION_RUN_CUSTOMER_MISMATCH")


def _normalize_state(state: str | ExecutionRunState | None) -> ExecutionRunState | None:
    if state is None:
        return None
    try:
        return ExecutionRunState(str(state).upper())
    except ValueError as exc:
        raise ValueError("RUN_STATE_INVALID") from exc


def _normalize_order(order_by: str) -> str:
    normalized = str(order_by).lower()
    if normalized not in _ORDER_FIELDS:
        raise ValueError("RUN_ORDER_INVALID")
    return normalized


def _normalize_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= _MAX_LIMIT:
        raise ValueError("RUN_LIMIT_INVALID")
    return limit


def _campaign_id(spec, operation: dict[str, Any]) -> str | None:
    value = spec.target.get("campaign_id") if spec is not None else operation.get("campaign_id")
    if value in (None, ""):
        return None
    return validate_google_ads_id(str(value), field="campaign_id")


def _change_kind(spec, operation: dict[str, Any]) -> str | None:
    value = spec.kind.value if spec is not None else operation.get("kind")
    if value in (None, ""):
        return None
    return ChangeKind(value).value


def _approval_state(run: ExecutionRun, authority: dict[str, Any]) -> str:
    if authority.get("consumed"):
        return "CONSUMED"
    if authority.get("source") == AuthoritySource.HUMAN_RUN_APPROVAL.value:
        return "APPROVED"
    if run.approval_request_id:
        return "PENDING"
    return "NOT_REQUESTED"


def _micros_to_units(value: Any) -> str:
    return _decimal_text(Decimal(str(value)) / Decimal(1_000_000))


def _decimal_text(value: Any) -> str:
    amount = Decimal(str(value))
    normalized = format(amount.normalize(), "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized
