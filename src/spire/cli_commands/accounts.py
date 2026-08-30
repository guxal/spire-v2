# @file Account CLI adapters.
# @domain interfaces
# @status stable
"""Account discovery and refresh command adapters."""

from .common import CommandContext, human_refresh, require_customer


def list_accounts(ctx: CommandContext, args) -> int:
    del args
    ctx.emit(ctx.api.accounts_list())
    return 0


def refresh(ctx: CommandContext, args) -> int:
    customer_id = require_customer(ctx, args.customer_id)
    if bool(args.date_start) != bool(args.date_end):
        raise ValueError("DATE_RANGE_BOTH_BOUNDS_REQUIRED")
    payload = ctx.api.account_refresh(
        customer_id,
        campaign_id=args.campaign_id,
        enabled_only=args.enabled_only,
        date_range=(
            {"start": args.date_start, "end": args.date_end}
            if args.date_start and args.date_end
            else None
        ),
    )
    ctx.emit(payload, human=human_refresh)
    return 0
