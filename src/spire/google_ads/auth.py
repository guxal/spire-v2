# @file Installed-app OAuth helpers.
# @domain google-ads
# @status stable
# @adr [[0014-google-ads-authentication-bootstrap]]
# @tested-by [[test_auth_service.py]]
"""Installed-app OAuth helpers preserved behind the v2 Google Ads boundary."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

SCOPES = ["https://www.googleapis.com/auth/adwords"]


def run_installed_app_oauth(
    client_secret_file: Path | None = None,
    port: int = 8080,
    *,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> dict[str, Any]:
    from google_auth_oauthlib.flow import InstalledAppFlow

    if client_id and client_secret:
        flow = InstalledAppFlow.from_client_config(
            {
                "installed": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=SCOPES,
        )
    elif client_secret_file is not None:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_file), scopes=SCOPES)
    else:
        raise ValueError("OAUTH_CLIENT_CONFIG_REQUIRED")
    credentials = flow.run_local_server(
        host="localhost",
        port=port,
        authorization_prompt_message="Open this URL in your browser: {url}",
        success_message="OAuth flow completed. Return to the terminal.",
    )
    return {
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "scopes": list(credentials.scopes or []),
    }


def write_google_ads_config(
    output_path: Path,
    developer_token: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    login_customer_id: str | None = None,
) -> None:
    config: dict[str, Any] = {
        "developer_token": developer_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }
    if login_customer_id:
        config["login_customer_id"] = login_customer_id
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output_path.name}.", dir=output_path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            yaml.safe_dump(config, handle, sort_keys=False)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(output_path)
        try:
            os.chmod(output_path, 0o600)
        except OSError:
            pass
    finally:
        if temporary.exists():
            temporary.unlink()
