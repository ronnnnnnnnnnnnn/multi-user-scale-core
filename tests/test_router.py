from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from multi_user_scale_core import (
    DuplicateMeasurementError,
    MeasurementNotFoundError,
    RouterConfig,
    UserNotFoundError,
    UserProfile,
    WeightMeasurement,
    WeightRouter,
)
from multi_user_scale_core.errors import MeasurementValidationError

_FIXED = datetime(2026, 2, 1, 12, 0, 0, tzinfo=timezone.utc)


def _m(
    measurement_id: str,
    weight_kg: float,
    days_ago: float,
    source_id: str = "sensor.scale",
) -> WeightMeasurement:
    return WeightMeasurement(
        measurement_id=measurement_id,
        weight_kg=weight_kg,
        timestamp=_FIXED - timedelta(days=days_ago),
        source_id=source_id,
    )


def _router(*user_ids: str) -> WeightRouter:
    router = WeightRouter(now_provider=lambda: _FIXED)
    router.set_users(
        [UserProfile(user_id=uid, display_name=uid.title()) for uid in user_ids]
    )
    return router


# ---------------------------------------------------------------------------
# evaluate_measurement
# ---------------------------------------------------------------------------


def test_evaluate_no_users_returns_empty() -> None:
    router = WeightRouter()
    candidates = router.evaluate_measurement(
        _m("incoming", 75.0, 0)
    )
    assert candidates == []


def test_evaluate_all_no_history_returns_no_history_candidates() -> None:
    router = _router("alice", "bob")
    candidates = router.evaluate_measurement(_m("incoming", 75.0, 0))
    assert len(candidates) == 2
    assert all(c.reference_weight_kg is None for c in candidates)
    assert all(c.tolerance_kg is None for c in candidates)


def test_evaluate_returns_match_then_no_history_candidates() -> None:
    router = _router("alice", "bob", "charlie")
    for i, w in enumerate([75.0, 75.2, 74.9, 75.1, 75.0]):
        router.record_measurement_for_user("alice", _m(f"a{i}", w, 5 - i))
    for i, w in enumerate([90.0, 89.8, 90.1, 89.9, 90.2]):
        router.record_measurement_for_user("bob", _m(f"b{i}", w, 5 - i))

    candidates = router.evaluate_measurement(_m("incoming", 75.1, 0))

    assert [c.user_id for c in candidates] == ["alice", "charlie"]
    assert candidates[0].reference_weight_kg is not None
    assert candidates[0].tolerance_kg is not None
    assert candidates[1].reference_weight_kg is None
    assert candidates[1].tolerance_kg is None


def test_evaluate_closest_match_is_first() -> None:
    router = _router("alice", "bob")
    for i, w in enumerate([75.0, 75.2, 74.8, 75.1, 75.0]):
        router.record_measurement_for_user("alice", _m(f"a{i}", w, 5 - i))
    for i, w in enumerate([76.0, 76.1, 75.9, 76.0, 76.2]):
        router.record_measurement_for_user("bob", _m(f"b{i}", w, 5 - i))

    # 75.3 is closer to alice's reference (~75) than bob's (~76)
    candidates = router.evaluate_measurement(_m("incoming", 75.3, 0))

    assert len(candidates) == 2
    assert candidates[0].user_id == "alice"
    assert candidates[1].user_id == "bob"


def test_evaluate_prunes_inferior_matches() -> None:
    router = _router("alice", "bob")
    # Alice has 99.0 kg, Bob has 92.0 kg
    for i, w in enumerate([99.0, 99.2, 98.8, 99.1, 99.0]):
        router.record_measurement_for_user("alice", _m(f"a{i}", w, 5 - i))
    for i, w in enumerate([92.0, 92.1, 91.9, 92.0, 92.2]):
        router.record_measurement_for_user("bob", _m(f"b{i}", w, 5 - i))

    # To trigger the bug, Bob needs to not have weighed in recently,
    # so his tolerance expands to > 5.5 kg.
    # We recorded Bob's measurements 1-5 days ago. 
    # Wait, 5 days ago is not enough to expand the tolerance to 5.5 kg.
    # Let's just simulate the distance: 
    # Alex distance: 1.0 kg (from 99.0 to 98.0)
    # Bob distance: 6.0 kg (from 92.0 to 98.0)
    # If Bob's tolerance somehow allowed 6.0 kg, Bob would be included.
    # We don't even need to trigger the expanded tolerance if we just test
    # the pruning logic against a case where two candidates are returned by distance.
    # Oh wait, if the tolerance doesn't allow it, Bob won't even make it to the candidate list.
    # Let's just manually set Bob's measurements to 30 days ago to expand tolerance
    router = _router("alice", "bob")
    for i, w in enumerate([99.0, 99.2, 98.8, 99.1, 99.0]):
        router.record_measurement_for_user("alice", _m(f"a{i}", w, 5 - i))
    for i, w in enumerate([92.0, 92.1, 91.9, 92.2]):
        router.record_measurement_for_user("bob", _m(f"b{i}", w, 60 - i))

    # Bob's distance is |98.0 - 92.0| = 6.0 kg.
    # Base tolerance for 92kg is ~3.68kg.
    # Recency multiplier for 25 days is 1.0 + (0.15 * 5) = 1.75.
    # Tolerance = 3.68 * 1.75 = 6.44 kg.
    # So 6.0 kg is within Bob's tolerance! Bob WOULD be included without pruning.
    
    # Alice's distance is |98.0 - 99.0| = 1.0 kg.
    # Alice's tolerance is ~3.96kg.
    
    # Best distance is 1.0. Margin is 3.0 (default prune_margin_kg). Prune threshold is 4.0.
    # Bob's distance is 6.0 > 4.0, so Bob should be pruned.
    
    candidates = router.evaluate_measurement(_m("incoming", 98.0, 0))

    assert len(candidates) == 1
    assert candidates[0].user_id == "alice"

    # Now verify that setting enable_pruning=False returns both candidates
    router.set_config(RouterConfig(enable_pruning=False))
    candidates_no_pruning = router.evaluate_measurement(_m("incoming", 98.0, 0))
    assert len(candidates_no_pruning) == 2
    assert candidates_no_pruning[0].user_id == "alice"
    assert candidates_no_pruning[1].user_id == "bob"


def test_evaluate_out_of_tolerance_not_returned() -> None:
    router = _router("alice")
    for i, w in enumerate([75.0, 75.2, 74.9, 75.1, 75.0]):
        router.record_measurement_for_user("alice", _m(f"a{i}", w, 5 - i))

    # 95 kg is far outside alice's tolerance
    candidates = router.evaluate_measurement(_m("incoming", 95.0, 0))

    assert candidates == []


def test_evaluate_rejects_nan_weight() -> None:
    router = _router("alice")
    with pytest.raises(MeasurementValidationError):
        router.evaluate_measurement(_m("bad", float("nan"), 0))


def test_evaluate_rejects_inf_weight() -> None:
    router = _router("alice")
    with pytest.raises(MeasurementValidationError):
        router.evaluate_measurement(_m("bad", float("inf"), 0))


def test_evaluate_rejects_non_numeric_weight() -> None:
    m = WeightMeasurement(
        measurement_id="bad",
        weight_kg="seventy",  # type: ignore[arg-type]
        timestamp=_FIXED,
        source_id="test",
    )
    router = _router("alice")
    with pytest.raises(MeasurementValidationError):
        router.evaluate_measurement(m)


# ---------------------------------------------------------------------------
# record_measurement_for_user
# ---------------------------------------------------------------------------


def test_record_unknown_user_raises() -> None:
    router = _router("alice")
    with pytest.raises(UserNotFoundError):
        router.record_measurement_for_user("unknown", _m("m1", 75.0, 0))


def test_record_duplicate_id_rejected_globally() -> None:
    router = _router("alice", "bob")
    router.record_measurement_for_user("alice", _m("dup", 75.0, 1))
    with pytest.raises(DuplicateMeasurementError):
        router.record_measurement_for_user("bob", _m("dup", 88.0, 0))


# ---------------------------------------------------------------------------
# remove_measurement
# ---------------------------------------------------------------------------


def test_remove_latest_fallback() -> None:
    router = _router("alice")
    router.record_measurement_for_user("alice", _m("m1", 75.0, 2))
    router.record_measurement_for_user("alice", _m("m2", 75.5, 1))

    removed = router.remove_measurement("alice")
    assert removed.measurement_id == "m2"
    assert [m.measurement_id for m in router.get_user_history("alice")] == ["m1"]


def test_remove_by_id() -> None:
    router = _router("alice")
    router.record_measurement_for_user("alice", _m("m1", 75.0, 2))
    router.record_measurement_for_user("alice", _m("m2", 75.5, 1))

    removed = router.remove_measurement("alice", "m1")
    assert removed.measurement_id == "m1"
    assert [m.measurement_id for m in router.get_user_history("alice")] == ["m2"]


def test_remove_unknown_user_raises() -> None:
    router = _router("alice")
    with pytest.raises(UserNotFoundError):
        router.remove_measurement("unknown")


def test_remove_empty_history_raises() -> None:
    router = _router("alice")
    with pytest.raises(MeasurementNotFoundError):
        router.remove_measurement("alice")


def test_remove_unknown_id_raises() -> None:
    router = _router("alice")
    router.record_measurement_for_user("alice", _m("m1", 75.0, 1))
    with pytest.raises(MeasurementNotFoundError):
        router.remove_measurement("alice", "does-not-exist")


def test_remove_releases_measurement_id() -> None:
    router = _router("alice")
    m = _m("reusable", 75.0, 0)
    router.record_measurement_for_user("alice", m)
    router.remove_measurement("alice", "reusable")
    # ID should be released — can be recorded again without DuplicateMeasurementError
    router.record_measurement_for_user("alice", m)
    assert len(router.get_user_history("alice")) == 1


# ---------------------------------------------------------------------------
# reassign_measurement
# ---------------------------------------------------------------------------


def test_reassign_latest_fallback() -> None:
    router = _router("alice", "bob")
    router.record_measurement_for_user("alice", _m("m1", 75.0, 2))
    router.record_measurement_for_user("alice", _m("m2", 75.5, 1))

    reassigned = router.reassign_measurement("alice", "bob")
    assert reassigned.measurement_id == "m2"
    assert [m.measurement_id for m in router.get_user_history("alice")] == ["m1"]
    assert [m.measurement_id for m in router.get_user_history("bob")] == ["m2"]


def test_reassign_by_id() -> None:
    router = _router("alice", "bob")
    router.record_measurement_for_user("alice", _m("m1", 75.0, 2))
    router.record_measurement_for_user("alice", _m("m2", 75.5, 1))

    reassigned = router.reassign_measurement("alice", "bob", "m1")
    assert reassigned.measurement_id == "m1"
    assert [m.measurement_id for m in router.get_user_history("alice")] == ["m2"]
    assert [m.measurement_id for m in router.get_user_history("bob")] == ["m1"]


def test_reassign_unknown_source_raises() -> None:
    router = _router("alice", "bob")
    with pytest.raises(UserNotFoundError):
        router.reassign_measurement("unknown", "bob")


def test_reassign_unknown_target_raises() -> None:
    router = _router("alice", "bob")
    router.record_measurement_for_user("alice", _m("m1", 75.0, 1))
    with pytest.raises(UserNotFoundError):
        router.reassign_measurement("alice", "unknown")


# ---------------------------------------------------------------------------
# get_user_history / get_user_last_measurement
# ---------------------------------------------------------------------------


def test_get_user_history_unknown_raises() -> None:
    router = WeightRouter()
    with pytest.raises(UserNotFoundError):
        router.get_user_history("unknown")


def test_get_user_last_measurement_empty_returns_none() -> None:
    router = _router("alice")
    assert router.get_user_last_measurement("alice") is None


def test_get_user_last_measurement_returns_most_recent() -> None:
    router = _router("alice")
    router.record_measurement_for_user("alice", _m("m1", 75.0, 2))
    router.record_measurement_for_user("alice", _m("m2", 75.5, 1))

    last = router.get_user_last_measurement("alice")
    assert last is not None
    assert last.measurement_id == "m2"


def test_get_user_last_measurement_unknown_raises() -> None:
    router = WeightRouter()
    with pytest.raises(UserNotFoundError):
        router.get_user_last_measurement("unknown")


# ---------------------------------------------------------------------------
# set_users — history management
# ---------------------------------------------------------------------------


def test_set_users_drops_history_for_removed_user() -> None:
    router = _router("alice", "bob")
    router.record_measurement_for_user("alice", _m("alice-m1", 75.0, 1))

    router.set_users([UserProfile(user_id="bob", display_name="Bob")])

    with pytest.raises(UserNotFoundError):
        router.get_user_history("alice")


def test_set_users_releases_measurement_ids_for_removed_user() -> None:
    router = _router("alice", "bob")
    m = _m("shared-id", 75.0, 1)
    router.record_measurement_for_user("alice", m)

    # Remove alice; her measurement ID should be released
    router.set_users([UserProfile(user_id="bob", display_name="Bob")])
    # Re-add alice
    router.set_users(
        [
            UserProfile(user_id="alice", display_name="Alice"),
            UserProfile(user_id="bob", display_name="Bob"),
        ]
    )
    # "shared-id" should no longer be tracked → can be recorded without error
    router.record_measurement_for_user("alice", m)
    assert len(router.get_user_history("alice")) == 1


# ---------------------------------------------------------------------------
# set_config — pruning
# ---------------------------------------------------------------------------


def test_set_config_prunes_measurements_outside_new_retention() -> None:
    router = _router("alice")
    router.record_measurement_for_user("alice", _m("old", 75.0, 40))
    router.record_measurement_for_user("alice", _m("recent", 75.0, 5))

    assert len(router.get_user_history("alice")) == 2

    # Shorten retention to 30 days — "old" (40 d) should be pruned
    router.set_config(RouterConfig(history_retention_days=30))

    history = router.get_user_history("alice")
    assert len(history) == 1
    assert history[0].measurement_id == "recent"


# ---------------------------------------------------------------------------
# History retention and max size
# ---------------------------------------------------------------------------


def test_history_retention_prunes_on_record() -> None:
    router = WeightRouter(
        config=RouterConfig(history_retention_days=30),
        now_provider=lambda: _FIXED,
    )
    router.set_users([UserProfile(user_id="alice", display_name="Alice")])
    router.record_measurement_for_user("alice", _m("older", 75.0, 50))
    router.record_measurement_for_user("alice", _m("old", 75.0, 40))
    router.record_measurement_for_user("alice", _m("recent", 75.5, 1))

    history = router.get_user_history("alice")
    assert len(history) == 1
    assert history[0].measurement_id == "recent"


def test_history_retention_retains_last_measurement() -> None:
    router = WeightRouter(
        config=RouterConfig(history_retention_days=30),
        now_provider=lambda: _FIXED,
    )
    router.set_users([UserProfile(user_id="alice", display_name="Alice")])
    router.record_measurement_for_user("alice", _m("very_old", 75.0, 60))
    router.record_measurement_for_user("alice", _m("old", 75.5, 40))

    # Trigger a pruning run using the current time
    router.evaluate_measurement(_m("incoming", 75.0, 0))

    # Even though both are > 30 days old relative to the incoming measurement (now),
    # the most recent one ("old") should be retained.
    history = router.get_user_history("alice")
    assert len(history) == 1
    assert history[0].measurement_id == "old"


def test_max_history_size_evicts_oldest() -> None:
    router = WeightRouter(
        config=RouterConfig(max_history_size=3),
        now_provider=lambda: _FIXED,
    )
    router.set_users([UserProfile(user_id="alice", display_name="Alice")])

    for i in range(4):
        router.record_measurement_for_user(
            "alice", _m(f"m{i}", 75.0, 4 - i)
        )

    history = router.get_user_history("alice")
    assert len(history) == 3
    assert [m.measurement_id for m in history] == ["m1", "m2", "m3"]
