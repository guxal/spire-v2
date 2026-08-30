# @file Execution authority surface contracts.
# @domain interfaces
# @status stable
# @adr [[0012-exact-human-approval]]
# @adr [[0018-bounded-execution-operation-extension]]
# @tested-by [[test_execution_authority.py]]
"""Thin external surfaces around the canonical execution service."""

from __future__ import annotations


class McpExecutionSurface:
    """Agent-callable preparation only; it has no approval operation."""

    def __init__(self, execution_service) -> None:
        self.execution_service = execution_service

    def change_budget(
        self,
        customer_id: str,
        campaign_id: str,
        daily_budget: object,
        environment: str = "PRODUCTION",
    ) -> dict:
        return self.execution_service.prepare_change_budget(
            customer_id,
            campaign_id,
            daily_budget,
            environment=environment,
            provenance={"producer": "mcp"},
        )

    def change_negative_keyword(
        self,
        customer_id: str,
        campaign_id: str,
        text: object,
        match_type: object,
        *,
        ad_group_id: str | None = None,
        environment: str = "PRODUCTION",
    ) -> dict:
        return self.execution_service.prepare_add_negative_keyword(
            customer_id,
            campaign_id,
            text,
            match_type,
            ad_group_id=ad_group_id,
            environment=environment,
            provenance={"producer": "mcp"},
        )

    def create_search_campaign(
        self, customer_id: str, request: dict, environment: str = "PRODUCTION"
    ) -> dict:
        return self.execution_service.prepare_create_search_campaign(
            customer_id,
            request,
            environment=environment,
            provenance={"producer": "mcp"},
        )


class TrustedExecutionCli:
    """Human-facing approval and continuation for an existing exact request."""

    def __init__(self, execution_service) -> None:
        self.execution_service = execution_service

    def approve_run(
        self,
        run_id: str,
        *,
        customer_id: str,
        principal_id: str,
        affirmation: bool,
    ) -> dict:
        return self.execution_service.approve_human(
            run_id,
            customer_id=customer_id,
            principal_id=principal_id,
            affirmation=affirmation,
        )

    def execute_run(self, run_id: str, *, customer_id: str) -> dict:
        return self.execution_service.execute_approved(run_id, customer_id=customer_id)
