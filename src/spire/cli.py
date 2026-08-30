# @file Public CLI entrypoint.
# @domain interfaces
# @status stable
# @adr [[0015-cli-interaction-policy]]
# @tested-by [[test_public_surfaces.py]]
"""Composition-only entrypoint for the public Spire CLI."""

from __future__ import annotations

import argparse
import json
import sys

from spire.application import Application
from spire.core import SpireError, WorkspacePaths, resolve_project_root
from spire.surfaces import PublicApi

from .cli_commands import accounts, auth, campaigns, evidence, execution, workspace
from .cli_commands.common import CommandContext


def main(argv: list[str] | None = None, *, application: Application | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        app = application or Application(WorkspacePaths(resolve_project_root(args.project_root)))
        if args.group == "mcp":
            from spire.mcp_server import serve

            serve(app)
            return 0
        context = CommandContext(app_api(app), args.json_output, args.no_input)
        return args.handler(context, args)
    except (SpireError, ValueError, TypeError, OSError, KeyError) as exc:
        code = getattr(exc, "reason_code", None) or (
            "PROVIDER_UNAVAILABLE" if isinstance(exc, OSError) else str(exc)
        ) or type(exc).__name__
        if getattr(args, "json_output", False):
            print(json.dumps({"error": code}, sort_keys=True))
        else:
            print(f"error: {code}", file=sys.stderr)
        return 1


def app_api(application: Application) -> PublicApi:
    return PublicApi(application)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spire", description="Frozen Google Ads operations")
    parser.add_argument(
        "--project-root",
        help=(
            "canonical workspace root; resolution order is this option, $SPIRE_PROJECT_ROOT, "
            "then the Spire source-checkout root; fails if none is available (relative explicit "
            "paths resolve from cwd)"
        ),
    )
    groups = parser.add_subparsers(dest="group", required=True)

    _auth_parser(groups)
    accounts_group = groups.add_parser("accounts", help="list accessible Google Ads accounts")
    accounts_actions = accounts_group.add_subparsers(dest="action", required=True)
    _leaf(accounts_actions, "list", accounts.list_accounts, help="list accounts")

    account_group = groups.add_parser("account", help="refresh frozen account truth")
    account_actions = account_group.add_subparsers(dest="action", required=True)
    refresh = _leaf(account_actions, "refresh", accounts.refresh, help="refresh account truth")
    refresh.add_argument("--customer-id")
    refresh.add_argument("--campaign-id")
    refresh.add_argument("--enabled-only", action="store_true")
    refresh.add_argument("--date-start")
    refresh.add_argument("--date-end")

    campaigns_group = groups.add_parser("campaigns", help="discover and read campaigns")
    campaign_actions = campaigns_group.add_subparsers(dest="action", required=True)
    discover = _leaf(campaign_actions, "discover", campaigns.discover, help="discover live campaigns")
    discover.add_argument("--customer-id")
    listing = _leaf(campaign_actions, "list", campaigns.list_campaigns, help="list frozen campaigns")
    listing.add_argument("--customer-id")
    get = _leaf(campaign_actions, "get", campaigns.get_campaign, help="read one frozen campaign")
    get.add_argument("--customer-id")
    get.add_argument("--campaign-id")

    evidence_group = groups.add_parser("evidence", help="query frozen evidence")
    evidence_actions = evidence_group.add_subparsers(dest="action", required=True)
    query = _leaf(evidence_actions, "query", evidence.query, help="run a safe evidence query")
    query.add_argument("--customer-id")
    query.add_argument("--campaign-id", action="append", default=[])
    query.add_argument("--dataset", required=True)
    query.add_argument("--date-start")
    query.add_argument("--date-end")
    query.add_argument("--dimension", action="append", default=[])
    query.add_argument("--metric", action="append", default=[])
    query.add_argument("--limit", type=int, default=100)
    query.add_argument("--order-by", action="append")
    datasets = _leaf(evidence_actions, "datasets", evidence.datasets, help="list available datasets")
    datasets.add_argument("--customer-id")
    datasets.add_argument("--campaign-id")

    change_group = groups.add_parser("change", help="prepare an approved business change")
    change_actions = change_group.add_subparsers(dest="action", required=True)
    budget = _leaf(change_actions, "budget", execution.change_budget, help="prepare a budget change")
    budget.add_argument("--customer-id")
    budget.add_argument("--campaign-id")
    budget.add_argument("--daily-budget", required=True)
    budget.add_argument("--environment", default="production")

    runs_group = groups.add_parser("runs", help="inspect and continue execution runs")
    run_actions = runs_group.add_subparsers(dest="action", required=True)
    run_list = _leaf(run_actions, "list", execution.list_runs, help="discover runs")
    run_list.add_argument("--customer-id")
    run_list.add_argument("--campaign-id")
    run_list.add_argument("--status")
    run_list.add_argument("--limit", type=int, default=100)
    run_list.add_argument("--latest", action="store_true")
    run_list.add_argument("--order-by", choices=("created_at", "updated_at"), default="created_at")
    run_get = _leaf(run_actions, "get", execution.get_run, help="inspect a run")
    run_get.add_argument("--run-id", required=True)
    approve = _leaf(run_actions, "approve", execution.approve, help="approve one exact run")
    approve.add_argument("--run-id", required=True)
    approve.add_argument("--principal")
    approve.add_argument("--yes", action="store_true", help="affirm the exact displayed preview")
    resume = _leaf(run_actions, "resume", execution.resume, help="continue an approved run")
    resume.add_argument("--run-id", required=True)

    workspace_group = groups.add_parser("workspace", help="inspect the active workspace")
    workspace_actions = workspace_group.add_subparsers(dest="action", required=True)
    _leaf(workspace_actions, "status", workspace.status, help="show safe workspace status")

    groups.add_parser("mcp", help="run the MCP stdio server")
    return parser


def _auth_parser(groups: argparse._SubParsersAction) -> None:
    auth_group = groups.add_parser("auth", help="authenticate external providers")
    providers = auth_group.add_subparsers(dest="provider", required=True)
    google = providers.add_parser("google-ads", help="Google Ads authentication")
    actions = google.add_subparsers(dest="action", required=True)
    login = _leaf(actions, "login", auth.login, help="start OAuth login")
    login.add_argument("--port", type=int, default=8080)
    _leaf(actions, "status", auth.status, help="show local authentication status")
    verify = _leaf(actions, "verify", auth.verify, help="verify account access")
    verify.add_argument("--customer-id")


def _leaf(parent: argparse._SubParsersAction, name: str, handler, *, help: str):
    parser = parent.add_parser(name, help=help)
    parser.set_defaults(handler=handler, json_output=False, no_input=False)
    parser.add_argument("--json", dest="json_output", action="store_true")
    parser.add_argument("--no-input", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
