class LogVaultError(Exception):
    """Base exception for LogVault errors."""


class DownloadCancelled(LogVaultError):
    """Raised when the user cancels an active download."""


class ConfigurationError(LogVaultError):
    """Raised when required configuration is missing or invalid."""


class WarcraftLogsError(LogVaultError):
    """Raised when the Warcraft Logs API returns an error."""


class GraphQLError(WarcraftLogsError):
    """Raised when the GraphQL response contains errors."""
