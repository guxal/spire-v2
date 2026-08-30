# @file Application composition root.
# @domain application
# @status stable
# @adr [[0007-google-ads-provider-ownership]]
# @adr [[0009-capability-projection]]
# @tested-by [[test_public_surfaces.py]]
"""Composition root for public Spire surfaces."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from spire.core import WorkspaceStatusService
from spire.execution import (
    AuthorityService,
    BudgetCompiler,
    ExecutionRunQueryService,
    ExecutionRunService,
    HardPolicyService,
    ProductionRuntime,
)
from spire.google_ads import (
    AccountDiscoveryService,
    CampaignReadService,
    GoogleAdsAuthService,
    GoogleAdsClientProvider,
    ScopedRefreshService,
)
from spire.truth import AccountSnapshotService, EvidenceQueryService


@dataclass(frozen=True, slots=True)
class CustomerServices:
    provider: GoogleAdsClientProvider
    discovery: AccountDiscoveryService
    refresh: ScopedRefreshService
    campaigns: CampaignReadService
    evidence: EvidenceQueryService
    execution: ExecutionRunService


class Application:
    """Build explicit customer-scoped services for CLI and MCP adapters."""

    def __init__(self, workspace, *, provider_factory: Callable | None = None) -> None:
        self.workspace = workspace
        self._provider_factory = provider_factory or GoogleAdsClientProvider.for_customer
        self.runs = ExecutionRunQueryService(workspace)
        self.workspace_status = WorkspaceStatusService(workspace)
        self.auth = GoogleAdsAuthService(
            workspace,
            provider_factory=self._provider_factory,
        )

    def for_customer(self, customer_id: str) -> CustomerServices:
        provider = self._provider_factory(self.workspace, customer_id)
        discovery = AccountDiscoveryService(provider, self.workspace)
        snapshots = AccountSnapshotService(self.workspace)
        return CustomerServices(
            provider=provider,
            discovery=discovery,
            refresh=ScopedRefreshService(provider, self.workspace),
            campaigns=CampaignReadService(discovery, snapshots),
            evidence=EvidenceQueryService(self.workspace, snapshots=snapshots),
            execution=ExecutionRunService(
                self.workspace,
                snapshots=snapshots,
                compiler=BudgetCompiler(self.workspace),
                policy=HardPolicyService(),
                authority=AuthorityService(),
                runtime=ProductionRuntime(provider),
            ),
        )
