"""Error types used by the multi-user routing core."""


class RouterError(Exception):
    """Base class for router-related errors."""


class MeasurementValidationError(RouterError):
    """Raised when a weight measurement is invalid."""


class DuplicateMeasurementError(RouterError):
    """Raised when a measurement_id already exists in committed history."""


class MeasurementNotFoundError(RouterError):
    """Raised when an operation references an unknown measurement."""


class UserNotFoundError(RouterError):
    """Raised when an operation references an unknown user."""
