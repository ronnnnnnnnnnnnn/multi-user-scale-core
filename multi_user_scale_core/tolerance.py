"""Tolerance calculations for weight matching."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from math import sqrt
from statistics import pstdev
from typing import Iterable

from .models import WeightMeasurement


DEFAULT_TOLERANCE_PERCENTAGE = 0.04
MIN_TOLERANCE_KG = 1.5
MAX_TOLERANCE_KG = 5.0

MIN_MEASUREMENTS_FOR_ADAPTIVE = 5
REFERENCE_WINDOW_DAYS = 7
VARIANCE_WINDOW_DAYS = 30
TOLERANCE_MULTIPLIER = 2.5
RECENCY_SCALING_RATE = 0.15
RECENCY_SCALING_MAX = 2.5
MAX_MEASUREMENTS_PER_DAY_FOR_TOLERANCE = 2


def _days_between(first: datetime, second: datetime) -> float:
    delta = abs(second - first)
    return max(delta.total_seconds() / 86400, 0.0)


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _filtered_measurements(
    measurements: Iterable[WeightMeasurement],
    reference_time: datetime,
    window_days: float,
) -> list[WeightMeasurement]:
    cutoff = reference_time - timedelta(days=window_days)
    return [
        measurement for measurement in measurements if measurement.timestamp >= cutoff
    ]


def _limit_measurements_per_day(
    measurements: list[WeightMeasurement],
    max_per_day: int = MAX_MEASUREMENTS_PER_DAY_FOR_TOLERANCE,
) -> list[WeightMeasurement]:
    if len(measurements) <= max_per_day:
        return measurements

    by_day: dict[date, list[WeightMeasurement]] = defaultdict(list)
    for measurement in measurements:
        by_day[measurement.timestamp.date()].append(measurement)

    limited: list[WeightMeasurement] = []
    for daily_measurements in by_day.values():
        if len(daily_measurements) <= max_per_day:
            limited.extend(daily_measurements)
            continue

        daily_min = min(daily_measurements, key=lambda sample: sample.weight_kg)
        daily_max = max(daily_measurements, key=lambda sample: sample.weight_kg)
        limited.append(daily_min)
        if daily_max is not daily_min:
            limited.append(daily_max)

    return sorted(limited, key=lambda sample: sample.timestamp)


def calculate_reference_weight(
    measurements: Iterable[WeightMeasurement],
    reference_time: datetime,
    window_days: int = REFERENCE_WINDOW_DAYS,
    half_life_days: float = 3.5,
) -> float | None:
    """Calculate exponentially weighted reference weight for a window."""

    all_measurements = list(measurements)
    if not all_measurements:
        return None

    samples = _filtered_measurements(all_measurements, reference_time, window_days)
    if not samples:
        # Fallback to the most recent measurement when the window is empty.
        latest = max(all_measurements, key=lambda sample: sample.timestamp)
        return latest.weight_kg

    samples = _limit_measurements_per_day(samples)
    if not samples:
        latest = max(all_measurements, key=lambda sample: sample.timestamp)
        return latest.weight_kg

    weighted_total = 0.0
    weighted_divisor = 0.0

    for measurement in samples:
        age_days = _days_between(measurement.timestamp, reference_time)
        decay = pow(0.5, age_days / half_life_days) if half_life_days > 0 else 1.0
        weighted_total += decay * measurement.weight_kg
        weighted_divisor += decay

    if weighted_divisor <= 0:
        return None

    return weighted_total / weighted_divisor


def calculate_base_tolerance(
    reference_weight: float,
    tolerance_percentage: float = DEFAULT_TOLERANCE_PERCENTAGE,
) -> float:
    if reference_weight <= 0:
        return MIN_TOLERANCE_KG
    base = abs(reference_weight * tolerance_percentage)
    return _clamp(base, MIN_TOLERANCE_KG, MAX_TOLERANCE_KG)


def calculate_variance_tolerance(
    measurements: Iterable[WeightMeasurement],
    reference_weight: float,
    base_tolerance: float,
    reference_time: datetime,
    variance_window_days: int = VARIANCE_WINDOW_DAYS,
    min_measurements_for_adaptive: int = MIN_MEASUREMENTS_FOR_ADAPTIVE,
) -> float:
    samples = _filtered_measurements(measurements, reference_time, variance_window_days)
    samples = _limit_measurements_per_day(samples)
    if len(samples) < min_measurements_for_adaptive:
        return base_tolerance

    values = [sample.weight_kg for sample in samples]
    if len(values) < 2:
        return base_tolerance

    std_dev = pstdev(values)
    adaptive = std_dev * TOLERANCE_MULTIPLIER
    lower = base_tolerance * 0.5
    upper = base_tolerance * 1.5
    return _clamp(adaptive, lower, upper)


def calculate_final_tolerance(
    measurements: Iterable[WeightMeasurement],
    reference_weight: float,
    reference_time: datetime,
    *,
    tolerance_percentage: float = DEFAULT_TOLERANCE_PERCENTAGE,
    min_tolerance_kg: float = MIN_TOLERANCE_KG,
    min_measurements_for_adaptive: int = MIN_MEASUREMENTS_FOR_ADAPTIVE,
    variance_window_days: int = VARIANCE_WINDOW_DAYS,
) -> float:
    measurement_list = list(measurements)

    base = calculate_base_tolerance(
        reference_weight,
        tolerance_percentage=tolerance_percentage,
    )
    adaptive = calculate_variance_tolerance(
        measurements=measurement_list,
        reference_weight=reference_weight,
        base_tolerance=base,
        reference_time=reference_time,
        variance_window_days=variance_window_days,
        min_measurements_for_adaptive=min_measurements_for_adaptive,
    )

    if not measurement_list:
        latest = reference_time
    else:
        latest_measurement = max(measurement_list, key=lambda sample: sample.timestamp)
        latest = latest_measurement.timestamp

    days_since_last = _days_between(latest, reference_time)
    recency_multiplier = 1.0 + (RECENCY_SCALING_RATE * sqrt(days_since_last))
    recency_multiplier = min(recency_multiplier, RECENCY_SCALING_MAX)
    final = adaptive * recency_multiplier

    # Only enforce a minimum tolerance floor; do not cap the upper bound.
    return max(min_tolerance_kg, final)
