"""Core weight routing primitives shared across integrations."""

__version__ = "0.1.1"

from .errors import (
    DuplicateMeasurementError,
    MeasurementNotFoundError,
    MeasurementValidationError,
    RouterError,
    UserNotFoundError,
)
from .models import (
    MeasurementCandidate,
    RouterConfig,
    WeightMeasurement,
    UserProfile,
)
from .router import WeightRouter
from .tolerance import (
    DEFAULT_TOLERANCE_PERCENTAGE,
    MAX_TOLERANCE_KG,
    MIN_MEASUREMENTS_FOR_ADAPTIVE,
    MIN_TOLERANCE_KG,
    REFERENCE_WINDOW_DAYS,
    VARIANCE_WINDOW_DAYS,
)

__all__ = [
    "DEFAULT_TOLERANCE_PERCENTAGE",
    "DuplicateMeasurementError",
    "MeasurementCandidate",
    "MeasurementNotFoundError",
    "MeasurementValidationError",
    "MAX_TOLERANCE_KG",
    "MIN_TOLERANCE_KG",
    "MIN_MEASUREMENTS_FOR_ADAPTIVE",
    "REFERENCE_WINDOW_DAYS",
    "RouterConfig",
    "RouterError",
    "UserNotFoundError",
    "VARIANCE_WINDOW_DAYS",
    "WeightMeasurement",
    "UserProfile",
    "WeightRouter",
]
