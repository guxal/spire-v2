# @file Exact human approval authority.
# @domain execution
# @status stable
# @adr [[0012-exact-human-approval]]
# @tested-by [[test_execution_authority.py]]
"""Exact, single-use authority for one prepared execution run."""

from __future__ import annotations

from spire.core import canonical_hash

from .contracts import AuthorityCoverage, AuthoritySource, ExecutionRun, ExecutionRunState
from .store import ExecutionStore, new_id, utc_now


def approval_fingerprint(run: ExecutionRun) -> str:
    return canonical_hash(
        {
            "run_id": run.run_id,
            "customer_id": run.customer_id,
            "account_id": run.account_id,
            "mode": run.mode.value,
            "spec_hash": run.spec_hash,
            "snapshot_ref": dict(run.snapshot_ref),
            "compiled_hash": (run.compiled_operation or {}).get("content_hash", ""),
            "preview_hash": (run.preview or {}).get("operation_hash", ""),
        }
    )


class AuthorityService:
    def coverage(self, run: ExecutionRun) -> AuthorityCoverage:
        authority = dict(run.authority or {})
        source = AuthoritySource(authority.get("source", AuthoritySource.NONE))
        return AuthorityCoverage(
            source=source,
            status="COVERED" if source is not AuthoritySource.NONE else "NOT_COVERED",
            reason_codes=() if source is not AuthoritySource.NONE else ("HUMAN_APPROVAL_REQUIRED",),
            approval_request_id=run.approval_request_id,
            approval_fingerprint=run.approval_fingerprint,
            consumed=bool(authority.get("consumed", False)),
        )

    def request_human_approval(self, store: ExecutionStore, run: ExecutionRun) -> tuple[ExecutionRun, dict]:
        if run.state is not ExecutionRunState.VALIDATED:
            raise ValueError("RUN_NOT_READY_FOR_APPROVAL")
        fingerprint = approval_fingerprint(run)
        request = {
            "request_id": new_id("approval"),
            "run_id": run.run_id,
            "status": "PENDING",
            "fingerprint": fingerprint,
            "preview": dict(run.preview or {}),
            "created_at": utc_now(),
        }
        store.save_approval_request(request)
        updated = store.transition(
            run,
            ExecutionRunState.WAITING_FOR_APPROVAL,
            approval_request_id=request["request_id"],
            approval_fingerprint=fingerprint,
            authority={"source": AuthoritySource.NONE.value, "consumed": False},
        )
        store.append_event(
            run.run_id,
            "APPROVAL_REQUESTED",
            {"approval_request_id": request["request_id"], "fingerprint": fingerprint},
        )
        return updated, request

    def approve_human(
        self,
        store: ExecutionStore,
        run_id: str,
        *,
        principal_id: str,
        affirmation: bool,
    ) -> ExecutionRun:
        run = store.load_run(run_id)
        if not affirmation or not principal_id.strip():
            raise ValueError("EXPLICIT_HUMAN_AFFIRMATION_REQUIRED")
        if run.state is not ExecutionRunState.WAITING_FOR_APPROVAL:
            raise ValueError("RUN_NOT_WAITING_FOR_APPROVAL")
        if not run.approval_request_id or not run.approval_fingerprint:
            raise ValueError("APPROVAL_REQUEST_MISSING")
        if approval_fingerprint(run) != run.approval_fingerprint:
            raise ValueError("APPROVAL_FINGERPRINT_MISMATCH")
        request = store.load_approval_request(run.approval_request_id)
        if request.get("run_id") != run.run_id or request.get("fingerprint") != run.approval_fingerprint:
            raise ValueError("APPROVAL_RUN_BINDING_MISMATCH")
        if request.get("status") != "PENDING":
            raise ValueError("APPROVAL_ALREADY_CONSUMED")
        request = {
            **request,
            "status": "APPROVED",
            "principal_id": principal_id,
            "approved_at": utc_now(),
        }
        store.save_approval_request(request)
        approved = store.transition(
            run,
            ExecutionRunState.APPROVED,
            authority={
                "source": AuthoritySource.HUMAN_RUN_APPROVAL.value,
                "consumed": False,
                "principal_id": principal_id,
                "approved_at": request["approved_at"],
            },
        )
        store.append_event(run.run_id, "HUMAN_APPROVED", {"principal_id": principal_id})
        return approved

    def consume(self, store: ExecutionStore, run: ExecutionRun) -> ExecutionRun:
        if run.state is not ExecutionRunState.APPROVED:
            raise ValueError("RUN_NOT_APPROVED")
        authority = dict(run.authority or {})
        if authority.get("source") != AuthoritySource.HUMAN_RUN_APPROVAL.value:
            raise ValueError("HUMAN_APPROVAL_REQUIRED")
        if authority.get("consumed"):
            raise ValueError("APPROVAL_ALREADY_CONSUMED")
        request = store.load_approval_request(run.approval_request_id)
        if request.get("status") != "APPROVED" or request.get("fingerprint") != run.approval_fingerprint:
            raise ValueError("APPROVAL_NOT_CONSUMABLE")
        consumed = store.transition(
            run,
            ExecutionRunState.APPLYING,
            authority={**authority, "consumed": True, "consumed_at": utc_now()},
        )
        store.append_event(run.run_id, "AUTHORITY_CONSUMED", {"source": authority["source"]})
        return consumed
