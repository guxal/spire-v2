"""Core identity and workspace contracts."""

from .errors import ArtifactIdentityError, ArtifactNotFoundError, ScopeMismatchError, SpireError
from .identity import (
    assert_loaded_scope,
    assert_resolved_below_root,
    canonical_hash,
    safe_artifact_file,
    safe_child,
    safe_scoped_root,
    validate_artifact_id,
    validate_customer_id,
    validate_google_ads_id,
)
from .workspace import WorkspacePaths, initialize_customer_workspace

__all__ = [
    "ArtifactIdentityError",
    "ArtifactNotFoundError",
    "ScopeMismatchError",
    "SpireError",
    "WorkspacePaths",
    "assert_loaded_scope",
    "assert_resolved_below_root",
    "canonical_hash",
    "initialize_customer_workspace",
    "safe_artifact_file",
    "safe_child",
    "safe_scoped_root",
    "validate_artifact_id",
    "validate_customer_id",
    "validate_google_ads_id",
]
