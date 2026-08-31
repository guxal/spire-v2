from types import SimpleNamespace

from conftest import FakeGoogleAdsService

from spire.core import WorkspacePaths
from spire.execution import BudgetCompiler
from spire.execution.authority import AuthorityService
from spire.execution.policy import HardPolicyService
from spire.execution.runtime import ProductionRuntime
from spire.execution.service import ExecutionRunService
from spire.google_ads import (
    AccountDiscoveryService,
    CampaignReadService,
    GoogleAdsClientProvider,
    GoogleAdsConfig,
    RefreshSpec,
    ScopedRefreshService,
)
from spire.interfaces import DateRange, McpExecutionSurface, TrustedExecutionCli
from spire.truth import AccountSnapshotService


class _MutableService(FakeGoogleAdsService):
    def mutate(self, **request):
        if not request["request"].validate_only:
            update = request["request"].mutate_operations[0].campaign_budget_operation.update
            for row in self.rows:
                if row.get("campaign.id") == "101":
                    row["campaign_budget.amount_micros"] = update.amount_micros
        return SimpleNamespace()


class _MutableClient:
    def __init__(self, rows, calls):
        self.service = _MutableService(rows, calls)

    def get_service(self, name):
        assert name == "GoogleAdsService"
        return self.service

    def get_type(self, name):
        if name == "MutateOperation":
            update = SimpleNamespace(resource_name="", amount_micros=0)
            return SimpleNamespace(campaign_budget_operation=SimpleNamespace(update=update, update_mask=SimpleNamespace(paths=[])))
        assert name == "MutateGoogleAdsRequest"
        return SimpleNamespace(customer_id="", mutate_operations=[], validate_only=False)


def test_fresh_workspace_reaches_verified_without_old_data(campaign_rows, tmp_path):
    customer_id = "1234567890"
    assert not (tmp_path / ".spire" / "customers" / customer_id).exists()
    calls = []
    client = _MutableClient(campaign_rows, calls)
    provider = GoogleAdsClientProvider(
        GoogleAdsConfig({"developer_token": "test-token"}), client_factory=lambda _: client
    )
    workspace = WorkspacePaths(tmp_path)
    refresh = ScopedRefreshService(provider, workspace)
    reads = CampaignReadService(
        AccountDiscoveryService(provider, workspace), AccountSnapshotService(workspace)
    )

    assert not calls
    refresh.refresh(RefreshSpec(customer_id, ("101",), DateRange("2026-08-01", "2026-08-02")))
    current = reads.get(customer_id, "101")
    proposed = current["daily_budget"] + 1
    service = ExecutionRunService(
        workspace,
        snapshots=AccountSnapshotService(workspace),
        compiler=BudgetCompiler(workspace),
        policy=HardPolicyService(),
        authority=AuthorityService(),
        runtime=ProductionRuntime(provider),
    )

    prepared = McpExecutionSurface(service).change_budget(customer_id, "101", proposed, "PRODUCTION")
    assert prepared["state"] == "WAITING_FOR_APPROVAL"
    assert prepared["preview"]["status"] == "PASSED"
    assert prepared["request_sent"] is None

    cli = TrustedExecutionCli(service)
    cli.approve_run(
        prepared["run_id"],
        customer_id=customer_id,
        principal_id="human@example.test",
        affirmation=True,
    )
    completed = cli.execute_run(prepared["run_id"], customer_id=customer_id)

    assert completed["state"] == "VERIFIED"
    assert completed["verification"]["observed"]["daily_budget_micros"] == 13_500_000
    assert (workspace.execution(customer_id) / "runs").is_dir()
    assert not any(
        (tmp_path / name).exists()
        for name in ("data", "actions", "context", "business_memory", "recommendations", "campaign_studio")
    )
