import pytest

from isas.control.yaw_control import (
    right_turn_target,
    wrap_degrees,
    yaw_hold_command,
)


@pytest.mark.parametrize(
    ("angle", "expected"),
    [(0.0, 0.0), (190.0, -170.0), (-190.0, 170.0), (360.0, 0.0)],
)
def test_wrap_degrees(angle: float, expected: float) -> None:
    assert wrap_degrees(angle) == pytest.approx(expected)


def test_right_turn_target_wraps_north() -> None:
    assert right_turn_target(350.0, 90.0) == pytest.approx(80.0)


def test_yaw_hold_uses_shortest_direction() -> None:
    assert yaw_hold_command(350.0, 10.0, proportional_gain=2.0) == 40
    assert yaw_hold_command(10.0, 350.0, proportional_gain=2.0) == -40


def test_yaw_hold_is_bounded() -> None:
    assert yaw_hold_command(0.0, 90.0, proportional_gain=10.0, maximum=120) == 120
