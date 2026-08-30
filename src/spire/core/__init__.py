# @file Core contract exports.
# @domain core
# @status stable
"""Core identity and workspace contracts."""

from .errors import (
    ArtifactIdentityError,
    ArtifactNotFoundError,
    GoogleAdsAuthError,
    ScopeMismatchError,
    SpireError,
)
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
from .workspace import (
    PROJECT_ROOT_ENV,
    WorkspacePaths,
    WorkspaceStatusService,
    initialize_customer_workspace,
    resolve_project_root,
)

__all__ = [
    "PROJECT_ROOT_ENV",
    "ArtifactIdentityError",
    "ArtifactNotFoundError",
    "GoogleAdsAuthError",
    "ScopeMismatchError",
    "SpireError",
    "WorkspacePaths",
    "WorkspaceStatusService",
    "assert_loaded_scope",
    "assert_resolved_below_root",
    "canonical_hash",
    "initialize_customer_workspace",
    "resolve_project_root",
    "safe_artifact_file",
    "safe_child",
    "safe_scoped_root",
    "validate_artifact_id",
    "validate_customer_id",
    "validate_google_ads_id",
]
