from types import SimpleNamespace

from spire.execution import ChangeKind, CompiledOperation, ProductionRuntime
from spire.google_ads import GoogleAdsClientProvider, GoogleAdsConfig


class _Batch:
    def __init__(self, results):
        self.results = results


class _Service:
    def __init__(self):
        self.calls = []
        self.budget = 12_000_000

    def mutate(self, **kwargs):
        self.calls.append(kwargs)
        if not kwargs["validate_only"]:
            self.budget = kwargs["operations"][0].campaign_budget_operation.update.amount_micros
        return SimpleNamespace()

    def search_stream(self, *, customer_id, query):
        self.calls.append({"customer_id": customer_id, "query": query})
        yield _Batch([{"campaign.id": "101", "campaign_budget.amount_micros": self.budget}])


class _Client:
    def __init__(self):
        self.service = _Service()

    def get_service(self, name):
        assert name == "GoogleAdsService"
        return self.service

    def get_type(self, name):
        assert name == "MutateOperation"
        update = SimpleNamespace(resource_name="", amount_micros=0, update_mask=SimpleNamespace(paths=[]))
        return SimpleNamespace(campaign_budget_operation=SimpleNamespace(update=update))


def test_validate_mutate_and_readback_share_one_provider_client():
    client = _Client()
    provider = GoogleAdsClientProvider(
        GoogleAdsConfig({"developer_token": "token"}), client_factory=lambda _: client
    )
    operation = CompiledOperation(
        "operation_runtime_1", "1234567890", "101", ChangeKind.UPDATE_BUDGET,
        "customers/1234567890/campaignBudgets/9001", 13_000_000, "sha256:snapshot",
    )
    runtime = ProductionRuntime(provider)
    preview = runtime.validate_only(operation)
    sent = runtime.mutate(operation)
    verification = runtime.verify(operation)
    assert preview.status == "PASSED"
    assert sent["status"] == "SENT"
    assert verification.status == "VERIFIED"
    assert provider.get_client() is client
    assert [call["validate_only"] for call in client.service.calls if "validate_only" in call] == [True, False]


def test_semantic_readback_rejects_the_wrong_budget():
    client = _Client()
    provider = GoogleAdsClientProvider(
        GoogleAdsConfig({"developer_token": "token"}), client_factory=lambda _: client
    )
    operation = CompiledOperation(
        "operation_runtime_2", "1234567890", "101", ChangeKind.UPDATE_BUDGET,
        "customers/1234567890/campaignBudgets/9001", 13_000_000, "sha256:snapshot",
    )
    result = ProductionRuntime(provider).verify(operation)
    assert result.status == "FAILED"
    assert result.reason_code == "BUDGET_MISMATCH"
