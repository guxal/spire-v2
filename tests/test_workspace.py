from __future__ import annotations

import os

import pytest

from spire.core import ArtifactIdentityError, WorkspacePaths


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
