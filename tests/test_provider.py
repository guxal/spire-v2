from __future__ import annotations

from spire.google_ads import GoogleAdsClientProvider, GoogleAdsConfig


def test_provider_normalizes_once_and_constructs_lazily():
    calls = []
    provider = GoogleAdsClientProvider(
        GoogleAdsConfig({"developer_token": "x", "login_customer_id": "111-222"}),
        client_factory=lambda config: calls.append(config) or object(),
    )
    assert calls == []
    first = provider.get_client()
    second = provider.get_client()
    assert first is second
    assert len(calls) == 1
    assert calls[0]["login_customer_id"] == "111222"
    assert provider.login_customer_id == "111222"


def test_provider_instances_are_isolated():
    clients = []
    first = GoogleAdsClientProvider(
        GoogleAdsConfig({"developer_token": "one"}),
        client_factory=lambda config: clients.append(("one", config)) or object(),
    )
    second = GoogleAdsClientProvider(
        GoogleAdsConfig({"developer_token": "two"}),
        client_factory=lambda config: clients.append(("two", config)) or object(),
    )
    assert first.get_client() is not second.get_client()
    assert [item[0] for item in clients] == ["one", "two"]
