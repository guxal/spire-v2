from types import SimpleNamespace

from spire.execution import ChangeKind, CompiledOperation, ProductionRuntime
from spire.execution.runtime import _negative_keyword_operation, _search_campaign_operations
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
        request = kwargs["request"]
        if not request.validate_only:
            self.budget = request.mutate_operations[0].campaign_budget_operation.update.amount_micros
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
        if name == "MutateOperation":
            update = SimpleNamespace(resource_name="", amount_micros=0)
            return SimpleNamespace(campaign_budget_operation=SimpleNamespace(update=update, update_mask=SimpleNamespace(paths=[])))
        assert name == "MutateGoogleAdsRequest"
        return SimpleNamespace(customer_id="", mutate_operations=[], validate_only=False)


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
    assert [call["request"].validate_only for call in client.service.calls if "request" in call] == [True, False]


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


class _Node:
    def __init__(self):
        self.paths = []

    def __getattr__(self, name):
        if name in {"headlines", "descriptions", "final_urls", "mutate_operations"}:
            value = []
        else:
            value = _Node()
        setattr(self, name, value)
        return value

    def SetInParent(self):
        self.is_present = True


class _Enums:
    def __getattr__(self, name):
        return self

    def __getitem__(self, name):
        return name

    def __getattribute__(self, name):
        if name.isupper():
            return name
        return object.__getattribute__(self, name)


class _OperationClient:
    enums = _Enums()

    def get_type(self, name):
        return _Node()


def test_new_google_ads_operations_are_composite_and_campaign_is_paused():
    operation = CompiledOperation(
        "operation_create_1",
        "1234567890",
        "",
        ChangeKind.CREATE_SEARCH_CAMPAIGN,
        "",
        10_000_000,
        "sha256:snapshot",
        payload={
            "campaign_name": "Paused Search",
            "bidding_strategy": "MAXIMIZE_CLICKS",
            "geo_target_ids": ["2170"],
            "language_criterion_ids": ["1003"],
            "budget_resource_name": "customers/1234567890/campaignBudgets/-1",
            "campaign_resource_name": "customers/1234567890/campaigns/-2",
            "ad_groups": [{"name": "Core", "keywords": [{"text": "roof repair", "match_type": "PHRASE"}], "headlines": ["Roof repair", "Local roofers", "Request quote"], "descriptions": ["Repair service.", "Request a quote."], "final_url": "https://example.test/roof"}],
        },
    )
    client = _OperationClient()
    operations = _search_campaign_operations(client, operation)

    assert len(operations) == 7
    assert operations[0].campaign_budget_operation.create.name.startswith("Spire operation_create_1")
    assert operations[1].campaign_operation.create.status == "PAUSED"
    assert operations[1].campaign_operation.create.campaign_budget.endswith("/-1")

    negative = CompiledOperation(
        "operation_negative_1", "1234567890", "101", ChangeKind.ADD_NEGATIVE_KEYWORD,
        "", 0, "sha256:snapshot", payload={"text": "free", "match_type": "EXACT", "scope": "CAMPAIGN", "ad_group_id": ""},
    )
    criterion = _negative_keyword_operation(client, negative)
    assert criterion.campaign_criterion_operation.create.negative is True
    assert criterion.campaign_criterion_operation.create.keyword.text == "free"
