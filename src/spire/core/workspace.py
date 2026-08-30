"""Canonical account-scoped runtime roots."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .errors import ArtifactIdentityError
from .identity import assert_resolved_below_root, safe_child, safe_scoped_root, validate_customer_id


@dataclass(frozen=True, slots=True)
class WorkspacePaths:
    """The only authority for deriving account runtime roots."""

    project_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_root", Path(self.project_root).absolute())

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


def initialize_customer_workspace(paths: WorkspacePaths, customer_id: str) -> Path:
    """Create the canonical roots for a customer and nothing else."""

    root = paths.customer_root(customer_id)
    for category in (paths.config, paths.truth, paths.knowledge, paths.execution, paths.cache):
        category(customer_id).mkdir(parents=True, exist_ok=True)
    return root
