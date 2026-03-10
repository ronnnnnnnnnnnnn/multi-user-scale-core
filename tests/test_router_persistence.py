from __future__ import annotations

from datetime import datetime, timezone

import pytest

from multi_user_scale_core import (
    DuplicateMeasurementError,
    RouterConfig,
    UserProfile,
    WeightMeasurement,
    WeightRouter,
)


def _now(seconds: int) -> datetime:
    return datetime(2026, 2, 19, 12, 0, seconds, tzinfo=timezone.utc)


def _build_router() -> WeightRouter:
    router = WeightRouter(
        config=RouterConfig(history_retention_days=30, max_history_size=10)
    )
    router.set_users(
        [
            UserProfile(user_id="alice", display_name="Alice"),
            UserProfile(user_id="bob", display_name="Bob"),
        ]
    )
    router.record_measurement_for_user(
        "alice",
        WeightMeasurement(weight_kg=75.0, timestamp=_now(10), source_id="scale"),
    )
    router.record_measurement_for_user(
        "bob",
        WeightMeasurement(weight_kg=68.0, timestamp=_now(20), source_id="scale"),
    )
    return router


# ---------------------------------------------------------------------------
# Round-trip fidelity
# ---------------------------------------------------------------------------


def test_to_dict_round_trip_preserves_state() -> None:
    router = _build_router()
    restored = WeightRouter.from_dict(router.to_dict())

    assert restored.config == router.config
    assert restored.users == router.users
    assert len(restored.get_user_history("alice")) == 1
    assert restored.get_user_history("alice")[0].weight_kg == 75.0
    assert len(restored.get_user_history("bob")) == 1
    assert restored.get_user_history("bob")[0].weight_kg == 68.0


def test_to_dict_contains_now_metadata() -> None:
    fixed = datetime(2026, 2, 19, 12, 0, 0, tzinfo=timezone.utc)
    router = WeightRouter(now_provider=lambda: fixed)
    router.set_users([])
    payload = router.to_dict()
    assert payload["now"] == fixed.isoformat()


# ---------------------------------------------------------------------------
# now_provider passthrough
# ---------------------------------------------------------------------------


def test_from_dict_now_provider_is_passed_through() -> None:
    fixed = datetime(2026, 3, 1, tzinfo=timezone.utc)
    router = _build_router()
    restored = WeightRouter.from_dict(router.to_dict(), now_provider=lambda: fixed)
    assert restored._now() == fixed


# ---------------------------------------------------------------------------
# Measurement-ID index is restored
# ---------------------------------------------------------------------------


def test_from_dict_preserves_measurement_id_index() -> None:
    router = _build_router()
    alice_id = router.get_user_history("alice")[0].measurement_id

    restored = WeightRouter.from_dict(router.to_dict())

    with pytest.raises(DuplicateMeasurementError):
        restored.record_measurement_for_user(
            "alice",
            WeightMeasurement(
                measurement_id=alice_id,
                weight_kg=75.5,
                timestamp=_now(30),
                source_id="scale",
            ),
        )


# ---------------------------------------------------------------------------
# from_dict validation
# ---------------------------------------------------------------------------


def test_from_dict_rejects_non_dict_payload() -> None:
    with pytest.raises(TypeError):
        WeightRouter.from_dict([])


def test_from_dict_rejects_non_dict_config() -> None:
    with pytest.raises(TypeError):
        WeightRouter.from_dict({"config": "bad"})


def test_from_dict_rejects_non_list_users() -> None:
    with pytest.raises(TypeError):
        WeightRouter.from_dict({"config": {}, "users": "bad"})


def test_from_dict_rejects_non_dict_history() -> None:
    with pytest.raises(TypeError):
        WeightRouter.from_dict({"config": {}, "history": []})


def test_from_dict_rejects_duplicate_measurement_ids_in_history() -> None:
    m_dict = WeightMeasurement(
        measurement_id="dup", weight_kg=75.0, timestamp=_now(10), source_id="scale"
    ).to_dict()
    payload = {
        "config": {},
        "users": [{"user_id": "alice", "display_name": "Alice"}],
        "history": {"alice": [m_dict, m_dict]},
    }
    with pytest.raises(ValueError, match="Duplicate"):
        WeightRouter.from_dict(payload)


def test_from_dict_rejects_unknown_user_in_history() -> None:
    m_dict = WeightMeasurement(
        weight_kg=75.0, timestamp=_now(10), source_id="scale"
    ).to_dict()
    payload = {
        "config": {},
        "users": [{"user_id": "alice", "display_name": "Alice"}],
        "history": {"bob": [m_dict]},  # bob not in users
    }
    with pytest.raises(ValueError, match="not configured"):
        WeightRouter.from_dict(payload)


def test_from_dict_ignores_unknown_config_keys() -> None:
    payload = {
        "config": {
            "history_retention_days": 60,
            "unknown_future_field": "ignored",
        },
        "users": [],
    }
    router = WeightRouter.from_dict(payload)
    assert router.config.history_retention_days == 60
