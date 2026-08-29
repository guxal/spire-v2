from __future__ import annotations

from dataclasses import dataclass

import pytest

from spire.core import WorkspacePaths
from spire.google_ads import GoogleAdsClientProvider, GoogleAdsConfig


@dataclass
class Batch:
    results: list[dict]


class FakeGoogleAdsService:
    def __init__(self, rows: list[dict], calls: list[str]) -> None:
        self.rows = rows
        self.calls = calls

    def search_stream(self, *, customer_id: str, query: str):
        self.calls.append(query)
        if "FROM customer LIMIT" in query:
            yield Batch(
                [
                    {
                        "customer.id": customer_id,
                        "customer.descriptive_name": "Example Account",
                        "customer.currency_code": "USD",
                        "customer.time_zone": "America/Bogota",
                    }
                ]
            )
        else:
            yield Batch(list(self.rows))


class FakeClient:
    def __init__(self, rows: list[dict], calls: list[str]) -> None:
        self.service = FakeGoogleAdsService(rows, calls)

    def get_service(self, name: str):
        assert name == "GoogleAdsService"
        return self.service


@pytest.fixture
def campaign_rows() -> list[dict]:
    return [
        {
            "customer.id": "1234567890",
            "customer.descriptive_name": "Example Account",
            "customer.currency_code": "USD",
            "customer.time_zone": "America/Bogota",
            "campaign.id": "101",
            "campaign.name": "Search - Brand",
            "campaign.status": "ENABLED",
            "campaign.serving_status": "SERVING",
            "campaign.advertising_channel_type": "SEARCH",
            "campaign.campaign_budget": "customers/1234567890/campaignBudgets/9001",
            "campaign_budget.amount_micros": 12500000,
        },
        {
            "customer.id": "1234567890",
            "customer.descriptive_name": "Example Account",
            "customer.currency_code": "USD",
            "customer.time_zone": "America/Bogota",
            "campaign.id": "202",
            "campaign.name": "Shopping - Core",
            "campaign.status": "PAUSED",
            "campaign.serving_status": "NONE",
            "campaign.advertising_channel_type": "SHOPPING",
            "campaign.campaign_budget": "customers/1234567890/campaignBudgets/9002",
            "campaign_budget.amount_micros": 20000000,
        },
    ]


@pytest.fixture
def fake_runtime(tmp_path, campaign_rows):
    calls: list[str] = []
    client = FakeClient(campaign_rows, calls)
    provider = GoogleAdsClientProvider(
        GoogleAdsConfig({"developer_token": "token", "login_customer_id": "123-456-7890"}),
        client_factory=lambda _: client,
    )
    workspace = WorkspacePaths(tmp_path)
    return workspace, provider, calls
