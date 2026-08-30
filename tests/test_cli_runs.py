from __future__ import annotations

import json

from spire.cli import main
from spire.core import ArtifactNotFoundError

RUN = {
    "run_id": "run_test",
    "customer_id": "1234567890",
    "campaign_id": "101",
    "change_kind": "UPDATE_BUDGET",
    "state": "WAITING_FOR_APPROVAL",
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:01Z",
    "terminal": False,
    "approval_required": True,
    "approval_state": "PENDING",
    "request_sent": False,
    "verification_state": "NOT_STARTED",
    "environment": "PRODUCTION",
    "validate_only_result": "REMOTE_VALIDATED",
    "policy": "ALLOWED",
    "fingerprint": "sha256:test",
    "current_value": "12.5",
    "proposed_value": "13",
    "delta_value": "0.5",
    "currency": "USD",
}


class _RunQueries:
    def __init__(self, *, found: bool = True) -> None:
        self.found = found
        self.filters = None

    def list_runs(self, **filters):
        self.filters = filters
        if not self.found:
            raise ArtifactNotFoundError("EXECUTION_RUN_NOT_FOUND")
        return (RUN,)


class _Application:
    def __init__(self, runs: _RunQueries) -> None:
        self.runs = runs


def test_runs_list_json_is_stable_and_delegates_filters(capsys):
    queries = _RunQueries()
    result = main(
        [
            "runs",
            "list",
            "--customer-id",
            "1234567890",
            "--campaign-id",
            "101",
            "--status",
            "waiting_for_approval",
            "--limit",
            "5",
            "--order-by",
            "updated_at",
            "--json",
        ],
        application=_Application(queries),
    )

    assert result == 0
    assert capsys.readouterr().out == json.dumps([RUN], sort_keys=True) + "\n"
    assert queries.filters == {
        "customer_id": "1234567890",
        "campaign_id": "101",
        "state": "waiting_for_approval",
        "order_by": "updated_at",
        "limit": 5,
    }


def test_runs_list_latest_returns_one_run(capsys):
    queries = _RunQueries()
    result = main(
        ["runs", "list", "--status", "waiting_for_approval", "--latest", "--json"],
        application=_Application(queries),
    )

    assert result == 0
    assert capsys.readouterr().out == json.dumps(RUN, sort_keys=True) + "\n"
    assert queries.filters["limit"] == 1


def test_runs_list_no_match_is_stable_not_found(capsys):
    result = main(
        ["runs", "list", "--latest", "--json"],
        application=_Application(_RunQueries(found=False)),
    )

    assert result == 1
    assert json.loads(capsys.readouterr().out) == {"error": "EXECUTION_RUN_NOT_FOUND"}
