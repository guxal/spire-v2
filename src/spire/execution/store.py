"""Execution artifact persistence confined to the account execution root."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from spire.core import ArtifactNotFoundError, safe_artifact_file, safe_child, validate_customer_id

from .contracts import ChangeSpec, ExecutionRun, ExecutionRunState


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:12]}"


class ExecutionStore:
    """Small JSON artifact store; no other runtime root is supported."""

    def __init__(self, workspace, customer_id: str) -> None:
        self.workspace = workspace
        self.customer_id = validate_customer_id(customer_id)
        self.root = workspace.execution(self.customer_id)

    @classmethod
    def find(cls, workspace, run_id: str) -> tuple[ExecutionStore, ExecutionRun]:
        """Locate a run through the account workspace boundary."""

        for customer_id in workspace.customer_ids():
            store = cls(workspace, customer_id)
            try:
                return store, store.load_run(run_id)
            except ArtifactNotFoundError:
                continue
        raise ArtifactNotFoundError("EXECUTION_RUN_NOT_FOUND")

    def save_spec(self, spec: ChangeSpec) -> None:
        self._write("change_specs", spec.spec_id, spec.to_dict())

    def load_spec(self, spec_id: str) -> ChangeSpec:
        return ChangeSpec(**self._read("change_specs", spec_id))

    def save_run(self, run: ExecutionRun) -> ExecutionRun:
        self._write("runs", run.run_id, run.to_dict())
        return run

    def load_run(self, run_id: str) -> ExecutionRun:
        return ExecutionRun(**self._read("runs", run_id))

    def transition(self, run: ExecutionRun, state: ExecutionRunState, **changes) -> ExecutionRun:
        if run.state is state and not changes:
            return run
        now = utc_now()
        updated = replace(run, state=state, updated_at=now, content_hash="", **changes)
        self.save_run(updated)
        self.append_event(updated.run_id, "STATE_CHANGED", {"state": state.value})
        return updated

    def append_event(self, run_id: str, event_type: str, payload: dict) -> None:
        events_root = safe_child(self.root, "events", field="execution_category")
        path = safe_artifact_file(events_root, run_id, suffix=".jsonl", field="run_id")
        path.parent.mkdir(parents=True, exist_ok=True)
        event = {"event_type": event_type, "run_id": run_id, "observed_at": utc_now(), **payload}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    def save_approval_request(self, request: dict) -> None:
        self._write("approval_requests", request["request_id"], request)

    def load_approval_request(self, request_id: str) -> dict:
        return self._read("approval_requests", request_id)

    def _write(self, category: str, artifact_id: str, payload: dict) -> None:
        category_root = safe_child(self.root, category, field="execution_category")
        path = safe_artifact_file(category_root, artifact_id)
        temporary = path.with_name(f".{path.name}.tmp")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        temporary.replace(path)

    def _read(self, category: str, artifact_id: str) -> dict:
        category_root = safe_child(self.root, category, field="execution_category")
        path = safe_artifact_file(category_root, artifact_id)
        if not path.exists():
            raise ArtifactNotFoundError(f"EXECUTION_ARTIFACT_NOT_FOUND:{category}:{artifact_id}")
        return json.loads(path.read_text(encoding="utf-8"))
