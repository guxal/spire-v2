# @file Authentication CLI adapters.
# @domain interfaces
# @status stable
"""Authentication command adapters."""

from __future__ import annotations

from .common import CommandContext


def login(ctx: CommandContext, args) -> int:
    if not ctx.interactive:
        raise ValueError("INTERACTIVE_AUTH_REQUIRED")
    ctx.emit(ctx.api.application.auth.login(port=args.port))
    return 0


def status(ctx: CommandContext, args) -> int:
    del args
    ctx.emit(ctx.api.application.auth.status())
    return 0


def verify(ctx: CommandContext, args) -> int:
    customer_id = args.customer_id
    if customer_id is None and not ctx.interactive:
        raise ValueError("CUSTOMER_ID_REQUIRED_NON_INTERACTIVE")
    result = ctx.api.application.auth.verify(
        customer_id,
        input_fn=ctx.input_fn,
        output_fn=ctx.write,
    )
    ctx.emit(result)
    return 0
