from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from multi_user_scale_core import (
    DuplicateMeasurementError,
    RouterConfig,
    UserProfile,
    WeightMeasurement,
    WeightRouter,
)


def _measurement(
    measurement_id: str,
    weight_kg: float,
    days_ago: int,
    source_id: str = "sensor.scale",
) -> WeightMeasurement:
    return WeightMeasurement(
        measurement_id=measurement_id,
        weight_kg=weight_kg,
        timestamp=datetime.now(tz=timezone.utc) - timedelta(days=days_ago),
        source_id=source_id,
    )


def test_evaluate_measurement_returns_matches_and_no_history_candidates() -> None:
    router = WeightRouter()
    router.set_users(
        [
            UserProfile(user_id="alice", display_name="Alice"),
            UserProfile(user_id="bob", display_name="Bob"),
            UserProfile(user_id="charlie", display_name="Charlie"),
        ]
    )
    for offset, weight in enumerate([75.0, 75.2, 74.9, 75.1, 75.0]):
        router.record_measurement_for_user(
            "alice",
            _measurement(f"alice-{offset}", weight, 5 - offset),
        )
    for offset, weight in enumerate([90.0, 89.8, 90.1, 89.9, 90.2]):
        router.record_measurement_for_user(
            "bob",
            _measurement(f"bob-{offset}", weight, 5 - offset),
        )

    candidates = router.evaluate_measurement(
        WeightMeasurement(
            measurement_id="incoming",
            weight_kg=75.1,
            timestamp=datetime.now(tz=timezone.utc),
            source_id="sensor.scale",
        )
    )

    assert [candidate.user_id for candidate in candidates] == ["alice", "charlie"]
    assert candidates[0].reference_weight_kg is not None
    assert candidates[0].tolerance_kg is not None
    assert candidates[1].reference_weight_kg is None
    assert candidates[1].tolerance_kg is None


def test_measurement_mutations_support_measurement_id_and_latest_fallback() -> None:
    router = WeightRouter()
    router.set_users(
        [
            UserProfile(user_id="alice", display_name="Alice"),
            UserProfile(user_id="bob", display_name="Bob"),
        ]
    )
    first = _measurement("m1", 75.0, 2)
    latest = _measurement("m2", 75.5, 1)
    router.record_measurement_for_user("alice", first)
    router.record_measurement_for_user("alice", latest)

    reassigned = router.reassign_measurement("alice", "bob")
    assert reassigned.measurement_id == "m2"
    assert [m.measurement_id for m in router.get_user_history("alice")] == ["m1"]
    assert [m.measurement_id for m in router.get_user_history("bob")] == ["m2"]

    removed = router.remove_measurement("alice", "m1")
    assert removed.measurement_id == "m1"
    assert router.get_user_history("alice") == []


def test_duplicate_measurement_id_is_rejected_globally() -> None:
    router = WeightRouter(
        config=RouterConfig(history_retention_days=90, max_history_size=100)
    )
    router.set_users(
        [
            UserProfile(user_id="alice", display_name="Alice"),
            UserProfile(user_id="bob", display_name="Bob"),
        ]
    )
    measurement = _measurement("duplicate-id", 75.0, 0)
    router.record_measurement_for_user("alice", measurement)

    with pytest.raises(DuplicateMeasurementError):
        router.record_measurement_for_user(
            "bob",
            WeightMeasurement(
                measurement_id="duplicate-id",
                weight_kg=88.0,
                timestamp=datetime.now(tz=timezone.utc),
                source_id="sensor.scale",
            ),
        )
