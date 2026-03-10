from __future__ import annotations

from datetime import datetime, timezone

import pytest

from multi_user_scale_core import RouterConfig, UserProfile, WeightMeasurement


# ---------------------------------------------------------------------------
# RouterConfig validation
# ---------------------------------------------------------------------------


class TestRouterConfigDefaults:
    def test_defaults_are_valid(self) -> None:
        c = RouterConfig()
        assert c.history_retention_days == 90
        assert c.max_history_size == 100
        assert c.tolerance_percentage == 0.04
        assert c.min_tolerance_kg == 1.5
        assert c.variance_window_days == 30
        assert c.reference_window_days == 7
        assert c.min_measurements_for_adaptive == 5


class TestRouterConfigIntFields:
    INT_FIELDS = [
        "history_retention_days",
        "max_history_size",
        "variance_window_days",
        "reference_window_days",
        "min_measurements_for_adaptive",
    ]

    @pytest.mark.parametrize("field", INT_FIELDS)
    def test_float_rejected(self, field: str) -> None:
        with pytest.raises(TypeError):
            RouterConfig(**{field: 1.5})

    @pytest.mark.parametrize("field", INT_FIELDS)
    def test_string_rejected(self, field: str) -> None:
        with pytest.raises(TypeError):
            RouterConfig(**{field: "10"})

    @pytest.mark.parametrize("field", INT_FIELDS)
    def test_bool_rejected(self, field: str) -> None:
        with pytest.raises(TypeError):
            RouterConfig(**{field: True})

    @pytest.mark.parametrize("field", INT_FIELDS)
    def test_zero_raises_value_error(self, field: str) -> None:
        with pytest.raises(ValueError):
            RouterConfig(**{field: 0})

    @pytest.mark.parametrize("field", INT_FIELDS)
    def test_negative_raises_value_error(self, field: str) -> None:
        with pytest.raises(ValueError):
            RouterConfig(**{field: -1})


class TestRouterConfigFloatFields:
    FLOAT_FIELDS = ["tolerance_percentage", "min_tolerance_kg"]

    @pytest.mark.parametrize("field", FLOAT_FIELDS)
    def test_string_rejected(self, field: str) -> None:
        with pytest.raises(TypeError):
            RouterConfig(**{field: "0.04"})

    @pytest.mark.parametrize("field", FLOAT_FIELDS)
    def test_none_rejected(self, field: str) -> None:
        with pytest.raises(TypeError):
            RouterConfig(**{field: None})

    @pytest.mark.parametrize("field", FLOAT_FIELDS)
    def test_bool_rejected(self, field: str) -> None:
        with pytest.raises(TypeError):
            RouterConfig(**{field: True})

    @pytest.mark.parametrize("field", FLOAT_FIELDS)
    def test_zero_raises_value_error(self, field: str) -> None:
        with pytest.raises(ValueError):
            RouterConfig(**{field: 0.0})

    @pytest.mark.parametrize("field", FLOAT_FIELDS)
    def test_negative_raises_value_error(self, field: str) -> None:
        with pytest.raises(ValueError):
            RouterConfig(**{field: -0.01})


# ---------------------------------------------------------------------------
# WeightMeasurement round-trip
# ---------------------------------------------------------------------------


class TestWeightMeasurementRoundTrip:
    def test_to_dict_from_dict_preserves_all_fields(self) -> None:
        ts = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        original = WeightMeasurement(
            weight_kg=75.3,
            timestamp=ts,
            source_id="sensor.scale",
            measurement_id="abc123",
            source_unit="lb",
            raw={"raw_lb": 166.0},
        )
        restored = WeightMeasurement.from_dict(original.to_dict())

        assert restored.weight_kg == original.weight_kg
        assert restored.timestamp == original.timestamp
        assert restored.source_id == original.source_id
        assert restored.measurement_id == original.measurement_id
        assert restored.source_unit == original.source_unit
        assert restored.raw == original.raw

    def test_from_dict_missing_required_key_raises(self) -> None:
        with pytest.raises(KeyError):
            # timestamp is missing
            WeightMeasurement.from_dict({"weight_kg": 75.0, "source_id": "s"})

    def test_from_dict_non_dict_raises(self) -> None:
        with pytest.raises(TypeError):
            WeightMeasurement.from_dict([])  # type: ignore[arg-type]

    def test_from_dict_generates_id_when_absent(self) -> None:
        ts = datetime(2026, 1, 15, tzinfo=timezone.utc)
        m = WeightMeasurement.from_dict(
            {"weight_kg": 75.0, "timestamp": ts.isoformat(), "source_id": "sensor"}
        )
        assert m.measurement_id  # auto-generated, non-empty

    def test_from_dict_defaults_source_unit_to_kg(self) -> None:
        ts = datetime(2026, 1, 15, tzinfo=timezone.utc)
        m = WeightMeasurement.from_dict(
            {"weight_kg": 75.0, "timestamp": ts.isoformat(), "source_id": "sensor"}
        )
        assert m.source_unit == "kg"


# ---------------------------------------------------------------------------
# UserProfile round-trip
# ---------------------------------------------------------------------------


class TestUserProfileRoundTrip:
    def test_to_dict_from_dict_preserves_fields(self) -> None:
        original = UserProfile(user_id="alice", display_name="Alice Smith")
        restored = UserProfile.from_dict(original.to_dict())
        assert restored == original

    def test_from_dict_non_dict_raises(self) -> None:
        with pytest.raises(TypeError):
            UserProfile.from_dict("alice")  # type: ignore[arg-type]

    def test_from_dict_missing_display_name_raises(self) -> None:
        with pytest.raises(KeyError):
            UserProfile.from_dict({"user_id": "alice"})
