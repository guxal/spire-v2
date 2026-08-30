# @file Canonical customer-scoped runtime workspace.
# @domain core
# @status stable
# @adr [[0006-account-scoped-workspace]]
# @tested-by [[test_workspace.py]]
"""Canonical account-scoped runtime roots."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ArtifactIdentityError
from .identity import assert_resolved_below_root, safe_child, safe_scoped_root, validate_customer_id

PROJECT_ROOT_ENV = "SPIRE_PROJECT_ROOT"


@dataclass(frozen=True, slots=True)
class WorkspacePaths:
    """The only authority for deriving account runtime roots."""

    project_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_root", Path(self.project_root).expanduser().resolve())

    def customer_root(self, customer_id: str) -> Path:
        if not isinstance(customer_id, str):
            raise ArtifactIdentityError("INVALID_CUSTOMER_ID")
        normalized = validate_customer_id(customer_id)
        spire_root = self.project_root / ".spire"
        customers_root = spire_root / "customers"
        assert_resolved_below_root(self.project_root, spire_root)
        assert_resolved_below_root(self.project_root, customers_root)
        return safe_scoped_root(customers_root, normalized)

    def config(self, customer_id: str) -> Path:
        return self._category(customer_id, "config")

    def truth(self, customer_id: str) -> Path:
        return self._category(customer_id, "truth")

    def knowledge(self, customer_id: str) -> Path:
        return self._category(customer_id, "knowledge")

    def execution(self, customer_id: str) -> Path:
        return self._category(customer_id, "execution")

    def cache(self, customer_id: str) -> Path:
        return self._category(customer_id, "cache")

    def customer_ids(self) -> tuple[str, ...]:
        """Return existing customer workspaces without deriving paths elsewhere."""

        root = self.project_root / ".spire" / "customers"
        if not root.is_dir():
            return ()
        return tuple(
            sorted(
                path.name
                for path in root.iterdir()
                if path.is_dir() and path.name.isascii() and path.name.isdigit()
            )
        )

    def _category(self, customer_id: str, category: str) -> Path:
        return safe_child(self.customer_root(customer_id), category, field="workspace_category")


class WorkspaceStatusService:
    """Return a safe public projection of the active workspace."""

    def __init__(self, workspace: WorkspacePaths) -> None:
        self.workspace = workspace

    def status(self) -> dict[str, Any]:
        customer_ids = self.workspace.customer_ids()
        return {
            "project_root": str(self.workspace.project_root),
            "customer_root_pattern": str(
                self.workspace.project_root / ".spire" / "customers" / "<customer_id>"
            ),
            "configured_customer_count": len(customer_ids),
            "execution_store_available": (
                "YES"
                if any(self.workspace.execution(customer_id).is_dir() for customer_id in customer_ids)
                else "NO"
            ),
        }


def resolve_project_root(
    explicit: str | Path | None = None,
    *,
    environment: Mapping[str, str] | None = None,
) -> Path:
    """Resolve one canonical workspace root without depending on the invocation cwd by default."""

    env = os.environ if environment is None else environment
    configured = explicit if explicit not in (None, "") else env.get(PROJECT_ROOT_ENV)
    if configured not in (None, ""):
        return Path(configured).expanduser().resolve()

    source_root = _source_project_root()
    if source_root is None:
        raise ValueError("PROJECT_ROOT_REQUIRED")
    return source_root


def _source_project_root() -> Path | None:
    source_file = Path(__file__).resolve()
    for candidate in source_file.parents:
        if (candidate / "pyproject.toml").is_file() and (
            candidate / "src" / "spire"
        ).is_dir():
            return candidate
    return None


def initialize_customer_workspace(paths: WorkspacePaths, customer_id: str) -> Path:
    """Create the canonical roots for a customer and nothing else."""

    root = paths.customer_root(customer_id)
    for category in (paths.config, paths.truth, paths.knowledge, paths.execution, paths.cache):
        category(customer_id).mkdir(parents=True, exist_ok=True)
    return root
