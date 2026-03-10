from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from multi_user_scale_core.models import WeightMeasurement
from multi_user_scale_core.tolerance import (
    DEFAULT_TOLERANCE_PERCENTAGE,
    MAX_TOLERANCE_KG,
    MIN_TOLERANCE_KG,
    calculate_base_tolerance,
    calculate_final_tolerance,
    calculate_reference_weight,
)

_BASE = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


def _m(weight_kg: float, days_ago: float = 0.0) -> WeightMeasurement:
    return WeightMeasurement(
        weight_kg=weight_kg,
        timestamp=_BASE - timedelta(days=days_ago),
        source_id="test",
    )


# ---------------------------------------------------------------------------
# calculate_reference_weight
# ---------------------------------------------------------------------------


class TestCalculateReferenceWeight:
    def test_empty_measurements_returns_none(self) -> None:
        assert calculate_reference_weight([], _BASE) is None

    def test_single_measurement_within_window(self) -> None:
        result = calculate_reference_weight([_m(75.0, 1)], _BASE)
        assert result == pytest.approx(75.0)

    def test_all_outside_window_falls_back_to_latest(self) -> None:
        # Both outside 7-day window; fallback is the one 10 days ago (more recent)
        result = calculate_reference_weight(
            [_m(75.0, 10), _m(72.0, 20)], _BASE, window_days=7
        )
        assert result == pytest.approx(75.0)

    def test_recent_measurement_weighted_more(self) -> None:
        # Measurement today: decay = 1.0
        # Measurement 3.5 days ago: decay = 0.5 (at default half_life_days=3.5)
        # Expected = (1.0*80 + 0.5*60) / (1.0 + 0.5) = 110/1.5
        result = calculate_reference_weight(
            [_m(80.0, 0.0), _m(60.0, 3.5)], _BASE, half_life_days=3.5
        )
        assert result == pytest.approx(110.0 / 1.5, rel=1e-6)

    def test_zero_half_life_weights_all_measurements_equally(self) -> None:
        # half_life_days=0 → decay=1 for all; simple mean
        result = calculate_reference_weight(
            [_m(70.0, 1), _m(80.0, 2)], _BASE, half_life_days=0
        )
        assert result == pytest.approx(75.0)

    def test_accepts_iterator(self) -> None:
        def _gen():
            yield _m(75.0, 1)
            yield _m(75.0, 2)

        result = calculate_reference_weight(_gen(), _BASE)
        assert result == pytest.approx(75.0, rel=0.01)


# ---------------------------------------------------------------------------
# calculate_base_tolerance
# ---------------------------------------------------------------------------


class TestCalculateBaseTolerance:
    def test_zero_weight_returns_min(self) -> None:
        assert calculate_base_tolerance(0.0) == MIN_TOLERANCE_KG

    def test_negative_weight_returns_min(self) -> None:
        assert calculate_base_tolerance(-10.0) == MIN_TOLERANCE_KG

    def test_small_weight_clamps_to_min(self) -> None:
        # 10 kg * 4% = 0.4 kg < MIN_TOLERANCE_KG
        assert calculate_base_tolerance(10.0, DEFAULT_TOLERANCE_PERCENTAGE) == MIN_TOLERANCE_KG

    def test_large_weight_clamps_to_max(self) -> None:
        # 200 kg * 4% = 8.0 kg > MAX_TOLERANCE_KG
        assert calculate_base_tolerance(200.0, DEFAULT_TOLERANCE_PERCENTAGE) == MAX_TOLERANCE_KG

    def test_normal_weight_within_range(self) -> None:
        # 75 kg * 4% = 3.0 kg, within [MIN=1.5, MAX=5.0]
        assert calculate_base_tolerance(75.0, DEFAULT_TOLERANCE_PERCENTAGE) == pytest.approx(3.0)

    def test_custom_tolerance_percentage(self) -> None:
        # 75 kg * 2% = 1.5 kg → exactly at MIN
        assert calculate_base_tolerance(75.0, 0.02) == MIN_TOLERANCE_KG


# ---------------------------------------------------------------------------
# calculate_final_tolerance
# ---------------------------------------------------------------------------


class TestCalculateFinalTolerance:
    def test_insufficient_history_uses_base_tolerance(self) -> None:
        # 4 measurements < min_measurements_for_adaptive (5) → falls back to base
        samples = [_m(75.0, i) for i in range(4)]
        base = calculate_base_tolerance(75.0)
        result = calculate_final_tolerance(
            samples,
            reference_weight=75.0,
            reference_time=_BASE,
            min_measurements_for_adaptive=5,
        )
        # With very recent measurements, recency_multiplier ≈ 1.0
        assert result == pytest.approx(base, rel=0.05)

    def test_stale_history_increases_tolerance(self) -> None:
        # Last measurement 25 days ago
        # recency_multiplier = 1 + 0.15 * sqrt(25) = 1.75
        samples = [_m(75.0, 25)]
        base = calculate_base_tolerance(75.0)
        result = calculate_final_tolerance(
            samples,
            reference_weight=75.0,
            reference_time=_BASE,
        )
        assert result > base

    def test_min_tolerance_floor_applied(self) -> None:
        # Reference weight 5 kg: base clamped to module MIN (1.5); custom min=2.0 floors result
        samples = [_m(5.0, 0)]
        result = calculate_final_tolerance(
            samples,
            reference_weight=5.0,
            reference_time=_BASE,
            min_tolerance_kg=2.0,
        )
        assert result >= 2.0

    def test_accepts_iterator_without_double_consuming(self) -> None:
        # Generator must not be consumed more than once (validates the list() fix)
        def _gen():
            yield _m(75.0, 1)
            yield _m(75.2, 2)
            yield _m(74.9, 3)

        result = calculate_final_tolerance(
            _gen(),
            reference_weight=75.0,
            reference_time=_BASE,
        )
        assert result > 0

    def test_result_always_at_least_min_tolerance_kg(self) -> None:
        # Verify floor holds even with very consistent recent history
        samples = [_m(75.0 + 0.01 * i, i * 0.1) for i in range(10)]
        result = calculate_final_tolerance(
            samples,
            reference_weight=75.0,
            reference_time=_BASE,
            min_tolerance_kg=MIN_TOLERANCE_KG,
        )
        assert result >= MIN_TOLERANCE_KG
