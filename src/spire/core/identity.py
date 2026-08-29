"""Fail-closed identity, path-jail, and canonical hashing primitives."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .errors import ArtifactIdentityError

ARTIFACT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$", re.ASCII)


def validate_artifact_id(value: str, *, field: str = "artifact_id") -> str:
    return _validate_component(value, field=field)


def validate_customer_id(value: str) -> str:
    candidate = str(value)
    if not candidate.isascii() or not candidate.isdigit() or not 1 <= len(candidate) <= 20:
        raise ArtifactIdentityError("INVALID_CUSTOMER_ID")
    return candidate


def validate_google_ads_id(value: str, *, field: str) -> str:
    candidate = str(value)
    if not candidate.isascii() or not candidate.isdigit() or not 1 <= len(candidate) <= 20:
        raise ArtifactIdentityError(f"INVALID_{field.upper()}")
    return candidate


def safe_child(root: Path, artifact_id: str, *, field: str = "artifact_id") -> Path:
    child = Path(root) / validate_artifact_id(artifact_id, field=field)
    assert_resolved_below_root(root, child)
    return child


def safe_scoped_root(root: Path, scope_id: str, *, field: str = "customer_id") -> Path:
    child = Path(root) / _validate_component(scope_id, field=field)
    assert_resolved_below_root(root, child)
    return child


def safe_artifact_file(
    root: Path,
    artifact_id: str,
    *,
    suffix: str = ".json",
    field: str = "artifact_id",
) -> Path:
    if not suffix.startswith(".") or any(token in suffix for token in ("/", "\\", "%")):
        raise ArtifactIdentityError("INVALID_ARTIFACT_SUFFIX")
    candidate = safe_child(root, artifact_id, field=field).with_suffix(suffix)
    assert_resolved_below_root(root, candidate)
    return candidate


def assert_resolved_below_root(root: Path, candidate: Path) -> Path:
    """Reject traversal and symlinked descendants, including existing parents."""

    lexical_root = Path(root).absolute()
    lexical_candidate = Path(candidate).absolute()
    if lexical_root.exists() and lexical_root.is_symlink():
        raise ArtifactIdentityError("PATH_SYMLINK_FORBIDDEN")
    try:
        lexical_candidate.relative_to(lexical_root)
    except ValueError as exc:
        raise ArtifactIdentityError("PATH_SCOPE_VIOLATION") from exc

    current = lexical_candidate
    while current != lexical_root:
        if current.exists() and current.is_symlink():
            raise ArtifactIdentityError("PATH_SYMLINK_FORBIDDEN")
        if current.parent == current:
            raise ArtifactIdentityError("PATH_SCOPE_VIOLATION")
        current = current.parent

    resolved_root = lexical_root.resolve(strict=False)
    resolved_candidate = lexical_candidate.resolve(strict=False)
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ArtifactIdentityError("PATH_SCOPE_VIOLATION") from exc
    return resolved_candidate


def assert_loaded_scope(
    artifact: Mapping[str, Any], requested_scope: Mapping[str, Any], *, artifact_name: str
) -> None:
    for field, expected in requested_scope.items():
        if expected is None:
            continue
        if str(artifact.get(field)) != str(expected):
            raise ArtifactIdentityError(
                f"{artifact_name}: IDENTITY_MISMATCH:{field}:{artifact.get(field)!r}!={expected!r}"
            )


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate_component(value: str, *, field: str) -> str:
    candidate = str(value)
    if not ARTIFACT_ID_PATTERN.fullmatch(candidate):
        raise ArtifactIdentityError(f"INVALID_{field.upper()}")
    return candidate
