"""Central configuration for lap sampling and rule-based analysis."""

ANALYSIS_CONFIG = {
    "sample_distance_m": 5.0,
    "minimum_samples": 20,
    "start_line_tolerance_m": 250.0,
    "start_line_negative_tolerance_m": 25.0,
    "minimum_recorded_distance_m": 1000.0,
    "wheel_spin": {
        "enabled": True, "min_throttle": 0.15, "min_speed_kph": 5.0,
        "slip_threshold": 0.10, "min_duration_ms": 80,
    },
    "lockup": {
        "enabled": True, "min_brake": 0.35, "min_speed_kph": 20.0,
        "speed_ratio": 0.82, "slip_threshold": -0.10, "min_duration_ms": 60,
    },
    "comparison_step_m": 10.0,
    "maximum_comparison_gap_m": 50.0,
    "large_loss_ms": 100.0,
    "loss_zone_m": 100.0,
    "loss_zone_min_ms": 50.0,
    "max_loss_candidates": 8,
    "max_pace_zones": 14,
}

TYRE_NAMES = ("rear_left", "rear_right", "front_left", "front_right")


def tyre_values(values):
    """Convert the F1 UDP RL, RR, FL, FR array order to named values."""
    values = list(values or [])
    return {name: values[i] if i < len(values) else None for i, name in enumerate(TYRE_NAMES)}
