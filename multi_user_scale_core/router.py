"""Weight routing core engine."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import math
from collections.abc import Callable
from typing import Any

from .errors import (
    DuplicateMeasurementError,
    MeasurementNotFoundError,
    MeasurementValidationError,
    UserNotFoundError,
)
from .models import MeasurementCandidate, RouterConfig, UserProfile, WeightMeasurement
from .tolerance import calculate_final_tolerance, calculate_reference_weight


class WeightRouter:
    """Route incoming weight measurements to users based on profile history."""

    def __init__(
        self,
        config: RouterConfig | None = None,
        now_provider: Callable[[], datetime] = lambda: datetime.now(tz=timezone.utc),
    ) -> None:
        self._config = config or RouterConfig()
        self._history: dict[str, list[WeightMeasurement]] = {}
        self._measurement_ids: set[str] = set()
        self._users: dict[str, UserProfile] = {}
        self._now = now_provider

    @property
    def config(self) -> RouterConfig:
        return self._config

    def set_config(self, config: RouterConfig) -> None:
        """Replace router config and normalize history against current time."""
        self._config = config
        self._prune_all_histories(self._now())

    @property
    def users(self) -> dict[str, UserProfile]:
        return dict(self._users)

    def get_users(self) -> list[UserProfile]:
        return list(self._users.values())

    def set_users(self, users: list[UserProfile]) -> None:
        """Replace the full set of tracked users.

        Any committed history for users not present in the new list is
        permanently discarded. Callers should persist router state via
        ``to_dict`` before invoking this method if that history may be needed.
        """
        self._users = {user.user_id: user for user in users}
        for user_id in list(self._history):
            if user_id not in self._users:
                dropped = self._history.pop(user_id)
                for m in dropped:
                    self._measurement_ids.discard(m.measurement_id)

    def _prune_history(self, user_id: str, reference_time: datetime) -> None:
        history = self._history.setdefault(user_id, [])
        cutoff = reference_time - timedelta(days=self._config.history_retention_days)
        pruned_history = [
            measurement for measurement in history if measurement.timestamp >= cutoff
        ]
        if len(pruned_history) > self._config.max_history_size:
            pruned_history = pruned_history[-self._config.max_history_size :]
        if len(pruned_history) != len(history):
            kept_ids = {m.measurement_id for m in pruned_history}
            self._measurement_ids -= {
                m.measurement_id for m in history if m.measurement_id not in kept_ids
            }
        self._history[user_id] = pruned_history

    def _prune_all_histories(self, reference_time: datetime) -> None:
        for user_id in list(self._users):
            self._prune_history(user_id, reference_time)

    def _ensure_valid_weight(self, measurement: WeightMeasurement) -> None:
        if not isinstance(measurement.weight_kg, (int, float)):
            raise MeasurementValidationError("Weight is not a number")
        if not math.isfinite(measurement.weight_kg):
            raise MeasurementValidationError("Weight must be a finite number")

    def _ensure_user_exists(self, user_id: str, message: str) -> None:
        if user_id not in self._users:
            raise UserNotFoundError(message)

    def _measurement_exists(self, measurement_id: str) -> bool:
        return measurement_id in self._measurement_ids

    def _insert_measurement(self, user_id: str, measurement: WeightMeasurement) -> None:
        history = self._history.setdefault(user_id, [])
        timestamps = [sample.timestamp for sample in history]
        insert_at = bisect_left(timestamps, measurement.timestamp)
        history.insert(insert_at, measurement)

    def _select_measurement(
        self, user_id: str, measurement_id: str | None
    ) -> tuple[int, WeightMeasurement]:
        history = self._history.get(user_id, [])
        if not history:
            raise MeasurementNotFoundError("No measurements found for user")

        if measurement_id is None:
            return len(history) - 1, history[-1]

        for index, measurement in enumerate(history):
            if measurement.measurement_id == measurement_id:
                return index, measurement
        raise MeasurementNotFoundError("Measurement not found for user")

    def evaluate_measurement(
        self, measurement: WeightMeasurement
    ) -> list[MeasurementCandidate]:
        self._ensure_valid_weight(measurement)
        self._prune_all_histories(measurement.timestamp)

        weighted_candidates: list[tuple[float, MeasurementCandidate]] = []
        no_history_candidates: list[MeasurementCandidate] = []

        for user in self._users.values():
            history = self._history.get(user.user_id, [])
            if not history:
                no_history_candidates.append(MeasurementCandidate(user_id=user.user_id))
                continue

            reference = calculate_reference_weight(
                history,
                measurement.timestamp,
                self._config.reference_window_days,
            )
            if reference is None:
                no_history_candidates.append(MeasurementCandidate(user_id=user.user_id))
                continue

            tolerance = calculate_final_tolerance(
                measurements=history,
                reference_weight=reference,
                reference_time=measurement.timestamp,
                tolerance_percentage=self._config.tolerance_percentage,
                min_tolerance_kg=self._config.min_tolerance_kg,
                min_measurements_for_adaptive=self._config.min_measurements_for_adaptive,
                variance_window_days=self._config.variance_window_days,
            )
            distance = abs(measurement.weight_kg - reference)
            if distance <= tolerance:
                weighted_candidates.append(
                    (
                        distance,
                        MeasurementCandidate(
                            user_id=user.user_id,
                            reference_weight_kg=reference,
                            tolerance_kg=tolerance,
                        ),
                    )
                )

        weighted_candidates.sort(key=lambda item: item[0])
        ordered_matches = [candidate for _, candidate in weighted_candidates]
        return ordered_matches + no_history_candidates

    def record_measurement_for_user(
        self, user_id: str, measurement: WeightMeasurement
    ) -> WeightMeasurement:
        self._ensure_valid_weight(measurement)
        self._ensure_user_exists(user_id, "Unknown user")
        if self._measurement_exists(measurement.measurement_id):
            raise DuplicateMeasurementError(
                "Measurement ID already exists in committed history"
            )

        self._insert_measurement(user_id, measurement)
        self._measurement_ids.add(measurement.measurement_id)
        self._prune_history(user_id, measurement.timestamp)
        return measurement

    def reassign_measurement(
        self,
        from_user_id: str,
        to_user_id: str,
        measurement_id: str | None = None,
    ) -> WeightMeasurement:
        self._ensure_user_exists(from_user_id, "Source user is not configured")
        self._ensure_user_exists(to_user_id, "Target user is not configured")
        self._prune_all_histories(self._now())

        index, measurement = self._select_measurement(from_user_id, measurement_id)
        self._history.setdefault(from_user_id, []).pop(index)
        self._insert_measurement(to_user_id, measurement)
        self._prune_history(to_user_id, measurement.timestamp)
        return measurement

    def remove_measurement(
        self,
        user_id: str,
        measurement_id: str | None = None,
    ) -> WeightMeasurement:
        self._ensure_user_exists(user_id, "Unknown user")
        self._prune_all_histories(self._now())

        index, measurement = self._select_measurement(user_id, measurement_id)
        self._history.setdefault(user_id, []).pop(index)
        self._measurement_ids.discard(measurement.measurement_id)
        return measurement

    def get_user_history(self, user_id: str) -> list[WeightMeasurement]:
        self._ensure_user_exists(user_id, "Unknown user")
        return list(self._history.get(user_id, []))

    def get_user_last_measurement(self, user_id: str) -> WeightMeasurement | None:
        self._ensure_user_exists(user_id, "Unknown user")
        history = self._history.get(user_id, [])
        if not history:
            return None
        return history[-1]

    def to_dict(self) -> dict[str, Any]:
        """Serialise router state to a plain dictionary.

        The ``"now"`` field is a snapshot timestamp recorded for human
        inspection only.  It is **not** consumed by :meth:`from_dict` and
        has no effect on restoration.
        """
        return {
            "config": asdict(self._config),
            "users": [profile.to_dict() for profile in self._users.values()],
            "history": {
                user_id: [sample.to_dict() for sample in samples]
                for user_id, samples in self._history.items()
                if samples
            },
            "now": self._now().isoformat(),
        }

    @classmethod
    def from_dict(
        cls,
        payload: dict[str, Any],
        now_provider: Callable[[], datetime] = lambda: datetime.now(tz=timezone.utc),
    ) -> "WeightRouter":
        if not isinstance(payload, dict):
            raise TypeError("Payload must be a dictionary")

        config_payload = payload.get("config", {})
        if not isinstance(config_payload, dict):
            raise TypeError("Config payload must be a dictionary")

        allowed_config_keys = set(RouterConfig.__dataclass_fields__)
        filtered_config = {
            key: value
            for key, value in config_payload.items()
            if key in allowed_config_keys
        }
        router = cls(config=RouterConfig(**filtered_config), now_provider=now_provider)

        users_payload = payload.get("users", [])
        if not isinstance(users_payload, list):
            raise TypeError("Users payload must be a list")
        router.set_users([UserProfile.from_dict(item) for item in users_payload])

        history_payload = payload.get("history", {})
        if not isinstance(history_payload, dict):
            raise TypeError("History payload must be a dictionary")

        seen_measurement_ids: set[str] = set()
        for user_id, values in history_payload.items():
            if not isinstance(user_id, str):
                raise TypeError("History keys must be user IDs as strings")
            if user_id not in router._users:
                raise ValueError(
                    f"History payload contains user_id '{user_id}' that is not configured"
                )
            if not isinstance(values, list):
                raise TypeError("History measurements must be a list")

            restored_history = [
                WeightMeasurement.from_dict(sample) for sample in values
            ]
            for measurement in restored_history:
                if measurement.measurement_id in seen_measurement_ids:
                    raise ValueError("Duplicate measurement_id in router history")
                seen_measurement_ids.add(measurement.measurement_id)
            router._history[user_id] = sorted(
                restored_history, key=lambda sample: sample.timestamp
            )

        router._measurement_ids = seen_measurement_ids
        return router
