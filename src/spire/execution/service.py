# @file Canonical execution lifecycle orchestration.
# @domain execution
# @status stable
# @adr [[0011-canonical-execution-lifecycle]]
# @adr [[0012-exact-human-approval]]
# @adr [[0018-bounded-execution-operation-extension]]
# @tested-by [[test_execution_service.py]]
"""Thin orchestration for the one canonical execution lifecycle."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from spire.core import validate_customer_id, validate_google_ads_id
from spire.truth import AccountSnapshotService

from .authority import AuthorityService, approval_fingerprint
from .compiler import BudgetCompiler
from .contracts import (
    ChangeKind,
    ChangeSpec,
    CompiledOperation,
    ExecutionMode,
    ExecutionRun,
    ExecutionRunState,
)
from .policy import HardPolicyService
from .requests import normalize_keyword, normalize_search_campaign_request
from .runtime import ProductionRuntime, ProviderUnavailableError
from .store import ExecutionStore, new_id, utc_now


class ExecutionRunService:
    def __init__(
        self,
        workspace,
        *,
        snapshots: AccountSnapshotService,
        compiler: BudgetCompiler,
        policy: HardPolicyService,
        authority: AuthorityService,
        runtime: ProductionRuntime,
        store_factory=ExecutionStore,
    ) -> None:
        self.workspace = workspace
        self.snapshots = snapshots
        self.compiler = compiler
        self.policy = policy
        self.authority = authority
        self.runtime = runtime
        self._store_factory = store_factory

    def prepare_change_budget(
        self,
        customer_id: str,
        campaign_id: str,
        daily_budget: object,
        *,
        environment: str = "PRODUCTION",
        provenance: dict | None = None,
    ) -> dict:
        customer_id = validate_customer_id(customer_id)
        campaign_id = validate_google_ads_id(campaign_id, field="campaign_id")
        budget = _normalize_budget(daily_budget)
        return self._prepare(
            customer_id,
            ChangeKind.UPDATE_BUDGET,
            {"campaign_id": campaign_id},
            {"daily_budget": budget},
            environment=environment,
            provenance=provenance,
        )

    def prepare_add_negative_keyword(
        self,
        customer_id: str,
        campaign_id: str,
        text: object,
        match_type: object,
        *,
        ad_group_id: str | None = None,
        environment: str = "PRODUCTION",
        provenance: dict | None = None,
    ) -> dict:
        customer_id = validate_customer_id(customer_id)
        campaign_id = validate_google_ads_id(campaign_id, field="campaign_id")
        keyword = normalize_keyword(text, match_type)
        ad_group = validate_google_ads_id(ad_group_id, field="ad_group_id") if ad_group_id else ""
        return self._prepare(
            customer_id,
            ChangeKind.ADD_NEGATIVE_KEYWORD,
            {"campaign_id": campaign_id},
            {**keyword, "scope": "AD_GROUP" if ad_group else "CAMPAIGN", "ad_group_id": ad_group},
            environment=environment,
            provenance=provenance,
        )

    def prepare_create_search_campaign(
        self,
        customer_id: str,
        request: dict,
        *,
        environment: str = "PRODUCTION",
        provenance: dict | None = None,
    ) -> dict:
        customer_id = validate_customer_id(customer_id)
        normalized = normalize_search_campaign_request(request)
        return self._prepare(
            customer_id,
            ChangeKind.CREATE_SEARCH_CAMPAIGN,
            {"campaign_name": normalized["campaign_name"]},
            normalized,
            environment=environment,
            provenance=provenance,
        )

    def _prepare(
        self,
        customer_id: str,
        kind: ChangeKind,
        target: dict,
        requested_change: dict,
        *,
        environment: str,
        provenance: dict | None,
    ) -> dict:
        mode = ExecutionMode(environment.upper())
        campaign_id = target.get("campaign_id")
        snapshot = self.snapshots.current(customer_id, campaign_ids=(campaign_id,) if campaign_id else None)
        spec = ChangeSpec(
            spec_id=new_id("spec"),
            customer_id=customer_id,
            account_id=customer_id,
            kind=kind,
            target=target,
            requested_change=requested_change,
            snapshot_ref={
                "snapshot_id": snapshot.snapshot_id,
                "content_hash": snapshot.content_hash,
                "extraction_id": snapshot.extraction_id,
                "source": snapshot.source.value,
                "scope": dict(snapshot.scope),
            },
            provenance=provenance or {"producer": "spire.execution"},
        )
        store = self._store_factory(self.workspace, customer_id)
        store.save_spec(spec)
        run = ExecutionRun(
            run_id=new_id("run"),
            spec_id=spec.spec_id,
            customer_id=customer_id,
            account_id=customer_id,
            mode=mode,
            state=ExecutionRunState.DRAFT,
            spec_hash=spec.content_hash,
            snapshot_ref=spec.snapshot_ref,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        store.save_run(run)
        try:
            operation = self.compiler.compile(spec, snapshot)
            run = store.transition(run, ExecutionRunState.DRAFT, compiled_operation=operation.to_dict())
            preview = self.runtime.validate_only(operation)
            run = store.transition(run, ExecutionRunState.DRAFT, preview=preview.to_dict())
            decision = self.policy.evaluate(spec, snapshot, operation, mode=mode)
            run = store.transition(run, ExecutionRunState.DRAFT, policy=decision.to_dict())
            if preview.status != "PASSED":
                return self._failed(store, run, f"VALIDATE_ONLY_REJECTED:{preview.provider_code}")
            if decision.status != "ALLOWED":
                return self._failed(store, run, ";".join(decision.reason_codes))
            run = store.transition(run, ExecutionRunState.VALIDATED)
            run, request = self.authority.request_human_approval(store, run)
        except Exception as exc:
            if run.state not in {ExecutionRunState.FAILED, ExecutionRunState.RECONCILING}:
                run = self._failed_run(store, run, type(exc).__name__ + ":" + str(exc))
            raise
        return self._preparation_response(run, request)

    def approve_human(self, run_id: str, *, customer_id: str, principal_id: str, affirmation: bool) -> dict:
        store = self._store_factory(self.workspace, validate_customer_id(customer_id))
        run = self.authority.approve_human(
            store, run_id, principal_id=principal_id, affirmation=affirmation
        )
        return self._run_response(run)

    def execute_approved(self, run_id: str, *, customer_id: str) -> dict:
        store = self._store_factory(self.workspace, validate_customer_id(customer_id))
        run = store.load_run(run_id)
        if run.state is not ExecutionRunState.APPROVED:
            raise ValueError("RUN_NOT_APPROVED")
        if run.request_sent is not None:
            raise ValueError("REQUEST_ALREADY_SENT")
        if approval_fingerprint(run) != run.approval_fingerprint:
            raise ValueError("APPROVAL_FINGERPRINT_MISMATCH")
        if run.mode is not ExecutionMode.PRODUCTION or run.snapshot_ref.get("source") != "LIVE":
            raise ValueError("RUN_SOURCE_MODE_CHANGED")
        operation = CompiledOperation(**dict(run.compiled_operation or {}))
        if not run.preview or run.preview.get("operation_hash") != operation.content_hash:
            raise ValueError("PREVIEW_OPERATION_MISMATCH")
        run = self.authority.consume(store, run)
        request_record = {
            "operation_hash": operation.content_hash,
            "sent_at": utc_now(),
            "status": "REQUEST_SENT",
        }
        run = store.transition(run, ExecutionRunState.APPLYING, request_sent=request_record)
        try:
            transport = self.runtime.mutate(operation)
        except ProviderUnavailableError as exc:
            run = store.transition(
                run,
                ExecutionRunState.RECONCILING,
                request_sent={**request_record, "transport": "AMBIGUOUS", "error": str(exc)},
                failure_reason=exc.reason_code,
            )
            return self._run_response(run)
        run = store.transition(
            run,
            ExecutionRunState.APPLYING,
            request_sent={**request_record, "transport": transport, "transported_at": utc_now()},
        )
        verification = (
            self.runtime.verify(operation, transport)
            if getattr(self.runtime, "supports_transport_readback", False)
            else self.runtime.verify(operation)
        )
        final_state = ExecutionRunState(verification.status)
        run = store.transition(
            run,
            final_state,
            verification=verification.to_dict(),
            failure_reason=verification.reason_code,
        )
        return self._run_response(run)

    def _failed(self, store: ExecutionStore, run: ExecutionRun, reason: str) -> dict:
        return self._run_response(self._failed_run(store, run, reason))

    @staticmethod
    def _failed_run(store: ExecutionStore, run: ExecutionRun, reason: str) -> ExecutionRun:
        return store.transition(run, ExecutionRunState.FAILED, failure_reason=reason)

    @staticmethod
    def _preparation_response(run: ExecutionRun, request: dict) -> dict:
        response = ExecutionRunService._run_response(run)
        response["approval_request_id"] = request["request_id"]
        response["preview"] = dict(run.preview or {})
        response["fingerprint"] = run.approval_fingerprint
        return response

    @staticmethod
    def _run_response(run: ExecutionRun) -> dict:
        return {
            "run_id": run.run_id,
            "state": run.state.value,
            "customer_id": run.customer_id,
            "account_id": run.account_id,
            "mode": run.mode.value,
            "approval_request_id": run.approval_request_id,
            "fingerprint": run.approval_fingerprint,
            "request_sent": dict(run.request_sent) if run.request_sent else None,
            "verification": dict(run.verification) if run.verification else None,
            "failure_reason": run.failure_reason,
        }


def _normalize_budget(value: object) -> str:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("DAILY_BUDGET_INVALID") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError("DAILY_BUDGET_INVALID")
    normalized = format(amount.normalize(), "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized
