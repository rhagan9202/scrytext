"""Custom exceptions for Scry_Ingestor."""


class ScryIngestorError(Exception):
    """Base exception for all Scry_Ingestor errors."""
    pass


class CollectionError(ScryIngestorError):
    """Raised when data collection from source fails."""
    pass


class ValidationError(ScryIngestorError):
    """Raised when data validation fails."""
    pass


class TransformationError(ScryIngestorError):
    """Raised when data transformation fails."""
    pass


class ConfigurationError(ScryIngestorError):
    """Raised when configuration is invalid or missing."""
    pass


class AdapterNotFoundError(ScryIngestorError):
    """Raised when requested adapter is not registered."""
    pass


class AuthenticationError(ScryIngestorError):
    """Raised when API authentication fails."""
    pass
