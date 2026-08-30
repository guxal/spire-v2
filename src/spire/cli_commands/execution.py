"""Mutation preparation and trusted approval command adapters."""

from __future__ import annotations

import getpass

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


def get_run(ctx: CommandContext, args) -> int:
    ctx.emit(ctx.api.run_get(args.run_id))
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
