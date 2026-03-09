"""Data models for the weight routing core."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
import uuid


def _new_measurement_id() -> str:
    return uuid.uuid4().hex


@dataclass
class WeightMeasurement:
    """Normalized committed weight measurement."""

    weight_kg: float
    timestamp: datetime
    source_id: str
    measurement_id: str = field(default_factory=_new_measurement_id)
    source_unit: str = "kg"
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "weight_kg": self.weight_kg,
            "timestamp": self.timestamp.isoformat(),
            "source_id": self.source_id,
            "measurement_id": self.measurement_id,
            "source_unit": self.source_unit,
            "raw": self.raw,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WeightMeasurement":
        if not isinstance(payload, dict):
            raise TypeError("WeightMeasurement payload must be a dictionary")

        timestamp = datetime.fromisoformat(payload["timestamp"])
        return cls(
            weight_kg=float(payload["weight_kg"]),
            timestamp=timestamp,
            source_id=payload["source_id"],
            measurement_id=payload.get("measurement_id") or _new_measurement_id(),
            source_unit=payload.get("source_unit", "kg"),
            raw=payload.get("raw", {}) or {},
        )


@dataclass(frozen=True)
class UserProfile:
    """User profile metadata."""

    user_id: str
    display_name: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, str]) -> "UserProfile":
        if not isinstance(payload, dict):
            raise TypeError("UserProfile payload must be a dictionary")
        return cls(user_id=payload["user_id"], display_name=payload["display_name"])


@dataclass(frozen=True)
class MeasurementCandidate:
    """Candidate match produced by evaluating a measurement."""

    user_id: str
    reference_weight_kg: float | None = None
    tolerance_kg: float | None = None


@dataclass
class RouterConfig:
    """Configuration used by the routing engine."""

    history_retention_days: int = 90
    max_history_size: int = 100
    tolerance_percentage: float = 0.04
    min_tolerance_kg: float = 1.5
    max_tolerance_kg: float = 5.0
    variance_window_days: int = 30
    reference_window_days: int = 7
    min_measurements_for_adaptive: int = 5

    def __post_init__(self) -> None:
        int_fields = {
            "history_retention_days": self.history_retention_days,
            "max_history_size": self.max_history_size,
            "variance_window_days": self.variance_window_days,
            "reference_window_days": self.reference_window_days,
            "min_measurements_for_adaptive": self.min_measurements_for_adaptive,
        }
        for field_name, value in int_fields.items():
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"Invalid integer for {field_name}: {value!r}")

        float_fields = {
            "tolerance_percentage": self.tolerance_percentage,
            "min_tolerance_kg": self.min_tolerance_kg,
            "max_tolerance_kg": self.max_tolerance_kg,
        }
        for field_name, value in float_fields.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise TypeError(f"Invalid float for {field_name}: {value!r}")
