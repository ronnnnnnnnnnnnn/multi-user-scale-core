# multi-user-scale-core

[![PyPI version](https://img.shields.io/pypi/v/multi-user-scale-core.svg)](https://pypi.org/project/multi-user-scale-core/)

Not every smart scale integration surfaces who's standing on the scale. This library solves that: given a weight reading and a set of users with history, it returns a ranked list of likely owners. Pure Python, no runtime dependencies. Fully typed (PEP 561).

## Features

- **WeightRouter**: Route incoming weight measurements to users using adaptive tolerance.
- **Adaptive tolerance**: Exponentially-weighted reference weight, variance-based tolerance, and recency scaling that automatically widens the window when a user hasn't weighed in recently.
- **Persistence**: `to_dict()` / `from_dict()` for saving and restoring router state across restarts.
- **Models**: `WeightMeasurement`, `UserProfile`, `RouterConfig`, `MeasurementCandidate`.

[![Buy Me A Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/ronnnnnnn)


## Installation

Requires Python 3.10+. Install using pip:

```bash
pip install multi-user-scale-core
```

## Quick Start

```python
from multi_user_scale_core import RouterConfig, UserProfile, WeightMeasurement, WeightRouter
from datetime import datetime, timezone

router = WeightRouter(config=RouterConfig())
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
# candidates: list[MeasurementCandidate], ordered by match quality.
# Matched users come first, sorted by proximity to their reference weight.
# Users with no history yet are appended at the end.
#
# Matched candidates include:
#   .reference_weight_kg  — the weighted-average reference used for comparison
#   .tolerance_kg         — the tolerance band that accepted this reading
# No-history candidates have both fields as None.

# Once confirmed (e.g. by the user), record the measurement
router.record_measurement_for_user("alice", measurement)
```

## Usage

### Reassigning and removing measurements

```python
# Move the latest measurement from alice to bob (e.g. after user correction)
router.reassign_measurement("alice", "bob")

# Move a specific measurement by ID
router.reassign_measurement("alice", "bob", measurement_id="abc123")

# Remove the latest measurement for a user
router.remove_measurement("alice")

# Remove a specific measurement by ID
router.remove_measurement("alice", measurement_id="abc123")
```

### Managing users

```python
router.set_users([
    UserProfile(user_id="alice", display_name="Alice"),
    UserProfile(user_id="bob", display_name="Bob"),
])
```

> **Note**: `set_users()` replaces the entire user list. History for any user not present in the new list is permanently discarded. Call `to_dict()` first if you need to preserve that history.

### Persistence

```python
# Serialise state (e.g. to Home Assistant config entry data)
payload = router.to_dict()

# Restore state
router = WeightRouter.from_dict(payload)

# Inject a custom clock (useful in tests or when the stored "now" matters
# for pruning stale history on first mutation after restore)
router = WeightRouter.from_dict(payload, now_provider=lambda: my_fixed_time)
```

`to_dict()` includes a `"now"` snapshot timestamp for human inspection. It is **not** used during `from_dict()` restoration.

### Configuration

```python
config = RouterConfig(
    history_retention_days=90,       # drop measurements older than this
    max_history_size=100,            # cap per-user history length
    tolerance_percentage=0.04,       # base tolerance as fraction of body weight
    min_tolerance_kg=1.5,            # floor on tolerance regardless of body weight
    variance_window_days=30,         # window for variance-based adaptive tolerance
    reference_window_days=7,         # window for computing the reference weight
    min_measurements_for_adaptive=5, # minimum history needed for variance adaptation
)
```

Default tolerance constants are exported for convenience:

```python
from multi_user_scale_core import (
    DEFAULT_TOLERANCE_PERCENTAGE,  # 0.04
    MIN_TOLERANCE_KG,              # 1.5
    MAX_TOLERANCE_KG,              # 5.0
    MIN_MEASUREMENTS_FOR_ADAPTIVE, # 5
    REFERENCE_WINDOW_DAYS,         # 7
    VARIANCE_WINDOW_DAYS,          # 30
)
```

### Error handling

All errors inherit from `RouterError`:

```python
from multi_user_scale_core import (
    DuplicateMeasurementError,    # measurement_id already exists in history
    MeasurementNotFoundError,     # referenced measurement does not exist
    MeasurementValidationError,   # weight is NaN, infinite, or not a number
    RouterError,                  # base class
    UserNotFoundError,            # user_id not registered with set_users()
)
```

## Compatibility

- Python 3.10+
- No runtime dependencies


## Support the Project

If you find this project helpful, consider buying me a coffee! Your support helps maintain and improve this library.

[![Buy Me A Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/ronnnnnnn)


## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
