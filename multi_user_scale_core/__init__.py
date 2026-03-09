"""Core weight routing primitives shared across integrations."""

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
    MIN_MEASUREMENTS_FOR_ADAPTIVE,
    MIN_TOLERANCE_KG,
    MAX_TOLERANCE_KG,
    DEFAULT_TOLERANCE_PERCENTAGE,
    REFERENCE_WINDOW_DAYS,
    TOLERANCE_MULTIPLIER,
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
    "TOLERANCE_MULTIPLIER",
    "UserNotFoundError",
    "VARIANCE_WINDOW_DAYS",
    "WeightMeasurement",
    "UserProfile",
    "WeightRouter",
]
