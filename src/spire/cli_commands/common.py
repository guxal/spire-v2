"""Shared presentation and interactive selection helpers."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from spire.core import GoogleAdsAuthError, validate_customer_id, validate_google_ads_id
from spire.surfaces import PublicApi


@dataclass
class CommandContext:
    api: PublicApi
    json_output: bool = False
    no_input: bool = False
    input_fn: Callable[[str], str] = input
    output_fn: Callable[[str], None] = print

    @property
    def interactive(self) -> bool:
        return not self.json_output and not self.no_input and sys.stdin.isatty()

    def write(self, value: str) -> None:
        self.output_fn(value)

    def emit(self, payload: Any, *, human: Callable[[Any], str] | None = None) -> None:
        if self.json_output:
            self.output_fn(json.dumps(payload, sort_keys=True, default=str))
        elif human:
            self.output_fn(human(payload))
        elif isinstance(payload, dict):
            for key, value in payload.items():
                self.output_fn(f"{key}: {value}")
        else:
            self.output_fn(str(payload))


def require_customer(ctx: CommandContext, customer_id: str | None) -> str:
    if customer_id:
        return validate_customer_id(customer_id)
    if not ctx.interactive:
        raise ValueError("CUSTOMER_ID_REQUIRED_NON_INTERACTIVE")
    accounts = ctx.api.accounts_list()
    if not accounts:
        raise GoogleAdsAuthError("NO_ACCESSIBLE_ACCOUNTS")
    ctx.write("Available Google Ads accounts:")
    for index, account in enumerate(accounts, start=1):
        ctx.write(f"[{index}] {account['name']} ({account['customer_id']})")
    choice = ctx.input_fn("Select account number: ").strip()
    try:
        return validate_customer_id(accounts[int(choice) - 1]["customer_id"])
    except (ValueError, IndexError) as exc:
        raise ValueError("CUSTOMER_SELECTION_INVALID") from exc


def require_campaign(ctx: CommandContext, customer_id: str, campaign_id: str | None) -> str:
    if campaign_id:
        return validate_google_ads_id(campaign_id, field="campaign_id")
    if not ctx.interactive:
        raise ValueError("CAMPAIGN_ID_REQUIRED_NON_INTERACTIVE")
    campaigns = ctx.api.campaigns_list(customer_id)
    if not campaigns:
        raise ValueError("NO_CAMPAIGNS_AVAILABLE")
    ctx.write("Available campaigns:")
    for index, campaign in enumerate(campaigns, start=1):
        ctx.write(f"[{index}] {campaign.get('name', '')} ({campaign.get('campaign_id')})")
    choice = ctx.input_fn("Select campaign number: ").strip()
    try:
        return validate_google_ads_id(campaigns[int(choice) - 1]["campaign_id"], field="campaign_id")
    except (ValueError, IndexError) as exc:
        raise ValueError("CAMPAIGN_SELECTION_INVALID") from exc


def human_campaign(payload: dict[str, Any]) -> str:
    return "\n".join(
        (
            f"Campaign: {payload.get('name', payload.get('campaign_id', ''))}",
            f"Status: {payload.get('status')}",
            f"Budget: {payload.get('daily_budget')} {payload.get('currency')}/day",
            f"Snapshot: {payload.get('snapshot', 'CURRENT')}",
        )
    )


def human_refresh(payload: dict[str, Any]) -> str:
    return "\n".join(
        (
            "Refresh complete",
            f"Campaigns: {payload['campaign_count']}",
            f"Snapshot: {payload['snapshot']}",
            f"Evidence: {payload['evidence_ref']}",
        )
    )


def human_change(payload: dict[str, Any]) -> str:
    lines = [
        f"Run: {payload['run_id']}",
        f"Campaign: {payload.get('campaign_id', '')}",
        f"Current: {payload.get('current', 'unknown')}",
        f"Proposed: {payload.get('proposed', 'unknown')}",
        f"Delta: {payload.get('delta', 'unknown')}",
        f"Dry-run: {payload.get('dry_run', 'REMOTE_VALIDATED')}",
        f"Policy: {payload.get('policy', 'ALLOWED')}",
        f"Authority: {payload.get('authority', 'HUMAN_APPROVAL_REQUIRED')}",
        f"Status: {payload.get('state', 'WAITING_FOR_APPROVAL')}",
    ]
    if payload.get("fingerprint"):
        lines.append(f"Fingerprint: {payload['fingerprint']}")
    if payload.get("operation"):
        lines.append(f"Operation: {payload['operation']}")
    return "\n".join(lines)
