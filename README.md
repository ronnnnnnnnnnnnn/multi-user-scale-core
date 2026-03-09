# multi-user-scale-core

Core weight routing primitives for multi-user scale integrations. Pure Python, no framework dependencies. Used by [Multi-User Scale Router](https://github.com/ronnnnnnnnnnnnn/etekcity_fitness_scale_ble) and other integrations that need to route scale measurements to multiple users.

## Features

- **WeightRouter**: Route incoming weight measurements to users using adaptive tolerance.
- **Adaptive tolerance**: Reference weight (exponential decay), variance-based tolerance, recency scaling.
- **Persistence**: `WeightRouter.to_dict()` / `from_dict()` for saving and restoring state.
- **Models**: `WeightMeasurement`, `UserProfile`, `RouterConfig`, `MeasurementCandidate`.

## Install

```bash
pip install multi-user-scale-core
```

## Usage

```python
from multi_user_scale_core import (
    RouterConfig,
    UserProfile,
    WeightMeasurement,
    WeightRouter,
)
from datetime import datetime, timezone

router = WeightRouter(config=RouterConfig(history_retention_days=90, max_history_size=100))
router.set_users([
    UserProfile(user_id="alice", display_name="Alice"),
    UserProfile(user_id="bob", display_name="Bob"),
])

# Evaluate an incoming measurement (e.g. from a scale sensor)
measurement = WeightMeasurement(
    weight_kg=75.2,
    timestamp=datetime.now(tz=timezone.utc),
    source_id="sensor.scale",
)
candidates = router.evaluate_measurement(measurement)
# candidates: ordered list of MeasurementCandidate (user_id, reference_weight_kg, tolerance_kg)

# Record a measurement for a user (e.g. after user confirmation)
router.record_measurement_for_user("alice", measurement)
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
