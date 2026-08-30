from __future__ import annotations

import os
from pathlib import Path

import pytest

from spire.core import (
    PROJECT_ROOT_ENV,
    ArtifactIdentityError,
    WorkspacePaths,
    WorkspaceStatusService,
    initialize_customer_workspace,
    resolve_project_root,
)

ROOT = Path(__file__).parents[1].resolve()


def test_workspace_paths_are_exact_and_customer_scoped(tmp_path):
    paths = WorkspacePaths(tmp_path)
    assert paths.customer_root("123") == tmp_path / ".spire/customers/123"
    assert paths.config("123") == tmp_path / ".spire/customers/123/config"
    assert paths.truth("123") == tmp_path / ".spire/customers/123/truth"
    assert paths.knowledge("123") == tmp_path / ".spire/customers/123/knowledge"
    assert paths.execution("123") == tmp_path / ".spire/customers/123/execution"
    assert paths.cache("123") == tmp_path / ".spire/customers/123/cache"


@pytest.mark.parametrize("customer_id", ["", "../123", "123/456", "abc", "123\\456"])
def test_invalid_customer_id_is_rejected(tmp_path, customer_id):
    with pytest.raises(ArtifactIdentityError):
        WorkspacePaths(tmp_path).customer_root(customer_id)


def test_symlink_escape_is_rejected(tmp_path):
    paths = WorkspacePaths(tmp_path)
    (tmp_path / ".spire").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, tmp_path / ".spire/customers")
    with pytest.raises(ArtifactIdentityError):
        paths.customer_root("123")


def test_sibling_customer_isolation(tmp_path):
    paths = WorkspacePaths(tmp_path)
    assert paths.truth("123").parent != paths.truth("456").parent
    assert paths.truth("123").parts[-2:] == ("123", "truth")
    assert paths.truth("456").parts[-2:] == ("456", "truth")


def test_project_root_resolution_is_explicit_then_environment_then_source(tmp_path):
    explicit = tmp_path / "explicit"
    configured = tmp_path / "configured"

    assert resolve_project_root(explicit, environment={PROJECT_ROOT_ENV: str(configured)}) == (
        explicit.resolve()
    )
    assert resolve_project_root(environment={PROJECT_ROOT_ENV: str(configured)}) == (
        configured.resolve()
    )
    assert resolve_project_root(environment={}) == ROOT


def test_default_project_root_does_not_follow_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert resolve_project_root(environment={}) == ROOT


def test_workspace_status_is_safe_and_reports_execution_store(tmp_path):
    paths = WorkspacePaths(tmp_path)
    initialize_customer_workspace(paths, "1234567890")

    status = WorkspaceStatusService(paths).status()

    assert status == {
        "project_root": str(tmp_path.resolve()),
        "customer_root_pattern": str(
            tmp_path.resolve() / ".spire" / "customers" / "<customer_id>"
        ),
        "configured_customer_count": 1,
        "execution_store_available": "YES",
    }
