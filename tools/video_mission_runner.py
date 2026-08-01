#!/usr/bin/env python3
"""Guarded ArduSub runner for the 2026 advanced-category video route.

The default invocation is a hardware-free dry run. Real output requires both an
explicit connection and the --enable-output interlock. The open-loop circle size
and straight-leg distances must be calibrated in a pool before a recording run.
"""

import argparse
import json
import os
import re
import signal
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from isas.control.video_mission import MotionKind, VideoMissionPlan

try:
    from pymavlink import mavutil
except ImportError:  # pragma: no cover - dry-run works without pymavlink
    mavutil = None


CONTROL_PERIOD = 0.1
NEUTRAL_VERTICAL = 500
ESC_NEUTRAL_SETTLE_SECONDS = 5.0
ARMED_MANUAL_NEUTRAL_CHECK_SECONDS = 1.0
NEUTRAL_PWM_TOLERANCE = 10
OUTPUT_CONFIRMATION = "MOTORS_ARE_CLEAR"
ALL_MOTORS_CONFIRMATION = "ALL_MOTORS_RESTRAINED"
HIGH_OUTPUT_CONFIRMATION = "HIGH_OUTPUT_RESTRAINED"
LONG_OUTPUT_CONFIRMATION = "LONG_FULL_OUTPUT_RESTRAINED"
MAV_MODE_FLAG_SAFETY_ARMED = 128
MOTOR_TEST_THROTTLE_PWM = 1
MOTOR_TEST_ORDER_BOARD = 2
MOTOR_NEUTRAL_PWM = 1500
DEFAULT_AUDIT_LOG = (
    Path(__file__).resolve().parents[1]
    / "logs"
    / "pool_tests"
    / "pixhawk-audit.jsonl"
)


def json_safe(value):
    """Return a JSON-serialisable representation of a MAVLink value."""
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


class PixhawkAuditLog:
    """Append durable JSONL events and latest available MAVLink telemetry."""

    def __init__(self, path: Path, test_name: str, connection: str):
        self.path = path
        self.test_name = test_name
        self.connection = connection
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        self.session_id = f"{stamp}-{os.getpid()}-{uuid.uuid4().hex[:8]}"

    def event(self, name: str, data=None, telemetry=None) -> None:
        payload = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "test": self.test_name,
            "connection": self.connection,
            "event": name,
            "data": json_safe(data or {}),
            "telemetry": json_safe(telemetry or {}),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    @staticmethod
    def message_dict(message):
        if message is None or not hasattr(message, "get_type"):
            return None, None
        message_type = message.get_type()
        if not message_type or message_type == "BAD_DATA":
            return None, None
        try:
            content = message.to_dict()
        except Exception:
            content = {"raw": str(message)}
        return message_type, content

    def capture(self, master, name: str, data=None, duration: float = 0.4) -> dict:
        """Record the newest sample of every MAVLink type available now."""
        latest = {}
        cached = getattr(master, "messages", {}) or {}
        for message in cached.values():
            message_type, content = self.message_dict(message)
            if message_type is not None:
                latest[message_type] = content

        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            message = master.recv_match(blocking=True, timeout=0.05)
            message_type, content = self.message_dict(message)
            if message_type is not None:
                latest[message_type] = content

        details = dict(data or {})
        heartbeat = latest.get("HEARTBEAT")
        if isinstance(heartbeat, dict):
            base_mode = heartbeat.get("base_mode")
            if isinstance(base_mode, int):
                details["armed_from_heartbeat"] = bool(
                    base_mode & MAV_MODE_FLAG_SAFETY_ARMED
                )
        details["telemetry_message_types"] = sorted(latest)
        details["telemetry_type_count"] = len(latest)
        self.event(name, details, latest)
        return latest


def handle_stop_signal(_signum, _frame) -> None:
    """Route service stops through the normal neutral/disarm cleanup path."""
    raise KeyboardInterrupt


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--connection",
        help="MAVLink serial path/COM port/URL; omit for safe dry-run",
    )
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument(
        "--audit-log",
        type=Path,
        default=DEFAULT_AUDIT_LOG,
        help="Cumulative JSONL path for ARM/DISARM and MAVLink telemetry events",
    )
    parser.add_argument("--forward", type=int, default=200)
    parser.add_argument("--circle-forward", type=int, default=150)
    parser.add_argument("--circle-yaw", type=int, default=150)
    parser.add_argument(
        "--turn-yaw",
        "--turn-yaw-max",
        dest="turn_yaw",
        type=int,
        default=80,
        help="Open-loop right-turn command magnitude (legacy alias: --turn-yaw-max)",
    )
    parser.add_argument(
        "--turn-seconds",
        type=float,
        default=2.0,
        help="Open-loop right-turn command time; calibrate in the pool",
    )
    parser.add_argument(
        "--circle-seconds",
        type=float,
        default=12.0,
        help="Open-loop circle command time; calibrate in the pool",
    )
    parser.add_argument(
        "--straight-yaw-trim",
        type=int,
        default=0,
        help="Constant open-loop yaw correction while driving straight (-100..100)",
    )
    parser.add_argument(
        "--test",
        choices=(
            "mission",
            "motor",
            "motor-all",
            "straight",
            "vertical",
            "combined",
            "turn-right",
            "circle",
        ),
        default="mission",
        help="Run the full mission or one guarded pool test",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=2.0,
        help="Test movement time in seconds (limits depend on test type)",
    )
    parser.add_argument(
        "--countdown",
        type=int,
        default=10,
        help="Disarmed safety countdown before a real straight test (5-60)",
    )
    parser.add_argument(
        "--dry-run-hold",
        type=int,
        default=0,
        help="Safe no-output hold used to verify detached service operation (0-60s)",
    )
    parser.add_argument(
        "--motor-number",
        type=int,
        choices=range(1, 7),
        default=1,
        help="Board-order motor number for a guarded individual test (1-6)",
    )
    parser.add_argument(
        "--motor-pwm",
        type=int,
        default=1525,
        help="Individual motor-test PWM (1475-1525, excluding neutral 1500)",
    )
    parser.add_argument(
        "--vertical",
        type=int,
        default=550,
        help="Vertical-test MANUAL_CONTROL z value (0-1000; 500 is neutral)",
    )
    parser.add_argument(
        "--degrees",
        type=float,
        default=30.0,
        help="Intended turn angle label only; actual angle is measured externally",
    )
    parser.add_argument("--yaw-sign", type=int, choices=(-1, 1), default=1)
    parser.add_argument(
        "--enable-output",
        action="store_true",
        help="Allow mode change, ARM, and MANUAL_CONTROL output",
    )
    parser.add_argument(
        "--confirm",
        help=f"Second output interlock; required value: {OUTPUT_CONFIRMATION}",
    )
    parser.add_argument(
        "--confirm-all-motors",
        help=(
            "Additional interlock for simultaneous M1-M6 output; required value: "
            f"{ALL_MOTORS_CONFIRMATION}"
        ),
    )
    parser.add_argument(
        "--confirm-high-output",
        help=(
            "Additional interlock for high vertical or forward output; "
            f"required value: {HIGH_OUTPUT_CONFIRMATION}"
        ),
    )
    parser.add_argument(
        "--confirm-long-vertical",
        help=(
            "Additional interlock for vertical output longer than 5 seconds; "
            f"required value: {LONG_OUTPUT_CONFIRMATION}"
        ),
    )
    parser.add_argument(
        "--confirm-long-forward",
        help=(
            "Additional interlock for high forward output longer than 5 seconds; "
            f"required value: {LONG_OUTPUT_CONFIRMATION}"
        ),
    )
    return parser.parse_args(argv)


def validate_controls(args) -> None:
    if not 1 <= abs(args.forward) <= 1000:
        raise ValueError("--forward magnitude must be between 1 and 1000")
    for name in ("circle_forward", "circle_yaw", "turn_yaw"):
        value = abs(getattr(args, name))
        if not 1 <= value <= 400:
            raise ValueError(f"--{name.replace('_', '-')} must be between 1 and 400")
    if not 1.0 <= args.duration <= 60.0:
        raise ValueError("--duration must be between 1 and 60 seconds")
    if args.test in ("motor", "motor-all") and args.duration > 3.0:
        raise ValueError("motor tests require --duration between 1 and 3 seconds")
    if not 1475 <= args.motor_pwm <= 1525 or args.motor_pwm == MOTOR_NEUTRAL_PWM:
        raise ValueError("--motor-pwm must be 1475-1525 and must not be neutral 1500")
    if not 5 <= args.countdown <= 60:
        raise ValueError("--countdown must be between 5 and 60 seconds")
    if not 0 <= args.dry_run_hold <= 60:
        raise ValueError("--dry-run-hold must be between 0 and 60 seconds")
    if not 0 <= args.vertical <= 1000:
        raise ValueError("--vertical must be between 0 and 1000")
    if args.test in ("vertical", "combined") and args.vertical == NEUTRAL_VERTICAL:
        raise ValueError("--vertical must not be 500 for a vertical/combined test")
    if not 5.0 <= args.degrees <= 90.0:
        raise ValueError("--degrees must be between 5 and 90")
    if not 0.2 <= args.turn_seconds <= 10.0:
        raise ValueError("--turn-seconds must be between 0.2 and 10 seconds")
    if not 1.0 <= args.circle_seconds <= 60.0:
        raise ValueError("--circle-seconds must be between 1 and 60 seconds")
    if not -100 <= args.straight_yaw_trim <= 100:
        raise ValueError("--straight-yaw-trim must be between -100 and 100")


def dry_run(plan: VideoMissionPlan) -> int:
    print("VIDEO MISSION RUNNER - DRY RUN - HARDWARE OUTPUT DISABLED")
    for index, step in enumerate(plan, start=1):
        print(
            f"[{index:02d}/{len(plan.steps):02d}] {step.name:24} "
            f"kind={step.kind.value:12} duration={step.minimum_seconds:4.1f}s "
            f"turn={step.degrees:5.0f}deg distance={step.target_distance_m:3.1f}m "
            f"diameter={step.diameter_m:3.1f}m"
        )
    print("Control: MANUAL open-loop mixer; no compass heading feedback")
    print("RESULT: PLAN_VALID, NO CONNECTION, NO ARM, NO MOTOR OUTPUT")
    return 0


def dry_run_motion_test(args) -> int:
    print(f"{args.test.upper()} TEST - DRY RUN - HARDWARE OUTPUT DISABLED")
    print(f"Would wait {args.countdown}s while DISARMED")
    if args.test == "straight":
        action = (
            f"forward={args.forward}, yaw_trim={args.straight_yaw_trim} "
            f"for {args.duration:.1f}s"
        )
    elif args.test == "motor":
        action = (
            f"motor M{args.motor_number} at PWM={args.motor_pwm} "
            f"for {args.duration:.1f}s"
        )
    elif args.test == "motor-all":
        action = (
            f"all board-order motors M1-M6 simultaneously at PWM={args.motor_pwm} "
            f"for {args.duration:.1f}s"
        )
    elif args.test == "vertical":
        action = f"vertical z={args.vertical} for {args.duration:.1f}s"
    elif args.test == "combined":
        action = (
            f"forward={args.forward}, vertical z={args.vertical}, "
            f"yaw_trim={args.straight_yaw_trim} for {args.duration:.1f}s"
        )
    elif args.test == "turn-right":
        action = (
            f"yaw={args.turn_yaw}, yaw_sign={args.yaw_sign:+d} for "
            f"{args.turn_seconds:.1f}s; intended {args.degrees:.1f}deg is measured "
            "externally"
        )
    elif args.test == "circle":
        action = (
            f"one right circle with forward={args.circle_forward}, "
            f"yaw={args.circle_yaw}, yaw_sign={args.yaw_sign:+d} for "
            f"{args.circle_seconds:.1f}s"
        )
    else:  # guarded by argparse
        raise ValueError(f"unsupported test: {args.test}")
    print(f"Would ARM, command {action}, then neutral")
    print("Would DISARM before exit")
    if args.dry_run_hold:
        print(f"Safe detached-service hold: {args.dry_run_hold}s")
        for remaining in range(args.dry_run_hold, 0, -1):
            print(f"DRY HOLD {remaining:02d}s - NO HARDWARE OUTPUT")
            time.sleep(1.0)
    print("RESULT: TEST_VALID, NO CONNECTION, NO ARM, NO MOTOR OUTPUT")
    return 0


GCS_SOURCE_SYSTEM = 255


def open_connection(connection: str, baud: int):
    if mavutil is None:
        raise RuntimeError("pymavlink is required for a real connection")
    if os.name == "nt" and re.fullmatch(r"COM\d+", connection, re.IGNORECASE):
        return mavutil.mavserial(
            connection, baud=baud, source_system=GCS_SOURCE_SYSTEM
        )
    return mavutil.mavlink_connection(
        connection, baud=baud, source_system=GCS_SOURCE_SYSTEM
    )


class ArduSubRunner:
    def __init__(self, master, args, audit=None):
        self.master = master
        self.args = args
        self.audit = audit
        self.last_heartbeat = 0.0

    def audit_event(self, name: str, data=None, capture: bool = False) -> None:
        if self.audit is None:
            return
        if capture:
            self.audit.capture(self.master, name, data)
        else:
            self.audit.event(name, data)

    def send_gcs_heartbeat(self) -> None:
        now = time.monotonic()
        if now - self.last_heartbeat < 0.9:
            return
        self.master.mav.heartbeat_send(
            mavutil.mavlink.MAV_TYPE_GCS,
            mavutil.mavlink.MAV_AUTOPILOT_INVALID,
            0,
            0,
            0,
        )
        self.last_heartbeat = now

    def request_audit_streams(self) -> None:
        """Ask ArduPilot to stream every telemetry group available on this link."""
        self.master.mav.request_data_stream_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_DATA_STREAM_ALL,
            4,
            1,
        )

    def send_control(
        self,
        forward: int = 0,
        yaw: int = 0,
        vertical: int = NEUTRAL_VERTICAL,
    ) -> None:
        self.send_gcs_heartbeat()
        self.master.mav.manual_control_send(
            self.master.target_system,
            int(forward),
            0,
            int(vertical),
            int(yaw * self.args.yaw_sign),
            0,
        )

    def neutral(self, seconds: float = 1.0) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.send_control()
            time.sleep(CONTROL_PERIOD)

    def set_mode(self, mode_name: str) -> None:
        mode_id = (self.master.mode_mapping() or {}).get(mode_name)
        if mode_id is None:
            raise RuntimeError(f"{mode_name} mode was not reported by ArduSub")
        self.master.mav.set_mode_send(
            self.master.target_system,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            mode_id,
        )
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            heartbeat = self.master.recv_match(
                type="HEARTBEAT", blocking=True, timeout=1
            )
            if heartbeat is not None and heartbeat.custom_mode == mode_id:
                return
        raise RuntimeError(f"{mode_name} mode change was not confirmed")

    def set_manual(self) -> None:
        self.set_mode("MANUAL")

    def require_neutral_motor_outputs(self, event_name: str) -> None:
        """Refuse to continue unless MAIN OUT 1-6 all report neutral PWM."""
        if self.audit is None:
            raise RuntimeError("Pixhawk audit is required for neutral-output checks")
        telemetry = self.audit.capture(self.master, event_name, duration=0.5)
        outputs = telemetry.get("SERVO_OUTPUT_RAW")
        if not isinstance(outputs, dict):
            raise RuntimeError("SERVO_OUTPUT_RAW unavailable; refusing to ARM/test")
        values = {
            motor_number: outputs.get(f"servo{motor_number}_raw")
            for motor_number in range(1, 7)
        }
        invalid = {
            motor_number: pwm
            for motor_number, pwm in values.items()
            if not isinstance(pwm, int)
            or abs(pwm - MOTOR_NEUTRAL_PWM) > NEUTRAL_PWM_TOLERANCE
        }
        if invalid:
            self.audit.event(
                "NEUTRAL_OUTPUT_CHECK_FAILED",
                {"outputs": values, "invalid": invalid},
            )
            raise RuntimeError(
                f"MAIN OUT 1-6 are not neutral; refusing output: {invalid}"
            )
        print(f"MAIN OUT 1-6 neutral check: PASS {values}")

    def set_output_safety(self, allow_outputs: bool) -> None:
        """Explicitly unlock or lock PWM outputs for a buttonless Pixhawk."""
        action = "UNLOCK" if allow_outputs else "LOCK"
        self.audit_event(f"OUTPUT_SAFETY_{action}_REQUEST")
        state = (
            mavutil.mavlink.SAFETY_SWITCH_STATE_DANGEROUS
            if allow_outputs
            else mavutil.mavlink.SAFETY_SWITCH_STATE_SAFE
        )
        for _attempt in range(3):
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_DO_SET_SAFETY_SWITCH_STATE,
                0,
                state,
                0,
                0,
                0,
                0,
                0,
                0,
            )
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                ack = self.master.recv_match(
                    type="COMMAND_ACK", blocking=True, timeout=0.5
                )
                if ack is None:
                    continue
                if ack.command != mavutil.mavlink.MAV_CMD_DO_SET_SAFETY_SWITCH_STATE:
                    continue
                if ack.result != mavutil.mavlink.MAV_RESULT_ACCEPTED:
                    action = "enable" if allow_outputs else "lock"
                    raise RuntimeError(
                        f"hardware output safety {action} rejected: "
                        f"MAV_RESULT={ack.result}"
                    )
                state_name = "UNLOCKED" if allow_outputs else "LOCKED"
                print(f"Hardware output safety: {state_name}")
                self.audit_event(
                    f"OUTPUT_SAFETY_{state_name}",
                    {"mav_result": int(ack.result)},
                    capture=True,
                )
                return
            time.sleep(0.5)
        raise RuntimeError("hardware output safety command was not acknowledged")

    def wait_armed_state(self, armed: bool, timeout: float) -> None:
        """Wait for heartbeat armed state without pymavlink API-version coupling."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.send_gcs_heartbeat()
            heartbeat = self.master.recv_match(
                type="HEARTBEAT", blocking=True, timeout=1.0
            )
            if heartbeat is None:
                continue
            heartbeat_armed = bool(
                heartbeat.base_mode & MAV_MODE_FLAG_SAFETY_ARMED
            )
            if heartbeat_armed is armed:
                return
        state = "ARM" if armed else "DISARM"
        raise RuntimeError(f"{state} was not confirmed within {timeout:.0f}s")

    def arm(self) -> None:
        self.audit_event("ARM_REQUEST", capture=True)
        self.master.arducopter_arm()
        self.wait_armed_state(True, timeout=10)
        if not self.master.motors_armed():
            raise RuntimeError("ARM was not confirmed")
        self.audit_event("ARM_CONFIRMED", capture=True)

    def disarm(self) -> None:
        self.neutral(0.8)
        self.audit_event("DISARM_REQUEST", capture=True)
        self.master.arducopter_disarm()
        self.wait_armed_state(False, timeout=8)
        self.audit_event("DISARM_CONFIRMED", capture=True)

    def wait_neutral(self, seconds: float) -> None:
        print(f"Neutral wait: {seconds:.1f}s")
        self.neutral(seconds)

    def disarmed_countdown(self, seconds: int, test_name: str) -> None:
        print("Vehicle must be in water, restrained, and emergency power cut ready.")
        for remaining in range(seconds, 0, -1):
            print(f"{test_name} test starts in {remaining:02d}s (vehicle DISARMED)")
            self.send_gcs_heartbeat()
            time.sleep(1.0)

    def run_straight_test(self, seconds: float) -> None:
        print(
            f"Straight test: {seconds:.1f}s, forward={self.args.forward}, "
            f"yaw_trim={self.args.straight_yaw_trim}"
        )
        self.straight(seconds, "straight_test")

    def send_motor_test_command(self, motor_number: int, pwm: int) -> None:
        """Send one board-order direct-PWM command without refreshing control."""
        # ArduSub 4.7 passes param1 directly to AP_MotorsMatrix::output_test_num,
        # whose output-channel index is zero based despite the MAVLink-facing
        # comment saying 1..N. Keep the CLI human-friendly and translate here.
        output_channel = motor_number - 1
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST,
            0,
            float(output_channel),
            float(MOTOR_TEST_THROTTLE_PWM),
            float(pwm),
            0.0,
            0,
            MOTOR_TEST_ORDER_BOARD,
            0.0,
        )

    def send_motor_test_pwm(self, motor_number: int, pwm: int) -> None:
        """Refresh pilot input and send one board-order direct-PWM command."""
        # A neutral MANUAL_CONTROL packet refreshes the configured pilot-input
        # failsafe. Motor-test mode owns the actual outputs, so it adds no thrust.
        self.send_control()
        self.send_motor_test_command(motor_number, pwm)

    def collect_motor_test_responses(self) -> tuple[int, int | None, list[str]]:
        """Drain motor-test ACK/status messages currently waiting on MAVLink."""
        accepted = 0
        rejection_result = None
        status_texts = []
        while True:
            response = self.master.recv_match(
                type=["COMMAND_ACK", "STATUSTEXT"], blocking=False
            )
            if response is None:
                break
            if response.get_type() == "STATUSTEXT":
                text = str(response.text).strip("\x00")
                if text:
                    status_texts.append(text)
                continue
            if response.command != mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST:
                continue
            if response.result != mavutil.mavlink.MAV_RESULT_ACCEPTED:
                rejection_result = response.result
                break
            accepted += 1
        return accepted, rejection_result, status_texts

    def run_motor_test_phase(self, seconds: float, motor_number: int, pwm: int) -> None:
        """Drive one output while keeping ArduSub's motor-test watchdog alive."""
        deadline = time.monotonic() + seconds
        accepted = False
        status_texts = []
        rejection_result = None
        active_sample_logged = False
        started_at = time.monotonic()
        while time.monotonic() < deadline:
            self.send_motor_test_pwm(motor_number, pwm)
            while True:
                response = self.master.recv_match(
                    type=["COMMAND_ACK", "STATUSTEXT"], blocking=False
                )
                if response is None:
                    break
                if response.get_type() == "STATUSTEXT":
                    text = str(response.text).strip("\x00")
                    if text:
                        status_texts.append(text)
                    continue
                if response.command != mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST:
                    continue
                if response.result != mavutil.mavlink.MAV_RESULT_ACCEPTED:
                    rejection_result = response.result
                    break
                accepted = True
            if (
                accepted
                and not active_sample_logged
                and time.monotonic() - started_at >= 0.3
                and self.audit is not None
            ):
                self.audit.capture(
                    self.master,
                    "MOTOR_OUTPUT_ACTIVE_SAMPLE",
                    {"motor_number": motor_number, "commanded_pwm": pwm},
                    duration=0,
                )
                active_sample_logged = True
            if rejection_result is not None:
                # ArduSub can emit the diagnostic STATUSTEXT immediately after
                # COMMAND_ACK. Keep listening briefly before reporting failure.
                diagnostic_deadline = time.monotonic() + 1.0
                while time.monotonic() < diagnostic_deadline:
                    status = self.master.recv_match(
                        type="STATUSTEXT", blocking=True, timeout=0.2
                    )
                    if status is not None:
                        text = str(status.text).strip("\x00")
                        if text:
                            status_texts.append(text)
                detail = "; ".join(status_texts[-5:]) or "no STATUSTEXT"
                raise RuntimeError(
                    "motor-test command rejected: "
                    f"MAV_RESULT={rejection_result}; detail={detail}"
                )
            time.sleep(CONTROL_PERIOD)
        if not accepted:
            raise RuntimeError("motor-test command was not acknowledged")

    def hold_motor_test_neutral(self, motor_number: int, seconds: float) -> None:
        """Hold the previously tested output at bidirectional neutral."""
        neutral_deadline = time.monotonic() + seconds
        while time.monotonic() < neutral_deadline:
            self.send_motor_test_pwm(motor_number, MOTOR_NEUTRAL_PWM)
            time.sleep(CONTROL_PERIOD)

    def finish_motor_test(self, motor_number: int) -> None:
        # Explicitly command bidirectional neutral before allowing ArduSub's
        # 500 ms motor-test watchdog to stop the test and disarm the vehicle.
        self.hold_motor_test_neutral(motor_number, 0.3)
        time.sleep(0.8)

    def run_motor_test(self, seconds: float, motor_number: int, pwm: int) -> None:
        print(
            f"Individual motor test: M{motor_number}, PWM={pwm}, "
            f"duration={seconds:.1f}s"
        )
        print("All other motor outputs remain at their minimum/test-neutral state.")
        self.run_motor_test_phase(seconds, motor_number, pwm)
        self.finish_motor_test(motor_number)

    def command_all_motors(self, pwm: int) -> None:
        """Refresh failsafe input, then update all six outputs as one batch."""
        self.send_control()
        for motor_number in range(1, 7):
            self.send_motor_test_command(motor_number, pwm)

    def hold_all_motors_neutral(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.command_all_motors(MOTOR_NEUTRAL_PWM)
            time.sleep(CONTROL_PERIOD)

    def run_all_motor_test(self, seconds: float, pwm: int) -> None:
        """Apply the same direct PWM to M1-M6 for a strictly bounded interval."""
        print(
            f"SIMULTANEOUS motor test: M1-M6, PWM={pwm}, "
            f"duration={seconds:.1f}s"
        )
        print("This is direct equal PWM, not a vectored forward command.")
        deadline = time.monotonic() + seconds
        accepted = 0
        status_texts = []
        while time.monotonic() < deadline:
            self.command_all_motors(pwm)
            batch_accepted, rejection, batch_status = (
                self.collect_motor_test_responses()
            )
            accepted += batch_accepted
            status_texts.extend(batch_status)
            if rejection is not None:
                detail = "; ".join(status_texts[-5:]) or "no STATUSTEXT"
                raise RuntimeError(
                    "all-motor test command rejected: "
                    f"MAV_RESULT={rejection}; detail={detail}"
                )
            time.sleep(CONTROL_PERIOD)
        if accepted < 6:
            raise RuntimeError(
                "all-motor test did not receive six accepted motor acknowledgements"
            )
        # Command all ESCs to bidirectional neutral before motor-test timeout.
        self.hold_all_motors_neutral(0.5)
        time.sleep(0.8)

    def run_vertical_test(self, seconds: float, vertical: int) -> None:
        print(
            f"Vertical test: {seconds:.1f}s, z={vertical}; "
            "this is thrust input, not a measured depth target"
        )
        deadline = time.monotonic() + seconds
        started_at = time.monotonic()
        active_sample_logged = False
        while time.monotonic() < deadline:
            self.send_control(vertical=vertical)
            if (
                not active_sample_logged
                and time.monotonic() - started_at >= 0.3
                and self.audit is not None
            ):
                self.audit.capture(
                    self.master,
                    "VERTICAL_OUTPUT_ACTIVE_SAMPLE",
                    {"vertical_command": vertical},
                    duration=0.15,
                )
                active_sample_logged = True
            time.sleep(CONTROL_PERIOD)
        self.neutral(1.0)

    def run_combined_test(self, seconds: float) -> None:
        """Drive forward and vertical axes together through the ArduSub mixer."""
        print(
            f"Combined test: {seconds:.1f}s, forward={self.args.forward}, "
            f"vertical={self.args.vertical}, yaw_trim={self.args.straight_yaw_trim}"
        )
        deadline = time.monotonic() + seconds
        started_at = time.monotonic()
        active_sample_logged = False
        while time.monotonic() < deadline:
            self.send_control(
                forward=self.args.forward,
                vertical=self.args.vertical,
                yaw=self.args.straight_yaw_trim,
            )
            if (
                not active_sample_logged
                and time.monotonic() - started_at >= 0.3
                and self.audit is not None
            ):
                self.audit.capture(
                    self.master,
                    "COMBINED_OUTPUT_ACTIVE_SAMPLE",
                    {
                        "forward_command": self.args.forward,
                        "vertical_command": self.args.vertical,
                        "yaw_trim": self.args.straight_yaw_trim,
                    },
                    duration=0.15,
                )
                active_sample_logged = True
            time.sleep(CONTROL_PERIOD)
        self.neutral(1.0)

    def run_turn_test(self, degrees: float) -> None:
        print(
            f"Turn-right test: yaw={self.args.turn_yaw}, "
            f"time={self.args.turn_seconds:.1f}s; intended={degrees:.1f}deg, "
            "actual angle must be measured externally"
        )
        self.turn_right("turn_right_test")

    def straight(self, seconds: float, name: str) -> None:
        print(
            f"{name}: {seconds:.1f}s open-loop forward; "
            f"yaw_trim={self.args.straight_yaw_trim}"
        )
        deadline = time.monotonic() + seconds
        started_at = time.monotonic()
        active_sample_logged = False
        while time.monotonic() < deadline:
            self.send_control(
                forward=self.args.forward,
                yaw=self.args.straight_yaw_trim,
            )
            if (
                not active_sample_logged
                and time.monotonic() - started_at >= 0.3
                and self.audit is not None
            ):
                self.audit.capture(
                    self.master,
                    "STRAIGHT_OUTPUT_ACTIVE_SAMPLE",
                    {
                        "forward_command": self.args.forward,
                        "yaw_trim": self.args.straight_yaw_trim,
                    },
                    duration=0.15,
                )
                active_sample_logged = True
            time.sleep(CONTROL_PERIOD)
        # Come fully to neutral before starting the following turn.
        self.neutral(1.0)

    def turn_right(self, name: str) -> None:
        print(
            f"{name}: open-loop yaw={self.args.turn_yaw} for "
            f"{self.args.turn_seconds:.1f}s"
        )
        deadline = time.monotonic() + self.args.turn_seconds
        while time.monotonic() < deadline:
            self.send_control(yaw=self.args.turn_yaw)
            time.sleep(CONTROL_PERIOD)
        self.neutral(1.0)

    def circle_right(self, name: str) -> None:
        print(
            f"{name}: open-loop circle; forward={self.args.circle_forward}, "
            f"yaw={self.args.circle_yaw}, time={self.args.circle_seconds:.1f}s"
        )
        deadline = time.monotonic() + self.args.circle_seconds
        while time.monotonic() < deadline:
            self.send_control(
                forward=self.args.circle_forward,
                yaw=self.args.circle_yaw,
            )
            time.sleep(CONTROL_PERIOD)
        self.neutral(1.0)
        print("Circle timer complete; diameter and closure must be checked externally")

    def run(self, plan: VideoMissionPlan) -> None:
        print("Mission control: MANUAL open-loop mixer, no compass feedback")
        for step in plan:
            if step.kind is MotionKind.WAIT:
                self.wait_neutral(step.minimum_seconds)
            elif step.kind is MotionKind.STRAIGHT:
                self.straight(step.minimum_seconds, step.name)
            elif step.kind is MotionKind.TURN_RIGHT:
                print(f"{step.name}: intended {step.degrees:.0f}deg (external check)")
                self.turn_right(step.name)
            elif step.kind is MotionKind.CIRCLE_RIGHT:
                self.circle_right(step.name)
            elif step.kind is MotionKind.STOP:
                self.neutral(1.0)


def main() -> int:
    args = parse_args()
    validate_controls(args)
    plan = VideoMissionPlan.competition_default()

    if not args.enable_output:
        if args.test != "mission":
            return dry_run_motion_test(args)
        return dry_run(plan)
    if not args.connection:
        raise SystemExit("--connection is required with --enable-output")
    if args.confirm != OUTPUT_CONFIRMATION:
        raise SystemExit(
            f"output remains locked; add --confirm {OUTPUT_CONFIRMATION} "
            "only in a safe test"
        )
    if (
        args.test in ("motor-all", "combined")
        and args.confirm_all_motors != ALL_MOTORS_CONFIRMATION
    ):
        raise SystemExit(
            "simultaneous motor output remains locked; add "
            f"--confirm-all-motors {ALL_MOTORS_CONFIRMATION} only when the "
            "vehicle is restrained and all propellers are clear"
        )
    if (
        args.test in ("vertical", "combined")
        and abs(args.vertical - NEUTRAL_VERTICAL) > 50
        and args.confirm_high_output != HIGH_OUTPUT_CONFIRMATION
    ):
        raise SystemExit(
            "high vertical output remains locked; add "
            f"--confirm-high-output {HIGH_OUTPUT_CONFIRMATION} only when the "
            "vehicle is restrained"
        )
    if (
        args.test in ("vertical", "combined")
        and args.duration > 5.0
        and args.confirm_long_vertical != LONG_OUTPUT_CONFIRMATION
    ):
        raise SystemExit(
            "long vertical output remains locked; add "
            f"--confirm-long-vertical {LONG_OUTPUT_CONFIRMATION} only when "
            "the vehicle is fully submerged, restrained, and emergency power "
            "cut is ready"
        )
    if (
        args.test in ("straight", "combined")
        and abs(args.forward) > 400
        and args.confirm_high_output != HIGH_OUTPUT_CONFIRMATION
    ):
        raise SystemExit(
            "high forward output remains locked; add "
            f"--confirm-high-output {HIGH_OUTPUT_CONFIRMATION} only when the "
            "vehicle is fully submerged and restrained"
        )
    if (
        args.test in ("straight", "combined")
        and abs(args.forward) > 400
        and args.duration > 5.0
        and args.confirm_long_forward != LONG_OUTPUT_CONFIRMATION
    ):
        raise SystemExit(
            "long high forward output remains locked; add "
            f"--confirm-long-forward {LONG_OUTPUT_CONFIRMATION} only when "
            "the vehicle is fully submerged, restrained, and emergency power "
            "cut is ready"
        )

    signal.signal(signal.SIGTERM, handle_stop_signal)

    audit = PixhawkAuditLog(args.audit_log, args.test, args.connection)
    audit.event(
        "SESSION_START",
        {
            "baud": args.baud,
            "duration": args.duration,
            "forward": args.forward,
            "motor_number": args.motor_number,
            "motor_pwm": args.motor_pwm,
            "vertical": args.vertical,
            "turn_yaw": args.turn_yaw,
            "turn_seconds": args.turn_seconds,
            "circle_forward": args.circle_forward,
            "circle_yaw": args.circle_yaw,
            "circle_seconds": args.circle_seconds,
            "yaw_sign": args.yaw_sign,
        },
    )
    master = open_connection(args.connection, args.baud)
    runner = ArduSubRunner(master, args, audit)
    heartbeat = master.wait_heartbeat(timeout=15)
    if heartbeat is None or heartbeat.type != mavutil.mavlink.MAV_TYPE_SUBMARINE:
        audit.event("CONNECTION_REJECTED", {"reason": "SUBMARINE heartbeat missing"})
        raise SystemExit("ArduSub SUBMARINE heartbeat was not received")
    if master.motors_armed():
        audit.capture(master, "START_REFUSED_ALREADY_ARMED")
        raise SystemExit("vehicle was already armed; refusing to start")
    runner.request_audit_streams()
    audit.capture(master, "CONNECTION_READY", duration=1.5)

    result = 0
    try:
        runner.set_manual()
        runner.neutral(1.0)
        if args.test != "mission":
            runner.disarmed_countdown(args.countdown, args.test)
        runner.set_output_safety(True)
        print(
            f"Pre-arm ESC neutral settle: {ESC_NEUTRAL_SETTLE_SECONDS:.1f}s "
            "(vehicle remains DISARMED)"
        )
        runner.neutral(ESC_NEUTRAL_SETTLE_SECONDS)
        runner.require_neutral_motor_outputs("PRE_ARM_NEUTRAL_CHECK")
        runner.arm()
        print(
            "Armed MANUAL neutral verification: "
            f"{ARMED_MANUAL_NEUTRAL_CHECK_SECONDS:.1f}s"
        )
        runner.neutral(ARMED_MANUAL_NEUTRAL_CHECK_SECONDS)
        runner.require_neutral_motor_outputs("ARMED_MANUAL_NEUTRAL_CHECK")
        runner.audit_event(
            "TEST_COMMAND_BEGIN",
            {
                "duration": args.duration,
                "motor_number": args.motor_number,
                "motor_pwm": args.motor_pwm,
                "vertical": args.vertical,
                "forward": args.forward,
            },
            capture=True,
        )
        if args.test == "motor":
            runner.run_motor_test(args.duration, args.motor_number, args.motor_pwm)
        elif args.test == "motor-all":
            runner.run_all_motor_test(args.duration, args.motor_pwm)
        elif args.test == "straight":
            runner.run_straight_test(args.duration)
        elif args.test == "vertical":
            runner.run_vertical_test(args.duration, args.vertical)
        elif args.test == "combined":
            runner.run_combined_test(args.duration)
        elif args.test == "turn-right":
            runner.run_turn_test(args.degrees)
        elif args.test == "circle":
            runner.circle_right("circle_test")
        else:
            runner.run(plan)
        runner.audit_event("TEST_COMMAND_END", capture=True)
    except KeyboardInterrupt:
        print("Interrupted; neutral and disarm", file=sys.stderr)
        audit.event("RUN_INTERRUPTED")
        result = 130
    except Exception as exc:
        print(f"MISSION ERROR: {exc}", file=sys.stderr)
        audit.event("RUN_ERROR", {"error_type": type(exc).__name__, "error": str(exc)})
        result = 1
    finally:
        try:
            runner.disarm()
        except Exception as exc:
            print(f"DISARM WARNING: {exc}", file=sys.stderr)
            audit.event(
                "DISARM_FAILED",
                {"error_type": type(exc).__name__, "error": str(exc)},
            )
        try:
            time.sleep(0.8)
            runner.set_output_safety(False)
        except Exception as exc:
            print(f"OUTPUT SAFETY LOCK WARNING: {exc}", file=sys.stderr)
            audit.event(
                "OUTPUT_SAFETY_LOCK_FAILED",
                {"error_type": type(exc).__name__, "error": str(exc)},
            )
            result = 1
        try:
            audit.capture(master, "SESSION_END", {"result": result})
        except Exception as exc:
            audit.event(
                "SESSION_END_TELEMETRY_FAILED",
                {"result": result, "error": str(exc)},
            )
    return result


if __name__ == "__main__":
    sys.exit(main())
