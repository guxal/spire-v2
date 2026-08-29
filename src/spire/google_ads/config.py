"""Normalized Google Ads configuration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from spire.core import validate_customer_id


@dataclass(frozen=True, slots=True)
class GoogleAdsConfig:
    """Parsed once and immutable for one provider lifecycle."""

    values: Mapping[str, Any]
    login_customer_id: str | None = None

    def __post_init__(self) -> None:
        normalized = dict(self.values)
        login = normalize_login_customer_id(self.login_customer_id)
        if login is None:
            login = normalize_login_customer_id(normalized.get("login_customer_id"))
        if login is None:
            normalized.pop("login_customer_id", None)
        else:
            normalized["login_customer_id"] = login
        object.__setattr__(self, "values", MappingProxyType(normalized))
        object.__setattr__(self, "login_customer_id", login)

    @classmethod
    def from_yaml(cls, config_path: Path, login_customer_id: str | None = None) -> GoogleAdsConfig:
        with Path(config_path).open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
        if not isinstance(payload, dict):
            raise TypeError("GOOGLE_ADS_CONFIG_MUST_BE_A_MAPPING")
        return cls(payload, login_customer_id=login_customer_id)


def normalize_login_customer_id(customer_id: str | None) -> str | None:
    if customer_id is None or not str(customer_id).strip():
        return None
    return validate_customer_id(str(customer_id).replace("-", "").strip())
