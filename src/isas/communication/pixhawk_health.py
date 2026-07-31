"""Pure helpers for checking the agreed ArduSub Pixhawk configuration."""

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping

EXPECTED_PARAMETERS: Dict[str, float] = {
    "FRAME_CONFIG": 1.0,
    "SERVO1_FUNCTION": 33.0,
    "SERVO2_FUNCTION": 34.0,
    "SERVO3_FUNCTION": 35.0,
    "SERVO4_FUNCTION": 36.0,
    "SERVO5_FUNCTION": 37.0,
    "SERVO6_FUNCTION": 38.0,
    "MOT_PWM_TYPE": 0.0,
    "FS_PILOT_INPUT": 2.0,
    "FS_PILOT_TIMEOUT": 3.0,
    "FS_GCS_ENABLE": 2.0,
    "FS_GCS_TIMEOUT": 5.0,
    "BATT_MONITOR": 0.0,
    "RC_PROTOCOLS": 0.0,
    "FLTMODE_CH": 0.0,
    "AHRS_ORIENTATION": 0.0,
    "COMPASS_USE": 1.0,
}


@dataclass(frozen=True)
class ParameterCheck:
    """Result for one parameter read from the vehicle."""

    name: str
    expected: float
    actual: float
    passed: bool


def evaluate_parameters(
    actual: Mapping[str, float],
    expected: Mapping[str, float] = EXPECTED_PARAMETERS,
    tolerance: float = 0.01,
) -> List[ParameterCheck]:
    """Compare a parameter snapshot against the known-safe baseline."""
    checks = []
    for name, expected_value in expected.items():
        actual_value = actual.get(name)
        passed = (
            actual_value is not None
            and abs(actual_value - expected_value) <= tolerance
        )
        checks.append(
            ParameterCheck(
                name=name,
                expected=expected_value,
                actual=float("nan") if actual_value is None else actual_value,
                passed=passed,
            )
        )
    return checks


def all_passed(checks: Iterable[ParameterCheck]) -> bool:
    """Return True only when every supplied check passed."""
    return all(check.passed for check in checks)
