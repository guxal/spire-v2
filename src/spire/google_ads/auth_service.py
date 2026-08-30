"""Explicit Google Ads authentication bootstrap and verification."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from spire.core import GoogleAdsAuthError, validate_customer_id

from .auth import run_installed_app_oauth, write_google_ads_config
from .config import default_google_ads_config_path, normalize_login_customer_id
from .credentials import TOKEN_CACHE_SKEW, google_ads_token_cache_path, read_token_cache
from .provider import GoogleAdsClientProvider


class GoogleAdsAuthService:
    def __init__(
        self,
        workspace,
        *,
        config_path: Path | str | None = None,
        oauth_runner: Callable | None = None,
        provider_factory: Callable | None = None,
    ):
        self.workspace = workspace
        self.config_path = Path(config_path) if config_path else default_google_ads_config_path(workspace.project_root)
        self._oauth_runner = oauth_runner or run_installed_app_oauth
        self._provider_factory = provider_factory or GoogleAdsClientProvider.for_customer

    def login(self, *, port: int = 8080) -> dict[str, str]:
        config = self._load_config(required=True)
        _require_config(config, ("developer_token", "client_id", "client_secret"))
        if config.get("refresh_token"):
            raise GoogleAdsAuthError("AUTH_ALREADY_CONFIGURED")
        try:
            oauth = self._oauth_runner(
                client_id=str(config["client_id"]),
                client_secret=str(config["client_secret"]),
                port=port,
            )
        except GoogleAdsAuthError:
            raise
        except Exception as exc:
            raise GoogleAdsAuthError("OAUTH_REFRESH_FAILED") from exc
        refresh_token = oauth.get("refresh_token") if isinstance(oauth, dict) else None
        if not refresh_token:
            raise GoogleAdsAuthError("OAUTH_REFRESH_FAILED")
        write_google_ads_config(
            self.config_path,
            developer_token=str(config["developer_token"]),
            client_id=str(config["client_id"]),
            client_secret=str(config["client_secret"]),
            refresh_token=str(refresh_token),
            login_customer_id=_normalized_login(config.get("login_customer_id")),
        )
        return {"authentication": "OK", "config": "UPDATED", "refresh_token": "NOT_DISPLAYED"}

    def status(self) -> dict[str, str | None]:
        config = self._load_config(required=False)
        values = {name: "PRESENT" if config.get(name) else "MISSING" for name in (
            "developer_token", "client_id", "client_secret", "refresh_token"
        )}
        login = _normalized_login(config.get("login_customer_id")) if config.get("login_customer_id") else None
        cached = read_token_cache(
            google_ads_token_cache_path(self.workspace, login), now=datetime.now(UTC)
        ) if login else None
        expiry = cached["expiry"].isoformat() if cached else None
        valid = (
            "YES"
            if cached and cached["expiry"] > datetime.now(UTC) + TOKEN_CACHE_SKEW
            else "NO"
        )
        configured = all(values[name] == "PRESENT" for name in values) and login is not None
        return {
            "configured": "YES" if configured else "NO",
            **values,
            "login_customer_id": login or "MISSING",
            "cached_access_token": "PRESENT" if cached else "MISSING",
            "cached_token_valid": valid,
            "cached_token_expiry": expiry,
        }

    def verify(self, customer_id: str) -> dict[str, str]:
        customer_id = validate_customer_id(customer_id)
        config = self._load_config(required=True)
        _require_config(config, ("developer_token", "client_id", "client_secret", "refresh_token"))
        provider = self._provider_factory(
            self.workspace, customer_id, config_path=self.config_path
        )
        credential_provider = provider.credential_provider
        if credential_provider is None:
            raise GoogleAdsAuthError("AUTH_NOT_CONFIGURED")
        refresh_before = credential_provider.refresh_count
        cache_hit_before = credential_provider.cache_hits
        try:
            client = provider.get_client()
            service = client.get_service("GoogleAdsService")
            query = "SELECT customer.id FROM customer LIMIT 1"
            rows = []
            for batch in service.search_stream(customer_id=customer_id, query=query):
                rows.extend(batch.results)
        except GoogleAdsAuthError:
            raise
        except Exception as exc:
            code = "CUSTOMER_ACCESS_DENIED" if _looks_like_access_denial(exc) else "PROVIDER_UNAVAILABLE"
            raise GoogleAdsAuthError(code) from exc
        if not rows:
            raise GoogleAdsAuthError("CUSTOMER_ACCESS_DENIED")
        return {
            "authentication": "OK",
            "customer_access": "OK",
            "customer_id": customer_id,
            "login_customer_id": provider.login_customer_id or "MISSING",
            "oauth_refresh_performed": "YES" if credential_provider.refresh_count > refresh_before else "NO",
            "token_cache": "HIT" if credential_provider.cache_hits > cache_hit_before else "MISS",
        }

    def _load_config(self, *, required: bool) -> dict[str, Any]:
        if not self.config_path.exists():
            if required:
                raise GoogleAdsAuthError("AUTH_NOT_CONFIGURED")
            return {}
        try:
            payload = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise GoogleAdsAuthError("INVALID_CREDENTIAL_CONFIG") from exc
        if not isinstance(payload, dict):
            raise GoogleAdsAuthError("INVALID_CREDENTIAL_CONFIG")
        return payload


def _require_config(config: dict[str, Any], fields: tuple[str, ...]) -> None:
    if any(not config.get(field) for field in fields):
        raise GoogleAdsAuthError("INVALID_CREDENTIAL_CONFIG")


def _normalized_login(value: Any) -> str | None:
    try:
        return normalize_login_customer_id(value)
    except (TypeError, ValueError) as exc:
        raise GoogleAdsAuthError("INVALID_LOGIN_CUSTOMER") from exc


def _looks_like_access_denial(exc: Exception) -> bool:
    text = str(exc).upper()
    return any(value in text for value in ("PERMISSION_DENIED", "USER_PERMISSION_DENIED", "CUSTOMER_NOT_FOUND"))
