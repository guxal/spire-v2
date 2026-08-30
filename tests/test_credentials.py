import json
from datetime import UTC, datetime, timedelta

import pytest

from spire.core import GoogleAdsAuthError, WorkspacePaths
from spire.google_ads.credentials import GoogleAdsCredentialProvider, google_ads_token_cache_path


class _Credentials:
    def __init__(self, *, token=None, refresh_token=None, token_uri=None, client_id=None, client_secret=None, scopes=None, expiry=None):
        self.token = token
        self.refresh_token = refresh_token
        self.token_uri = token_uri
        self.client_id = client_id
        self.client_secret = client_secret
        self.scopes = scopes
        self.expiry = expiry

    def refresh(self, request):
        self.token = "access-secret"
        self.expiry = datetime.now(UTC) + timedelta(hours=1)


def _config():
    return {
        "developer_token": "developer-secret",
        "client_id": "client-id",
        "client_secret": "client-secret",
        "refresh_token": "refresh-secret",
    }


def test_valid_cache_avoids_oauth_refresh(tmp_path):
    path = tmp_path / "google_ads_oauth.json"
    path.write_text(
        json.dumps({"access_token": "cached-secret", "expiry": (datetime.now(UTC) + timedelta(hours=1)).isoformat()}),
        encoding="utf-8",
    )
    provider = GoogleAdsCredentialProvider(
        _config(), token_cache_path=path, credentials_factory=_Credentials
    )
    credentials = provider.get_credentials()
    assert credentials.token == "cached-secret"
    assert provider.cache_hits == 1
    assert provider.refresh_count == 0


def test_expired_cache_refreshes_once_and_replaces_atomically(tmp_path):
    path = tmp_path / "google_ads_oauth.json"
    path.write_text(
        json.dumps({"access_token": "expired-secret", "expiry": (datetime.now(UTC) - timedelta(minutes=1)).isoformat()}),
        encoding="utf-8",
    )
    provider = GoogleAdsCredentialProvider(
        _config(), token_cache_path=path, credentials_factory=_Credentials
    )
    provider.get_credentials()
    provider.get_credentials()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["access_token"] == "access-secret"
    assert provider.refresh_count == 1
    assert oct(path.stat().st_mode & 0o777) == "0o600"


def test_missing_credential_config_fails_with_stable_code(tmp_path):
    provider = GoogleAdsCredentialProvider(
        {"developer_token": "only-token"},
        token_cache_path=tmp_path / "google_ads_oauth.json",
        credentials_factory=_Credentials,
    )
    with pytest.raises(GoogleAdsAuthError, match="AUTH_NOT_CONFIGURED"):
        provider.get_credentials()


def test_cache_path_is_canonical_account_scoped_path(tmp_path):
    path = google_ads_token_cache_path(WorkspacePaths(tmp_path), "123-456-7890")
    assert path == tmp_path / ".spire/customers/1234567890/cache/google_ads_oauth.json"
