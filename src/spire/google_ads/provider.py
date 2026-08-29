"""The sole owner of Google Ads client construction."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .config import GoogleAdsConfig


class GoogleAdsClientProvider:
    """Lazily construct and cache one client within an explicit lifecycle."""

    def __init__(
        self,
        config: GoogleAdsConfig | Mapping[str, Any] | Path | str,
        login_customer_id: str | None = None,
        *,
        client_factory: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        self.config = (
            config
            if isinstance(config, GoogleAdsConfig)
            else GoogleAdsConfig(config, login_customer_id=login_customer_id)
            if isinstance(config, Mapping)
            else GoogleAdsConfig.from_yaml(Path(config), login_customer_id)
        )
        self._client_factory = client_factory
        self._client: Any | None = None

    @property
    def login_customer_id(self) -> str | None:
        return self.config.login_customer_id

    def get_client(self) -> Any:
        if self._client is None:
            factory = self._client_factory or _default_client_factory
            self._client = factory(dict(self.config.values))
        return self._client


def _default_client_factory(config: dict[str, Any]) -> Any:
    from google.ads.googleads.client import GoogleAdsClient

    return GoogleAdsClient.load_from_dict(config)
