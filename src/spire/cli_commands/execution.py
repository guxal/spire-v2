"""Mutation preparation and trusted approval command adapters."""

from __future__ import annotations

import getpass
from decimal import Decimal
from typing import Any

from .common import CommandContext, human_change, require_campaign, require_customer


def change_budget(ctx: CommandContext, args) -> int:
    customer_id = require_customer(ctx, args.customer_id)
    campaign_id = require_campaign(ctx, customer_id, args.campaign_id)
    prepared = ctx.api.change_budget(
        customer_id,
        campaign_id,
        args.daily_budget,
        environment=args.environment,
    )
    ctx.emit(prepared, human=human_change)
    return 0


def list_runs(ctx: CommandContext, args) -> int:
    result = ctx.api.runs_list(
        customer_id=args.customer_id,
        campaign_id=args.campaign_id,
        state=args.status,
        order_by=args.order_by,
        limit=args.limit,
        latest=args.latest,
    )
    ctx.emit(result, human=human_run)
    return 0


def get_run(ctx: CommandContext, args) -> int:
    ctx.emit(ctx.api.run_get(args.run_id), human=human_run)
    return 0


def approve(ctx: CommandContext, args) -> int:
    preview = ctx.api.run_approval_preview(args.run_id)
    if ctx.json_output and not args.yes:
        raise ValueError("EXPLICIT_APPROVAL_REQUIRED_FOR_JSON")
    if not args.yes and not ctx.interactive:
        raise ValueError("APPROVAL_REQUIRED_INTERACTIVE")
    if not ctx.json_output:
        ctx.emit(preview, human=human_change)
    if not args.yes:
        answer = ctx.input_fn("Approve this exact run? [y/N]: ").strip().lower()
        if answer not in {"y", "yes"}:
            raise ValueError("APPROVAL_NOT_CONFIRMED")
    result = ctx.api.run_approve(args.run_id, principal_id=args.principal or getpass.getuser())
    if ctx.json_output:
        ctx.emit({"preview": preview, "approval": result})
    else:
        ctx.emit(result)
    return 0


def resume(ctx: CommandContext, args) -> int:
    ctx.emit(ctx.api.run_resume(args.run_id))
    return 0


def human_run(payload: dict[str, Any] | list[dict[str, Any]]) -> str:
    runs = payload if isinstance(payload, list) else [payload]
    return "\n\n".join(_human_run_item(run) for run in runs)


def _human_run_item(run: dict[str, Any]) -> str:
    currency = run.get("currency")
    lines = [
        f"Run ID: {run['run_id']}",
        f"Customer: {run['customer_id']}",
        f"Campaign: {run.get('campaign_id') or 'not applicable'}",
        f"Change: {run.get('change_kind') or 'unknown'}",
        f"State: {run['state']}",
        f"Created: {run['created_at']}",
        f"Updated: {run['updated_at']}",
        f"Terminal: {'yes' if run['terminal'] else 'no'}",
        f"Current budget: {_money(run.get('current_value'), currency)}",
        f"Proposed budget: {_money(run.get('proposed_value'), currency)}",
        f"Delta: {_signed_money(run.get('delta_value'), currency)}",
        f"Validate-only result: {run['validate_only_result']}",
        f"Policy: {run.get('policy') or 'NOT_EVALUATED'}",
        f"Approval required: {'yes' if run['approval_required'] else 'no'}",
        f"Approval state: {run['approval_state']}",
        f"Request sent: {'present' if run['request_sent'] else 'absent'}",
        f"Verification state: {run['verification_state']}",
    ]
    if run.get("fingerprint"):
        lines.append(f"Fingerprint: {run['fingerprint']}")
    return "\n".join(lines)


def _money(value: Any, currency: Any) -> str:
    if value is None:
        return "unknown"
    return f"{_grouped_decimal(value)} {currency or 'currency unknown'}/day"


def _signed_money(value: Any, currency: Any) -> str:
    if value is None:
        return "unknown"
    amount = Decimal(str(value))
    sign = "+" if amount > 0 else ""
    return f"{sign}{_grouped_decimal(value)} {currency or 'currency unknown'}/day"


def _grouped_decimal(value: Any) -> str:
    formatted = format(Decimal(str(value)), ",f")
    return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted
