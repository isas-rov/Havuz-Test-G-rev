"""Small, hardware-independent yaw helpers used by the mission runner."""


def wrap_degrees(angle: float) -> float:
    """Wrap an angle to the half-open interval [-180, 180)."""
    return (angle + 180.0) % 360.0 - 180.0


def right_turn_target(current_yaw: float, degrees: float) -> float:
    """Return a clockwise/right target heading in the [0, 360) interval."""
    if degrees < 0.0:
        raise ValueError("right-turn degrees must not be negative")
    return (current_yaw + degrees) % 360.0


def yaw_hold_command(
    current_yaw: float,
    target_yaw: float,
    proportional_gain: float = 5.0,
    maximum: int = 180,
) -> int:
    """Create a bounded MANUAL_CONTROL yaw demand for heading hold."""
    if proportional_gain <= 0.0:
        raise ValueError("proportional_gain must be positive")
    if maximum <= 0:
        raise ValueError("maximum must be positive")
    error = wrap_degrees(target_yaw - current_yaw)
    command = int(round(error * proportional_gain))
    return max(-maximum, min(maximum, command))
