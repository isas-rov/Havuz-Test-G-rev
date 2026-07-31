import math

from isas.communication.pixhawk_health import (
    EXPECTED_PARAMETERS,
    all_passed,
    evaluate_parameters,
)


def test_known_pixhawk_baseline_passes() -> None:
    checks = evaluate_parameters(dict(EXPECTED_PARAMETERS))
    assert all_passed(checks)


def test_missing_parameter_fails_without_raising() -> None:
    parameters = dict(EXPECTED_PARAMETERS)
    parameters.pop("FRAME_CONFIG")
    checks = evaluate_parameters(parameters)
    frame_check = next(check for check in checks if check.name == "FRAME_CONFIG")
    assert not frame_check.passed
    assert math.isnan(frame_check.actual)
    assert not all_passed(checks)


def test_wrong_motor_function_fails() -> None:
    parameters = dict(EXPECTED_PARAMETERS)
    parameters["SERVO4_FUNCTION"] = 0.0
    checks = evaluate_parameters(parameters)
    assert not all_passed(checks)
