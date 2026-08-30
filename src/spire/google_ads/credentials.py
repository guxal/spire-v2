"""OAuth credential ownership and account-scoped access-token caching."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from spire.core import GoogleAdsAuthError, safe_artifact_file

from .config import normalize_login_customer_id

TOKEN_CACHE_FILENAME = "google_ads_oauth.json"
TOKEN_CACHE_SKEW = timedelta(seconds=60)
GOOGLE_ADS_SCOPES = ("https://www.googleapis.com/auth/adwords",)
_REQUIRED_CONFIG = ("developer_token", "client_id", "client_secret", "refresh_token")


def google_ads_token_cache_path(workspace, customer_id: str) -> Path:
    customer_id = normalize_login_customer_id(customer_id)
    if customer_id is None:
        raise GoogleAdsAuthError("INVALID_LOGIN_CUSTOMER")
    return safe_artifact_file(
        workspace.cache(customer_id), "google_ads_oauth", suffix=".json", field="token_cache"
    )


class GoogleAdsCredentialProvider:
    """Create refresh-token credentials and reuse a valid cached access token."""

    def __init__(
        self,
        config: Mapping[str, Any],
        *,
        token_cache_path: Path,
        credentials_factory: Callable[..., Credentials] = Credentials,
        request_factory: Callable[[], Request] = Request,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = dict(config)
        self.token_cache_path = Path(token_cache_path)
        self._credentials_factory = credentials_factory
        self._request_factory = request_factory
        self._now = now or (lambda: datetime.now(UTC))
        self._credentials: Credentials | None = None
        self.cache_hits = 0
        self.cache_misses = 0
        self.refresh_count = 0

    @property
    def token_expiry(self) -> datetime | None:
        return self._credentials.expiry if self._credentials is not None else None

    def get_credentials(self) -> Credentials:
        self._validate_config()
        if self._credentials is not None and _is_current(self._credentials, self._now()):
            return self._credentials
        with _token_cache_lock(self.token_cache_path):
            cached = _read_cached_token(self.token_cache_path, self._now())
            if cached is not None:
                self.cache_hits += 1
                credentials = self._new_credentials(
                    token=cached["access_token"], expiry=cached["expiry"]
                )
            else:
                self.cache_misses += 1
                credentials = self._new_credentials()
                self._refresh(credentials)
                _persist_cached_token(self.token_cache_path, credentials)
            self._credentials = credentials
            return credentials

    def _validate_config(self) -> None:
        if any(not self.config.get(name) for name in _REQUIRED_CONFIG):
            raise GoogleAdsAuthError("AUTH_NOT_CONFIGURED")

    def _new_credentials(self, *, token: str | None = None, expiry: datetime | None = None):
        return self._credentials_factory(
            token=token,
            refresh_token=str(self.config["refresh_token"]),
            token_uri=str(self.config.get("token_uri") or "https://accounts.google.com/o/oauth2/token"),
            client_id=str(self.config["client_id"]),
            client_secret=str(self.config["client_secret"]),
            scopes=list(self.config.get("scopes") or GOOGLE_ADS_SCOPES),
            expiry=_google_expiry(expiry),
        )

    def _refresh(self, credentials: Credentials) -> None:
        self.refresh_count += 1
        try:
            credentials.refresh(self._request_factory())
        except Exception as exc:
            raise GoogleAdsAuthError("OAUTH_REFRESH_FAILED") from exc
        if not credentials.token or credentials.expiry is None:
            raise GoogleAdsAuthError("OAUTH_REFRESH_FAILED")


def read_token_cache(path: Path, *, now: datetime | None = None) -> dict[str, Any] | None:
    """Read only safe token metadata for local status reporting."""

    return _read_cached_token(Path(path), now or datetime.now(UTC), reject_expired=False)


def _read_cached_token(path: Path, now: datetime, *, reject_expired: bool = True) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        token = payload["access_token"]
        expiry = _parse_expiry(payload["expiry"])
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
        return None
    if not isinstance(token, str) or not token:
        return None
    if reject_expired and not _is_before_expiry(expiry, now):
        return None
    return {"access_token": token, "expiry": expiry}


def _persist_cached_token(path: Path, credentials: Credentials) -> None:
    if not credentials.token or credentials.expiry is None:
        raise GoogleAdsAuthError("OAUTH_REFRESH_FAILED")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "access_token": credentials.token,
        "expiry": _normalize_expiry(credentials.expiry).isoformat(),
    }
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        if temporary.exists():
            temporary.unlink()


@contextmanager
def _token_cache_lock(path: Path) -> Iterator[None]:
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock")
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            os.chmod(lock_path, 0o600)
        except OSError:
            pass
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _is_current(credentials: Credentials, now: datetime) -> bool:
    return bool(credentials.token and credentials.expiry and _is_before_expiry(credentials.expiry, now))


def _is_before_expiry(expiry: datetime, now: datetime) -> bool:
    return _normalize_expiry(expiry) > _normalize_expiry(now) + TOKEN_CACHE_SKEW


def _parse_expiry(value: Any) -> datetime:
    if not isinstance(value, str):
        raise TypeError("TOKEN_CACHE_EXPIRY_INVALID")
    return _normalize_expiry(datetime.fromisoformat(value))


def _normalize_expiry(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _google_expiry(value: datetime | None) -> datetime | None:
    """Google auth currently compares expiry to a naive UTC clock."""

    if value is None:
        return None
    return _normalize_expiry(value).replace(tzinfo=None)
