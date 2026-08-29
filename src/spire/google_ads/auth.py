"""Installed-app OAuth helpers preserved behind the v2 Google Ads boundary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

SCOPES = ["https://www.googleapis.com/auth/adwords"]


def run_installed_app_oauth(client_secret_file: Path, port: int = 8080) -> dict[str, Any]:
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_file), scopes=SCOPES)
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
        "use_proto_plus": True,
    }
    if login_customer_id:
        config["login_customer_id"] = login_customer_id
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, sort_keys=False)
