"""Frozen evidence command adapters."""

from .common import CommandContext, require_campaign, require_customer


def query(ctx: CommandContext, args) -> int:
    customer_id = require_customer(ctx, args.customer_id)
    campaign_ids = args.campaign_id or [require_campaign(ctx, customer_id, None)]
    payload = ctx.api.evidence_query(
        customer_id,
        campaign_ids,
        args.dataset,
        date_range=(
            {"start": args.date_start, "end": args.date_end}
            if args.date_start and args.date_end
            else None
        ),
        dimensions=args.dimension,
        metrics=args.metric,
        filters={},
        limit=args.limit,
        order_by=args.order_by,
    )
    ctx.emit(payload)
    return 0


def datasets(ctx: CommandContext, args) -> int:
    customer_id = require_customer(ctx, args.customer_id)
    campaign_id = require_campaign(ctx, customer_id, args.campaign_id)
    ctx.emit(ctx.api.evidence_datasets(customer_id, campaign_id))
    return 0
