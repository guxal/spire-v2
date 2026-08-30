from types import SimpleNamespace

import pytest
import yaml

from spire.core import GoogleAdsAuthError, WorkspacePaths
from spire.google_ads.auth_service import GoogleAdsAuthService


def _write_config(path, *, refresh_token=None):
    payload = {
        "developer_token": "developer-secret",
        "client_id": "client-id",
        "client_secret": "client-secret",
        "login_customer_id": "123-456-7890",
    }
    if refresh_token:
        payload["refresh_token"] = refresh_token
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")


def test_login_persists_refresh_token_without_printing_it(tmp_path, capsys):
    config_path = tmp_path / "config/google-ads.yaml"
    _write_config(config_path)
    service = GoogleAdsAuthService(
        WorkspacePaths(tmp_path),
        config_path=config_path,
        oauth_runner=lambda **kwargs: {"refresh_token": "refresh-secret"},
    )
    result = service.login()
    print(result["authentication"])
    output = capsys.readouterr().out
    assert "refresh-secret" not in output
    assert yaml.safe_load(config_path.read_text(encoding="utf-8"))["refresh_token"] == "refresh-secret"
    assert oct(config_path.stat().st_mode & 0o777) == "0o600"


def test_login_does_not_overwrite_existing_refresh_token(tmp_path):
    config_path = tmp_path / "config/google-ads.yaml"
    _write_config(config_path, refresh_token="existing-refresh")
    service = GoogleAdsAuthService(
        WorkspacePaths(tmp_path),
        config_path=config_path,
        oauth_runner=lambda **kwargs: {"refresh_token": "new-refresh"},
    )
    with pytest.raises(GoogleAdsAuthError, match="AUTH_ALREADY_CONFIGURED"):
        service.login()
    assert "existing-refresh" in config_path.read_text(encoding="utf-8")


def test_status_is_local_only_and_redacted(tmp_path):
    config_path = tmp_path / "config/google-ads.yaml"
    _write_config(config_path, refresh_token="refresh-secret")
    service = GoogleAdsAuthService(WorkspacePaths(tmp_path), config_path=config_path)
    result = service.status()
    serialized = str(result)
    assert result["configured"] == "YES"
    assert result["login_customer_id"] == "1234567890"
    assert "refresh-secret" not in serialized
    assert result["cached_access_token"] == "MISSING"


def test_verify_performs_one_read_and_reports_cache_miss(tmp_path):
    config_path = tmp_path / "config/google-ads.yaml"
    _write_config(config_path, refresh_token="refresh-secret")
    calls = []

    class Service:
        def search_stream(self, **kwargs):
            calls.append(kwargs)
            yield SimpleNamespace(results=[{"customer.id": "1234567890"}])

    class Client:
        def get_service(self, name):
            return Service()

    credential = SimpleNamespace(refresh_count=1, cache_hits=0)
    provider = SimpleNamespace(
        credential_provider=credential,
        login_customer_id="1234567890",
        get_client=lambda: Client(),
    )
    service = GoogleAdsAuthService(
        WorkspacePaths(tmp_path),
        config_path=config_path,
        provider_factory=lambda *args, **kwargs: provider,
    )
    result = service.verify("1234567890")
    assert result["authentication"] == "OK"
    assert result["customer_access"] == "OK"
    assert result["token_cache"] == "MISS"
    assert len(calls) == 1
    assert "mutate" not in calls[0]


def test_malformed_config_fails_with_stable_code(tmp_path):
    config_path = tmp_path / "config/google-ads.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("- not-a-mapping\n", encoding="utf-8")
    service = GoogleAdsAuthService(WorkspacePaths(tmp_path), config_path=config_path)
    with pytest.raises(GoogleAdsAuthError, match="INVALID_CREDENTIAL_CONFIG"):
        service.status()


def test_verify_without_customer_id_picks_from_mcc_accounts(tmp_path):
    config_path = tmp_path / "config/google-ads.yaml"
    _write_config(config_path, refresh_token="refresh-secret")
    calls = []

    class GoogleAdsService:
        def search_stream(self, *, customer_id, query):
            calls.append((customer_id, query))
            yield SimpleNamespace(
                results=[
                    {
                        "customer.id": customer_id,
                        "customer.descriptive_name": f"Account {customer_id}",
                    }
                ]
            )

    class CustomerService:
        def list_accessible_customers(self):
            return SimpleNamespace(resource_names=["customers/111", "customers/222"])

    class Client:
        def get_service(self, name):
            return GoogleAdsService() if name == "GoogleAdsService" else CustomerService()

    credential = SimpleNamespace(refresh_count=0, cache_hits=1)
    provider = SimpleNamespace(
        credential_provider=credential,
        login_customer_id="1234567890",
        get_client=lambda: Client(),
    )
    prompts = []
    output = []
    service = GoogleAdsAuthService(
        WorkspacePaths(tmp_path),
        config_path=config_path,
        provider_factory=lambda *args, **kwargs: provider,
    )
    result = service.verify(
        input_fn=lambda prompt: prompts.append(prompt) or "2",
        output_fn=output.append,
    )
    assert result["customer_id"] == "222"
    assert output[0] == "Available Google Ads accounts:"
    assert "Account 111" in output[1]
    assert prompts == ["Select account number: "]
    assert calls[-1][0] == "222"
