"""Campaign command adapters."""

from .common import CommandContext, human_campaign, require_campaign, require_customer


def discover(ctx: CommandContext, args) -> int:
    customer_id = require_customer(ctx, args.customer_id)
    ctx.emit(ctx.api.campaigns_discover(customer_id))
    return 0


def list_campaigns(ctx: CommandContext, args) -> int:
    customer_id = require_customer(ctx, args.customer_id)
    ctx.emit(ctx.api.campaigns_list(customer_id))
    return 0


def get_campaign(ctx: CommandContext, args) -> int:
    customer_id = require_customer(ctx, args.customer_id)
    campaign_id = require_campaign(ctx, customer_id, args.campaign_id)
    ctx.emit(ctx.api.campaigns_get(customer_id, campaign_id), human=human_campaign)
    return 0
