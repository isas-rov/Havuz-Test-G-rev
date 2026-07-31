#!/usr/bin/env python3
"""Read-only Pixhawk/ArduSub health and parameter check.

This tool never changes mode, parameters, arming state, or actuator outputs.
"""

import argparse
import glob
import json
import math
import os
import re
import sys
import time
from pathlib import Path

from isas.communication.pixhawk_health import (
    EXPECTED_PARAMETERS,
    all_passed,
    evaluate_parameters,
)

try:
    from pymavlink import mavutil
except ImportError as exc:  # pragma: no cover - depends on deployment image
    raise SystemExit(
        "pymavlink is missing. Install with: python -m pip install -e '.[vehicle]'"
    ) from exc


def auto_connection() -> str:
    """Find a likely Pixhawk serial device without opening every serial port."""
    if os.name == "nt":
        try:
            from serial.tools import list_ports
        except ImportError as exc:
            raise RuntimeError(
                "pyserial is required for Windows port discovery"
            ) from exc

        ports = list(list_ports.comports())
        preferred_words = ("px4", "pixhawk", "ardupilot", "fmuv2", "3d robotics")
        preferred = [
            port.device
            for port in ports
            if any(word in (port.description or "").lower() for word in preferred_words)
        ]
        candidates = preferred or [port.device for port in ports]
        if not candidates:
            raise RuntimeError("no Windows serial port was found")
        return candidates[0]

    by_id = sorted(glob.glob("/dev/serial/by-id/*"))
    preferred = [
        path
        for path in by_id
        if any(word in path.lower() for word in ("px4", "pixhawk", "ardupilot"))
    ]
    if preferred:
        return preferred[0]
    if by_id:
        return by_id[0]
    if Path("/dev/ttyACM0").exists():
        return "/dev/ttyACM0"
    raise RuntimeError("no Pixhawk serial device was found")


def open_connection(connection: str, baud: int):
    """Open MAVLink, avoiding Windows reserved COM-name file detection."""
    if os.name == "nt" and re.fullmatch(r"COM\d+", connection, re.IGNORECASE):
        return mavutil.mavserial(connection, baud=baud, source_system=254)
    return mavutil.mavlink_connection(connection, baud=baud, source_system=254)


def read_parameter(master, name: str, timeout: float = 3.0) -> float:
    master.mav.param_request_read_send(
        master.target_system,
        master.target_component,
        name.encode("ascii"),
        -1,
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        message = master.recv_match(type="PARAM_VALUE", blocking=True, timeout=0.5)
        if message is None:
            continue
        param_id = message.param_id
        if isinstance(param_id, bytes):
            param_id = param_id.decode("ascii", errors="replace")
        if param_id.rstrip("\x00") == name:
            return float(message.param_value)
    raise TimeoutError(f"parameter not received: {name}")


def request_streams(master) -> None:
    master.mav.request_data_stream_send(
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL,
        5,
        1,
    )


def collect_status(master, seconds: float = 4.0):
    attitude = None
    status = None
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        message = master.recv_match(blocking=True, timeout=0.5)
        if message is None:
            continue
        if message.get_type() == "ATTITUDE":
            attitude = message
        elif message.get_type() == "SYS_STATUS":
            status = message
        if attitude is not None and status is not None:
            break
    return attitude, status


def sensor_report(status):
    sensors = {
        "gyro": mavutil.mavlink.MAV_SYS_STATUS_SENSOR_3D_GYRO,
        "accelerometer": mavutil.mavlink.MAV_SYS_STATUS_SENSOR_3D_ACCEL,
        "compass": mavutil.mavlink.MAV_SYS_STATUS_SENSOR_3D_MAG,
        "barometer": mavutil.mavlink.MAV_SYS_STATUS_SENSOR_ABSOLUTE_PRESSURE,
    }
    result = {}
    if status is None:
        return {
            name: {
                "state": "NO_DATA",
                "present": False,
                "enabled": False,
                "healthy": False,
            }
            for name in sensors
        }
    for name, flag in sensors.items():
        present = bool(status.onboard_control_sensors_present & flag)
        enabled = bool(status.onboard_control_sensors_enabled & flag)
        healthy = bool(status.onboard_control_sensors_health & flag)
        result[name] = {
            "state": "HEALTHY" if present and enabled and healthy else "CHECK",
            "present": present,
            "enabled": enabled,
            "healthy": healthy,
        }
    return result


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--connection",
        default="auto",
        help="Serial path, COM port, or MAVLink URL. Default: auto",
    )
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--json", dest="json_path", help="Optional JSON report path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    connection = auto_connection() if args.connection == "auto" else args.connection
    print(f"Connection: {connection}")
    try:
        master = open_connection(connection, args.baud)
    except Exception as exc:
        print(
            f"FAIL: cannot open {connection}. Disconnect Mission Planner or another "
            f"program using the port. Detail: {exc}",
            file=sys.stderr,
        )
        return 2
    heartbeat = master.wait_heartbeat(timeout=15)
    if heartbeat is None:
        print("FAIL: heartbeat was not received", file=sys.stderr)
        return 2

    is_submarine = heartbeat.type == mavutil.mavlink.MAV_TYPE_SUBMARINE
    is_armed = bool(
        heartbeat.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
    )
    vehicle_name = "SUBMARINE" if is_submarine else "WRONG"
    print(f"Vehicle type: {heartbeat.type} ({vehicle_name})")
    print(f"Armed: {is_armed}")

    parameters = {}
    read_errors = []
    for name in EXPECTED_PARAMETERS:
        try:
            parameters[name] = read_parameter(master, name)
        except TimeoutError:
            read_errors.append(name)

    checks = evaluate_parameters(parameters)
    for check in checks:
        actual = "MISSING" if math.isnan(check.actual) else f"{check.actual:g}"
        marker = "PASS" if check.passed else "FAIL"
        print(
            f"{marker:4} {check.name:18} actual={actual:>7} "
            f"expected={check.expected:g}"
        )

    request_streams(master)
    attitude, status = collect_status(master)
    attitude_report = None
    if attitude is not None:
        attitude_report = {
            "roll_deg": round(math.degrees(attitude.roll), 2),
            "pitch_deg": round(math.degrees(attitude.pitch), 2),
            "yaw_deg": round(math.degrees(attitude.yaw) % 360.0, 2),
        }
        print(
            "Attitude: roll={roll_deg:.2f} pitch={pitch_deg:.2f} "
            "yaw={yaw_deg:.2f}".format(**attitude_report)
        )

    sensors = sensor_report(status)
    print(
        "Sensors: "
        + ", ".join(
            f"{key}={value['state']}"
            f"(present={value['present']},enabled={value['enabled']},"
            f"healthy={value['healthy']})"
            for key, value in sensors.items()
        )
    )

    required_sensor_names = ("gyro", "accelerometer", "compass")
    required_sensors_healthy = all(
        sensors[name]["state"] == "HEALTHY" for name in required_sensor_names
    )

    passed = (
        is_submarine
        and not is_armed
        and not read_errors
        and all_passed(checks)
        and attitude_report is not None
        and required_sensors_healthy
    )
    report = {
        "connection": connection,
        "read_only": True,
        "vehicle_is_submarine": is_submarine,
        "armed": is_armed,
        "parameters": parameters,
        "parameter_read_errors": read_errors,
        "parameter_checks_passed": all_passed(checks),
        "attitude": attitude_report,
        "sensors": sensors,
        "passed": passed,
    }
    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
        )
        print(f"Report: {args.json_path}")

    print("RESULT: {}".format("PASS" if passed else "CHECK_REQUIRED"))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
