# @file Core error contracts.
# @domain core
# @status stable
"""Small, dependency-free domain errors."""


class SpireError(Exception):
    """Base class for expected Spire failures."""


class ArtifactIdentityError(SpireError, ValueError):
    """An identity or path failed fail-closed validation."""


class ArtifactNotFoundError(SpireError):
    """A requested finalized artifact does not exist."""


class ScopeMismatchError(SpireError):
    """A requested scope is not certified by the loaded artifact."""


class PublicationError(SpireError):
    """An extraction could not be atomically published."""


class GoogleAdsAuthError(SpireError):
    """A Google Ads authentication or account-access operation failed."""

    def __init__(self, reason_code: str, message: str = "Google Ads authentication failed") -> None:
        self.reason_code = reason_code
        super().__init__(reason_code if message == "Google Ads authentication failed" else message)
