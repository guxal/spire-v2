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
