from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from spire.cli import main
from spire.core import WorkspacePaths, WorkspaceStatusService
from spire.execution import (
    AuthorityService,
    BudgetCompiler,
    ExecutionRunQueryService,
    ExecutionRunService,
    HardPolicyService,
    PreviewResult,
)
from spire.google_ads import RefreshSpec, ScopedRefreshService
from spire.mcp_server import McpServer
from spire.surfaces import PublicApi
from spire.truth import AccountSnapshotService

ROOT = Path(__file__).parents[1].resolve()
CUSTOMER_ID = "1234567890"
CAMPAIGN_ID = "101"


class _PreviewRuntime:
    def validate_only(self, operation):
        return PreviewResult("PASSED", operation.content_hash, "2026-01-01T00:00:00Z")

    def mutate(self, _operation):
        raise AssertionError("preparation must not mutate")


class _PreparationApplication:
    def __init__(self, workspace: WorkspacePaths) -> None:
        self.workspace = workspace
        self.runs = ExecutionRunQueryService(workspace)
        self.workspace_status = WorkspaceStatusService(workspace)
        self.execution = ExecutionRunService(
            workspace,
            snapshots=AccountSnapshotService(workspace),
            compiler=BudgetCompiler(workspace),
            policy=HardPolicyService(),
            authority=AuthorityService(),
            runtime=_PreviewRuntime(),
        )

    def for_customer(self, _customer_id: str):
        return SimpleNamespace(execution=self.execution)


def _seed_truth(workspace, provider) -> None:
    ScopedRefreshService(provider, workspace).refresh(
        RefreshSpec(CUSTOMER_ID, (CAMPAIGN_ID,))
    )


def _run_cli(project_root, *arguments, cwd=None, environment=None):
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(ROOT / "src"), env.get("PYTHONPATH")) if part
    )
    if environment:
        env.update(environment)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "spire.cli",
            "--project-root",
            str(project_root),
            *arguments,
        ],
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _prepare_through_cli(workspace, provider, capsys):
    _seed_truth(workspace, provider)
    result = main(
        [
            "change",
            "budget",
            "--customer-id",
            CUSTOMER_ID,
            "--campaign-id",
            CAMPAIGN_ID,
            "--daily-budget",
            "13",
            "--environment",
            "production",
            "--json",
        ],
        application=_PreparationApplication(workspace),
    )
    assert result == 0
    return json.loads(capsys.readouterr().out)


def test_run_created_by_cli_is_rediscovered_by_a_new_cli_process(
    fake_runtime, capsys, tmp_path
):
    workspace, provider, _calls = fake_runtime
    prepared = _prepare_through_cli(workspace, provider, capsys)
    unrelated_cwd = tmp_path / "unrelated"
    unrelated_cwd.mkdir()

    listed = _run_cli(
        workspace.project_root,
        "runs",
        "list",
        "--customer-id",
        CUSTOMER_ID,
        "--campaign-id",
        CAMPAIGN_ID,
        "--status",
        "waiting_for_approval",
        "--latest",
        "--json",
        cwd=unrelated_cwd,
    )

    assert listed.returncode == 0, listed.stderr
    assert json.loads(listed.stdout)["run_id"] == prepared["run_id"]


def test_run_created_through_mcp_is_rediscovered_through_cli(fake_runtime, tmp_path):
    workspace, provider, _calls = fake_runtime
    _seed_truth(workspace, provider)
    server = McpServer(PublicApi(_PreparationApplication(workspace)))
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "change_budget",
                "arguments": {
                    "customer_id": CUSTOMER_ID,
                    "campaign_id": CAMPAIGN_ID,
                    "daily_budget": "13",
                    "environment": "production",
                },
            },
        }
    )
    prepared = response["result"]["structuredContent"]

    listed = _run_cli(
        workspace.project_root,
        "runs",
        "list",
        "--customer-id",
        CUSTOMER_ID,
        "--latest",
        "--json",
        cwd=tmp_path,
    )

    assert response["result"]["isError"] is False
    assert listed.returncode == 0, listed.stderr
    assert json.loads(listed.stdout)["run_id"] == prepared["run_id"]


def test_different_explicit_project_roots_have_isolated_stores(fake_runtime, capsys, tmp_path):
    workspace, provider, _calls = fake_runtime
    _prepare_through_cli(workspace, provider, capsys)
    isolated_root = tmp_path / "isolated"
    isolated_root.mkdir()

    listed = _run_cli(
        isolated_root,
        "runs",
        "list",
        "--customer-id",
        CUSTOMER_ID,
        "--latest",
        "--json",
    )

    assert listed.returncode == 1
    assert json.loads(listed.stdout) == {"error": "EXECUTION_RUN_NOT_FOUND"}


def test_cli_and_mcp_composition_use_same_configured_root(monkeypatch, tmp_path, capsys):
    project_root = tmp_path / "canonical"
    unrelated_cwd = tmp_path / "elsewhere"
    project_root.mkdir()
    unrelated_cwd.mkdir()
    monkeypatch.chdir(unrelated_cwd)
    monkeypatch.setenv("SPIRE_PROJECT_ROOT", str(project_root))

    assert main(["workspace", "status", "--json"]) == 0
    cli_status = json.loads(capsys.readouterr().out)

    captured = {}

    def capture(application):
        captured["project_root"] = str(application.workspace.project_root)

    monkeypatch.setattr("spire.mcp_server.serve", capture)
    assert main(["mcp"]) == 0

    assert cli_status["project_root"] == str(project_root.resolve())
    assert captured["project_root"] == cli_status["project_root"]


def test_workspace_status_json_and_project_root_help_are_public(tmp_path, capsys):
    status = _run_cli(tmp_path, "workspace", "status", "--json")

    assert status.returncode == 0, status.stderr
    assert json.loads(status.stdout) == {
        "configured_customer_count": 0,
        "customer_root_pattern": str(
            tmp_path.resolve() / ".spire" / "customers" / "<customer_id>"
        ),
        "execution_store_available": "NO",
        "project_root": str(tmp_path.resolve()),
    }

    try:
        main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
    assert "SPIRE_PROJECT_ROOT" in capsys.readouterr().out
