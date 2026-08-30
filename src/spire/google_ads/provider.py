# @file Lazy Google Ads client provider.
# @domain google-ads
# @status stable
# @adr [[0007-google-ads-provider-ownership]]
# @adr [[0014-google-ads-authentication-bootstrap]]
# @tested-by [[test_provider.py]]
"""The sole owner of Google Ads client construction."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from spire.core import GoogleAdsAuthError, validate_customer_id

from .config import GoogleAdsConfig
from .credentials import GoogleAdsCredentialProvider, google_ads_token_cache_path


class GoogleAdsClientProvider:
    """Lazily construct and cache one client within an explicit lifecycle."""

    def __init__(
        self,
        config: GoogleAdsConfig | Mapping[str, Any] | Path | str,
        login_customer_id: str | None = None,
        *,
        client_factory: Callable[[dict[str, Any]], Any] | None = None,
        workspace=None,
        customer_id: str | None = None,
        credential_provider: GoogleAdsCredentialProvider | None = None,
    ) -> None:
        self.config = (
            config
            if isinstance(config, GoogleAdsConfig)
            else GoogleAdsConfig(config, login_customer_id=login_customer_id)
            if isinstance(config, Mapping)
            else GoogleAdsConfig.from_yaml(Path(config), login_customer_id)
        )
        self._client_factory = client_factory
        self._credential_provider = credential_provider
        if self._credential_provider is None and self.config.values.get("refresh_token"):
            if workspace is None or customer_id is None:
                raise GoogleAdsAuthError("INVALID_CREDENTIAL_CONFIG")
            self._credential_provider = GoogleAdsCredentialProvider(
                self.config.values,
                token_cache_path=google_ads_token_cache_path(workspace, customer_id),
            )
        self._client: Any | None = None

    @classmethod
    def for_customer(
        cls,
        workspace,
        customer_id: str,
        *,
        config_path: Path | str | None = None,
        client_factory: Callable[[dict[str, Any]], Any] | None = None,
        ) -> GoogleAdsClientProvider:
        customer_id = validate_customer_id(customer_id)
        path = Path(config_path) if config_path is not None else Path(workspace.project_root) / "config" / "google-ads.yaml"
        return cls(
            path,
            workspace=workspace,
            customer_id=customer_id,
            client_factory=client_factory,
        )

    @property
    def login_customer_id(self) -> str | None:
        return self.config.login_customer_id

    @property
    def credential_provider(self) -> GoogleAdsCredentialProvider | None:
        return self._credential_provider

    def get_client(self) -> Any:
        if self._client is None:
            if self._client_factory is not None:
                self._client = self._client_factory(dict(self.config.values))
                return self._client
            if self._credential_provider is None:
                raise GoogleAdsAuthError("AUTH_NOT_CONFIGURED")
            credentials = self._credential_provider.get_credentials()
            self._client = _build_google_ads_client(dict(self.config.values), credentials)
        return self._client


def _build_google_ads_client(config: dict[str, Any], credentials: Any) -> Any:
    from google.ads.googleads.client import GoogleAdsClient

    return GoogleAdsClient(
        credentials=credentials,
        developer_token=config.get("developer_token"),
        endpoint=config.get("endpoint"),
        login_customer_id=config.get("login_customer_id"),
        logging_config=config.get("logging"),
        linked_customer_id=config.get("linked_customer_id"),
        http_proxy=config.get("http_proxy"),
        use_proto_plus=config.get("use_proto_plus", True),
    )
