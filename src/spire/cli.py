"""Small command-line entrypoint for explicit authentication bootstrap."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from spire.core import GoogleAdsAuthError, WorkspacePaths
from spire.google_ads.auth_service import GoogleAdsAuthService


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    service = GoogleAdsAuthService(WorkspacePaths(Path(args.project_root)))
    try:
        if args.action == "login":
            _print(service.login(port=args.port))
        elif args.action == "status":
            _print(service.status())
        else:
            _print(service.verify(args.customer_id))
    except GoogleAdsAuthError as exc:
        print(f"error: {exc.reason_code}", file=sys.stderr)
        return 1
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spire")
    parser.add_argument("--project-root", default=".", help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="group", required=True)
    auth = commands.add_parser("auth")
    google_ads = auth.add_subparsers(dest="provider", required=True)
    google = google_ads.add_parser("google-ads")
    actions = google.add_subparsers(dest="action", required=True)
    login = actions.add_parser("login")
    login.add_argument("--port", type=int, default=8080)
    actions.add_parser("status")
    verify = actions.add_parser("verify")
    verify.add_argument("--customer-id", required=True)
    return parser


def _print(values: dict) -> None:
    for key, value in values.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    raise SystemExit(main())
