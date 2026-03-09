from __future__ import annotations

from datetime import datetime, timezone

import pytest

from multi_user_scale_core import (
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
    users = [
        UserProfile(user_id="alice", display_name="Alice"),
        UserProfile(user_id="bob", display_name="Bob"),
    ]
    router.set_users(users)

    router.record_measurement_for_user(
        "alice",
        WeightMeasurement(
            weight_kg=75.0,
            timestamp=_now(10),
            source_id="scale",
        ),
    )
    router.record_measurement_for_user(
        "bob",
        WeightMeasurement(
            weight_kg=68.0,
            timestamp=_now(20),
            source_id="scale",
        ),
    )

    return router


def test_router_to_dict_round_trip_preserves_state() -> None:
    router = _build_router()
    payload = router.to_dict()

    restored = WeightRouter.from_dict(payload)

    assert restored.config == router.config
    assert restored.users == router.users
    assert len(restored.get_user_history("alice")) == 1
    assert restored.get_user_history("alice")[0].weight_kg == 75.0
    assert len(restored.get_user_history("bob")) == 1
    assert restored.get_user_history("bob")[0].weight_kg == 68.0


def test_router_restore_rejects_invalid_payload() -> None:
    with pytest.raises((TypeError, ValueError)):
        WeightRouter.from_dict([])

    bad_config_payload = {
        "config": "bad",
    }
    with pytest.raises((TypeError, ValueError)):
        WeightRouter.from_dict(bad_config_payload)

    bad_users_payload = {"config": {}, "users": "bad"}
    with pytest.raises((TypeError, ValueError)):
        WeightRouter.from_dict(bad_users_payload)

    bad_history_type = {"config": {}, "history": []}
    with pytest.raises((TypeError, ValueError)):
        WeightRouter.from_dict(bad_history_type)
