#!/usr/bin/env python3
"""Guarded ArduSub runner for the 2026 advanced-category video route.

The default invocation is a hardware-free dry run. Real output requires both an
explicit connection and the --enable-output interlock. The open-loop circle size
and straight-leg distances must be calibrated in a pool before a recording run.
"""

import argparse
import math
import os
import re
import signal
import sys
import time

from isas.control.video_mission import MotionKind, VideoMissionPlan
from isas.control.yaw_control import (
    right_turn_target,
    wrap_degrees,
    yaw_hold_command,
)

try:
    from pymavlink import mavutil
except ImportError:  # pragma: no cover - dry-run works without pymavlink
    mavutil = None


CONTROL_PERIOD = 0.1
NEUTRAL_VERTICAL = 500
OUTPUT_CONFIRMATION = "MOTORS_ARE_CLEAR"
CIRCLE_TIMEOUT_SECONDS = 75.0
MAV_MODE_FLAG_SAFETY_ARMED = 128
MOTOR_TEST_THROTTLE_PWM = 1
MOTOR_TEST_ORDER_BOARD = 0
MOTOR_NEUTRAL_PWM = 1500


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
    parser.add_argument("--forward", type=int, default=200)
    parser.add_argument("--circle-forward", type=int, default=150)
    parser.add_argument("--circle-yaw", type=int, default=150)
    parser.add_argument("--turn-yaw-max", type=int, default=220)
    parser.add_argument(
        "--test",
        choices=(
            "mission",
            "motor",
            "straight",
            "vertical",
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
        help="Vertical-test MANUAL_CONTROL z value (450-550; 500 is neutral)",
    )
    parser.add_argument(
        "--degrees",
        type=float,
        default=30.0,
        help="Turn-right test angle in degrees (5-90)",
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
    return parser.parse_args(argv)


def validate_controls(args) -> None:
    for name in ("forward", "circle_forward", "circle_yaw", "turn_yaw_max"):
        value = abs(getattr(args, name))
        if not 1 <= value <= 400:
            raise ValueError(f"--{name.replace('_', '-')} must be between 1 and 400")
    if not 1.0 <= args.duration <= 25.0:
        raise ValueError("--duration must be between 1 and 25 seconds")
    if args.test == "vertical" and args.duration > 5.0:
        raise ValueError("vertical-test --duration must be between 1 and 5 seconds")
    if args.test == "motor" and args.duration > 3.0:
        raise ValueError("motor-test --duration must be between 1 and 3 seconds")
    if not 1475 <= args.motor_pwm <= 1525 or args.motor_pwm == MOTOR_NEUTRAL_PWM:
        raise ValueError("--motor-pwm must be 1475-1525 and must not be neutral 1500")
    if not 5 <= args.countdown <= 60:
        raise ValueError("--countdown must be between 5 and 60 seconds")
    if not 0 <= args.dry_run_hold <= 60:
        raise ValueError("--dry-run-hold must be between 0 and 60 seconds")
    if not 450 <= args.vertical <= 550:
        raise ValueError("--vertical must be between 450 and 550")
    if args.test == "vertical" and args.vertical == NEUTRAL_VERTICAL:
        raise ValueError("--vertical must not be 500 for a vertical test")
    if not 5.0 <= args.degrees <= 90.0:
        raise ValueError("--degrees must be between 5 and 90")


def dry_run(plan: VideoMissionPlan) -> int:
    print("VIDEO MISSION RUNNER - DRY RUN - HARDWARE OUTPUT DISABLED")
    heading = 0.0
    for index, step in enumerate(plan, start=1):
        if step.kind is MotionKind.TURN_RIGHT:
            heading = right_turn_target(heading, step.degrees)
        elif step.kind is MotionKind.CIRCLE_RIGHT:
            heading = right_turn_target(heading, step.degrees)
        print(
            f"[{index:02d}/{len(plan.steps):02d}] {step.name:24} "
            f"kind={step.kind.value:12} duration={step.minimum_seconds:4.1f}s "
            f"turn={step.degrees:5.0f}deg distance={step.target_distance_m:3.1f}m "
            f"diameter={step.diameter_m:3.1f}m heading={heading:5.0f}deg"
        )
    print("RESULT: PLAN_VALID, NO CONNECTION, NO ARM, NO MOTOR OUTPUT")
    return 0


def dry_run_motion_test(args) -> int:
    print(f"{args.test.upper()} TEST - DRY RUN - HARDWARE OUTPUT DISABLED")
    print(f"Would wait {args.countdown}s while DISARMED")
    if args.test == "straight":
        action = f"forward={args.forward} for {args.duration:.1f}s"
    elif args.test == "motor":
        action = (
            f"motor M{args.motor_number} at PWM={args.motor_pwm} "
            f"for {args.duration:.1f}s"
        )
    elif args.test == "vertical":
        action = f"vertical z={args.vertical} for {args.duration:.1f}s"
    elif args.test == "turn-right":
        action = f"right {args.degrees:.1f}deg with yaw_sign={args.yaw_sign:+d}"
    elif args.test == "circle":
        action = (
            f"one right circle with forward={args.circle_forward}, "
            f"yaw={args.circle_yaw}, yaw_sign={args.yaw_sign:+d}"
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


def open_connection(connection: str, baud: int):
    if mavutil is None:
        raise RuntimeError("pymavlink is required for a real connection")
    if os.name == "nt" and re.fullmatch(r"COM\d+", connection, re.IGNORECASE):
        return mavutil.mavserial(connection, baud=baud, source_system=254)
    return mavutil.mavlink_connection(connection, baud=baud, source_system=254)


class ArduSubRunner:
    def __init__(self, master, args):
        self.master = master
        self.args = args
        self.last_heartbeat = 0.0

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

    def request_streams(self) -> None:
        self.master.mav.request_data_stream_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_DATA_STREAM_ALL,
            10,
            1,
        )

    def yaw_degrees(self, timeout: float = 2.0) -> float:
        message = self.master.recv_match(
            type="ATTITUDE", blocking=True, timeout=timeout
        )
        if message is None:
            raise RuntimeError("ATTITUDE timeout; neutral/disarm required")
        while True:
            queued = self.master.recv_match(type="ATTITUDE", blocking=False)
            if queued is None:
                break
            message = queued
        return math.degrees(message.yaw) % 360.0

    def set_stabilize(self) -> None:
        mode_id = (self.master.mode_mapping() or {}).get("STABILIZE")
        if mode_id is None:
            raise RuntimeError("STABILIZE mode was not reported by ArduSub")
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
        raise RuntimeError("STABILIZE mode change was not confirmed")

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
        self.master.arducopter_arm()
        self.wait_armed_state(True, timeout=10)
        if not self.master.motors_armed():
            raise RuntimeError("ARM was not confirmed")

    def disarm(self) -> None:
        self.neutral(0.8)
        self.master.arducopter_disarm()
        self.wait_armed_state(False, timeout=8)

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
        target_yaw = self.yaw_degrees()
        print(f"Straight test: {seconds:.1f}s, forward={self.args.forward}")
        self.straight(seconds, target_yaw, "straight_test")

    def send_motor_test_pwm(self, motor_number: int, pwm: int) -> None:
        """Send ArduSub's board-order motor test using direct bidirectional PWM."""
        # A neutral MANUAL_CONTROL packet also refreshes the configured pilot
        # input failsafe during a multi-motor sequence. Motor-test mode owns the
        # actual outputs, so this neutral packet cannot mix additional thrust.
        self.send_control()
        # ArduSub 4.7 passes param1 directly to AP_MotorsMatrix::output_test_num,
        # whose output-channel index is zero based despite the MAVLink-facing
        # comment saying 1..N. Keep the CLI human-friendly and translate here.
        output_channel = motor_number - 1
        self.master.mav.command_int_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_FRAME_GLOBAL,
            mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST,
            0,
            0,
            float(output_channel),
            float(MOTOR_TEST_THROTTLE_PWM),
            float(pwm),
            0.0,
            0,
            MOTOR_TEST_ORDER_BOARD,
            0.0,
        )

    def run_motor_test_phase(self, seconds: float, motor_number: int, pwm: int) -> None:
        """Drive one output while keeping ArduSub's motor-test watchdog alive."""
        deadline = time.monotonic() + seconds
        accepted = False
        while time.monotonic() < deadline:
            self.send_motor_test_pwm(motor_number, pwm)
            while True:
                ack = self.master.recv_match(type="COMMAND_ACK", blocking=False)
                if ack is None:
                    break
                if ack.command != mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST:
                    continue
                if ack.result != mavutil.mavlink.MAV_RESULT_ACCEPTED:
                    raise RuntimeError(
                        f"motor-test command rejected: MAV_RESULT={ack.result}"
                    )
                accepted = True
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

    def run_vertical_test(self, seconds: float, vertical: int) -> None:
        print(
            f"Vertical test: {seconds:.1f}s, z={vertical}; "
            "this is thrust input, not a measured depth target"
        )
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.send_control(vertical=vertical)
            time.sleep(CONTROL_PERIOD)
        self.neutral(1.0)

    def run_turn_test(self, degrees: float) -> None:
        initial_yaw = self.yaw_degrees()
        target_yaw = right_turn_target(initial_yaw, degrees)
        print(
            f"Turn-right test: initial={initial_yaw:.1f}deg, "
            f"target={target_yaw:.1f}deg"
        )
        self.turn_right(target_yaw, "turn_right_test")

    def straight(self, seconds: float, target_yaw: float, name: str) -> None:
        print(f"{name}: {seconds:.1f}s forward, heading={target_yaw:.1f}")
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            current = self.yaw_degrees()
            yaw = yaw_hold_command(current, target_yaw, maximum=140)
            self.send_control(forward=self.args.forward, yaw=yaw)
            time.sleep(CONTROL_PERIOD)
        # Come fully to neutral before starting the following turn.
        self.neutral(1.0)

    def turn_right(self, target_yaw: float, name: str) -> None:
        print(f"{name}: turn to heading={target_yaw:.1f}")
        deadline = time.monotonic() + 20.0
        stable_since = None
        while time.monotonic() < deadline:
            current = self.yaw_degrees()
            error = wrap_degrees(target_yaw - current)
            if abs(error) <= 3.0:
                if stable_since is None:
                    stable_since = time.monotonic()
                if time.monotonic() - stable_since >= 0.8:
                    self.neutral(0.5)
                    return
            else:
                stable_since = None
            yaw = yaw_hold_command(
                current,
                target_yaw,
                proportional_gain=5.0,
                maximum=self.args.turn_yaw_max,
            )
            self.send_control(yaw=yaw)
            time.sleep(CONTROL_PERIOD)
        raise RuntimeError(f"{name}: target heading timeout")

    def circle_right(self, name: str) -> None:
        print(
            f"{name}: open-loop circle; forward={self.args.circle_forward}, "
            f"yaw={self.args.circle_yaw}"
        )
        last_yaw = self.yaw_degrees()
        accumulated = 0.0
        deadline = time.monotonic() + CIRCLE_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            current = self.yaw_degrees()
            delta = wrap_degrees(current - last_yaw)
            # ArduPilot yaw headings increase clockwise. yaw_sign only adapts the
            # outgoing command and must not invert the measured heading delta.
            accumulated += max(0.0, delta)
            last_yaw = current
            if accumulated >= 360.0:
                self.neutral(0.8)
                print(f"Circle complete: accumulated={accumulated:.1f}deg")
                return
            self.send_control(
                forward=self.args.circle_forward,
                yaw=self.args.circle_yaw,
            )
            time.sleep(CONTROL_PERIOD)
        raise RuntimeError(f"{name}: circle timeout at {accumulated:.1f}deg")

    def run(self, plan: VideoMissionPlan) -> None:
        self.request_streams()
        initial_yaw = self.yaw_degrees()
        target_yaw = initial_yaw
        print(f"Initial heading: {initial_yaw:.1f}deg")
        for step in plan:
            if step.kind is MotionKind.WAIT:
                self.wait_neutral(step.minimum_seconds)
            elif step.kind is MotionKind.STRAIGHT:
                self.straight(step.minimum_seconds, target_yaw, step.name)
            elif step.kind is MotionKind.TURN_RIGHT:
                target_yaw = right_turn_target(target_yaw, step.degrees)
                self.turn_right(target_yaw, step.name)
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

    signal.signal(signal.SIGTERM, handle_stop_signal)

    master = open_connection(args.connection, args.baud)
    runner = ArduSubRunner(master, args)
    heartbeat = master.wait_heartbeat(timeout=15)
    if heartbeat is None or heartbeat.type != mavutil.mavlink.MAV_TYPE_SUBMARINE:
        raise SystemExit("ArduSub SUBMARINE heartbeat was not received")
    if master.motors_armed():
        raise SystemExit("vehicle was already armed; refusing to start")

    result = 0
    try:
        runner.set_stabilize()
        runner.neutral(1.0)
        if args.test != "mission":
            runner.disarmed_countdown(args.countdown, args.test)
        runner.arm()
        if args.test == "motor":
            runner.run_motor_test(args.duration, args.motor_number, args.motor_pwm)
        elif args.test == "straight":
            runner.run_straight_test(args.duration)
        elif args.test == "vertical":
            runner.run_vertical_test(args.duration, args.vertical)
        elif args.test == "turn-right":
            runner.run_turn_test(args.degrees)
        elif args.test == "circle":
            runner.circle_right("circle_test")
        else:
            runner.run(plan)
    except KeyboardInterrupt:
        print("Interrupted; neutral and disarm", file=sys.stderr)
        result = 130
    except Exception as exc:
        print(f"MISSION ERROR: {exc}", file=sys.stderr)
        result = 1
    finally:
        try:
            runner.disarm()
        except Exception as exc:
            print(f"DISARM WARNING: {exc}", file=sys.stderr)
            result = 1
    return result


if __name__ == "__main__":
    sys.exit(main())
