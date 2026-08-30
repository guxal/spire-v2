"""Small immutable contracts for the canonical execution lifecycle."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from spire.core import (
    canonical_hash,
    validate_artifact_id,
    validate_customer_id,
    validate_google_ads_id,
)


class ChangeKind(StrEnum):
    UPDATE_BUDGET = "UPDATE_BUDGET"


class ExecutionMode(StrEnum):
    PRODUCTION = "PRODUCTION"


class ExecutionRunState(StrEnum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    APPROVED = "APPROVED"
    APPLYING = "APPLYING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    RECONCILING = "RECONCILING"


class AuthoritySource(StrEnum):
    OPERATING_MANDATE = "operating_mandate"
    HUMAN_RUN_APPROVAL = "human_run_approval"
    NONE = "none"


def _freeze(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


def _hashable(value: Mapping[str, Any]) -> dict[str, Any]:
    return dict(value)


@dataclass(frozen=True, slots=True)
class ChangeSpec:
    spec_id: str
    customer_id: str
    account_id: str
    kind: ChangeKind
    target: Mapping[str, Any]
    requested_change: Mapping[str, Any]
    snapshot_ref: Mapping[str, Any]
    provenance: Mapping[str, Any] = field(default_factory=dict)
    content_hash: str = ""

    def __post_init__(self) -> None:
        validate_artifact_id(self.spec_id, field="spec_id")
        validate_customer_id(self.customer_id)
        validate_customer_id(self.account_id)
        object.__setattr__(self, "kind", ChangeKind(self.kind))
        object.__setattr__(self, "target", _freeze(self.target))
        object.__setattr__(self, "requested_change", _freeze(self.requested_change))
        object.__setattr__(self, "snapshot_ref", _freeze(self.snapshot_ref))
        object.__setattr__(self, "provenance", _freeze(self.provenance))
        if str(self.target.get("campaign_id", "")):
            validate_google_ads_id(str(self.target["campaign_id"]), field="campaign_id")
        forbidden = {"authority", "approval", "credentials", "execution_mode", "mode", "resource_name"}
        if forbidden.intersection(self.requested_change) or forbidden.intersection(self.provenance):
            raise ValueError("CHANGE_SPEC_AUTHORITY_OR_TECHNICAL_FIELD_FORBIDDEN")
        expected = canonical_hash(self._hash_material())
        if self.content_hash and self.content_hash != expected:
            raise ValueError("CHANGE_SPEC_HASH_MISMATCH")
        object.__setattr__(self, "content_hash", expected)

    def _hash_material(self) -> dict[str, Any]:
        return {
            "spec_id": self.spec_id,
            "customer_id": self.customer_id,
            "account_id": self.account_id,
            "kind": self.kind.value,
            "target": _hashable(self.target),
            "requested_change": _hashable(self.requested_change),
            "snapshot_ref": _hashable(self.snapshot_ref),
            "provenance": _hashable(self.provenance),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._hash_material(), "content_hash": self.content_hash}


@dataclass(frozen=True, slots=True)
class CompiledOperation:
    operation_id: str
    customer_id: str
    campaign_id: str
    kind: ChangeKind
    budget_resource_name: str
    daily_budget_micros: int
    snapshot_hash: str
    compiler_version: str = "spire-v2.update-budget.v1"
    content_hash: str = ""

    def __post_init__(self) -> None:
        validate_artifact_id(self.operation_id, field="operation_id")
        validate_customer_id(self.customer_id)
        validate_google_ads_id(self.campaign_id, field="campaign_id")
        object.__setattr__(self, "kind", ChangeKind(self.kind))
        if self.kind is not ChangeKind.UPDATE_BUDGET or self.daily_budget_micros <= 0:
            raise ValueError("INVALID_COMPILED_BUDGET")
        if not self.budget_resource_name.startswith("customers/"):
            raise ValueError("COMPILED_BUDGET_RESOURCE_INVALID")
        expected = canonical_hash(self._hash_material())
        if self.content_hash and self.content_hash != expected:
            raise ValueError("COMPILED_OPERATION_HASH_MISMATCH")
        object.__setattr__(self, "content_hash", expected)

    def _hash_material(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "customer_id": self.customer_id,
            "campaign_id": self.campaign_id,
            "kind": self.kind.value,
            "budget_resource_name": self.budget_resource_name,
            "daily_budget_micros": self.daily_budget_micros,
            "snapshot_hash": self.snapshot_hash,
            "compiler_version": self.compiler_version,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._hash_material(), "content_hash": self.content_hash}


@dataclass(frozen=True, slots=True)
class PreviewResult:
    status: str
    operation_hash: str
    observed_at: str
    provider_code: str = ""
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "operation_hash": self.operation_hash,
            "observed_at": self.observed_at,
            "provider_code": self.provider_code,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class VerificationResult:
    status: str
    expected: Mapping[str, Any]
    observed: Mapping[str, Any]
    observed_at: str
    reason_code: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "expected", _freeze(self.expected))
        object.__setattr__(self, "observed", _freeze(self.observed))

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "expected": dict(self.expected),
            "observed": dict(self.observed),
            "observed_at": self.observed_at,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True, slots=True)
class HardPolicyDecision:
    status: str
    reason_codes: tuple[str, ...]
    evaluated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "reason_codes": list(self.reason_codes), "evaluated_at": self.evaluated_at}


@dataclass(frozen=True, slots=True)
class AuthorityCoverage:
    source: AuthoritySource
    status: str
    reason_codes: tuple[str, ...] = ()
    approval_request_id: str = ""
    approval_fingerprint: str = ""
    consumed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", AuthoritySource(self.source))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.value,
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "approval_request_id": self.approval_request_id,
            "approval_fingerprint": self.approval_fingerprint,
            "consumed": self.consumed,
        }


@dataclass(frozen=True, slots=True)
class ExecutionRun:
    run_id: str
    spec_id: str
    customer_id: str
    account_id: str
    mode: ExecutionMode
    state: ExecutionRunState
    spec_hash: str
    snapshot_ref: Mapping[str, Any]
    compiled_operation: Mapping[str, Any] | None = None
    preview: Mapping[str, Any] | None = None
    policy: Mapping[str, Any] | None = None
    authority: Mapping[str, Any] | None = None
    approval_fingerprint: str = ""
    approval_request_id: str = ""
    request_sent: Mapping[str, Any] | None = None
    verification: Mapping[str, Any] | None = None
    failure_reason: str = ""
    created_at: str = ""
    updated_at: str = ""
    content_hash: str = ""

    def __post_init__(self) -> None:
        validate_artifact_id(self.run_id, field="run_id")
        validate_artifact_id(self.spec_id, field="spec_id")
        validate_customer_id(self.customer_id)
        validate_customer_id(self.account_id)
        object.__setattr__(self, "mode", ExecutionMode(self.mode))
        object.__setattr__(self, "state", ExecutionRunState(self.state))
        object.__setattr__(self, "snapshot_ref", _freeze(self.snapshot_ref))
        for name in ("compiled_operation", "preview", "policy", "authority", "request_sent", "verification"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _freeze(value))
        expected = canonical_hash(self._hash_material())
        if self.content_hash and self.content_hash != expected:
            raise ValueError("EXECUTION_RUN_HASH_MISMATCH")
        object.__setattr__(self, "content_hash", expected)

    def _hash_material(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "spec_id": self.spec_id,
            "customer_id": self.customer_id,
            "account_id": self.account_id,
            "mode": self.mode.value,
            "state": self.state.value,
            "spec_hash": self.spec_hash,
            "snapshot_ref": dict(self.snapshot_ref),
            "compiled_operation": dict(self.compiled_operation) if self.compiled_operation else None,
            "preview": dict(self.preview) if self.preview else None,
            "policy": dict(self.policy) if self.policy else None,
            "authority": dict(self.authority) if self.authority else None,
            "approval_fingerprint": self.approval_fingerprint,
            "approval_request_id": self.approval_request_id,
            "request_sent": dict(self.request_sent) if self.request_sent else None,
            "verification": dict(self.verification) if self.verification else None,
            "failure_reason": self.failure_reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._hash_material(), "content_hash": self.content_hash}
