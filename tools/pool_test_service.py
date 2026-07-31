#!/usr/bin/env python3
"""Start, inspect, or stop a pool test as a detached systemd user service.

The detached service survives SSH and Wi-Fi loss.  Real actuator output remains
behind the same explicit interlocks as video_mission_runner.py.  This launcher
never enables itself at boot and never restarts a completed or failed test.
"""

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

OUTPUT_CONFIRMATION = "MOTORS_ARE_CLEAR"
MISSION_CONFIRMATION = "FULL_MISSION_TUNED"
TEST_CHOICES = (
    "motor",
    "straight",
    "vertical",
    "turn-right",
    "circle",
    "mission",
)


def project_paths() -> tuple[Path, Path, Path, Path]:
    root = Path(__file__).resolve().parents[1]
    runtime = root / ".runtime"
    logs = root / "logs" / "pool_tests"
    state = runtime / "last_pool_test.json"
    return root, runtime, logs, state


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(description=__doc__)
    commands = top.add_subparsers(dest="action", required=True)

    start = commands.add_parser("start", help="Start one detached test")
    start.add_argument("--test", choices=TEST_CHOICES, required=True)
    start.add_argument("--duration", type=float, default=2.0)
    start.add_argument("--forward", type=int, default=100)
    start.add_argument("--motor-number", type=int, choices=range(1, 7), default=1)
    start.add_argument("--motor-pwm", type=int, default=1525)
    start.add_argument("--vertical", type=int, default=550)
    start.add_argument("--degrees", type=float, default=30.0)
    start.add_argument("--circle-forward", type=int, default=100)
    start.add_argument("--circle-yaw", type=int, default=80)
    start.add_argument("--turn-yaw-max", type=int, default=220)
    start.add_argument("--yaw-sign", type=int, choices=(-1, 1), default=1)
    start.add_argument("--countdown", type=int, default=15)
    start.add_argument(
        "--dry-hold",
        type=int,
        default=0,
        help="No-output service hold for Wi-Fi/SSH survival verification (0-60s)",
    )
    start.add_argument(
        "--connection",
        default=(
            "/dev/serial/by-id/"
            "usb-ArduPilot_Pixhawk1_280033001951333530393639-if00"
        ),
    )
    start.add_argument("--baud", type=int, default=115200)
    start.add_argument("--enable-output", action="store_true")
    start.add_argument("--confirm")
    start.add_argument(
        "--confirm-full-mission",
        help=f"Required for a real full mission: {MISSION_CONFIRMATION}",
    )

    commands.add_parser("status", help="Show the last unit and its saved log")
    commands.add_parser("stop", help="Stop the last unit through SIGTERM cleanup")
    return top


def validate_start(args: argparse.Namespace) -> None:
    if args.enable_output and args.confirm != OUTPUT_CONFIRMATION:
        raise SystemExit(
            f"output remains locked; add --confirm {OUTPUT_CONFIRMATION} "
            "only when the vehicle is safe"
        )
    if (
        args.enable_output
        and args.test == "mission"
        and args.confirm_full_mission != MISSION_CONFIRMATION
    ):
        raise SystemExit(
            "full mission remains locked; add "
            f"--confirm-full-mission {MISSION_CONFIRMATION} only after tuning"
        )


def runner_command(args: argparse.Namespace, root: Path) -> list[str]:
    python = root / ".venv" / "bin" / "python"
    runner = root / "tools" / "video_mission_runner.py"
    if not python.exists():
        raise SystemExit(f"virtual-environment Python not found: {python}")
    command = [
        str(python),
        "-u",
        str(runner),
        "--test",
        args.test,
        "--connection",
        args.connection,
        "--baud",
        str(args.baud),
        "--duration",
        str(args.duration),
        "--forward",
        str(args.forward),
        "--motor-number",
        str(args.motor_number),
        "--motor-pwm",
        str(args.motor_pwm),
        "--vertical",
        str(args.vertical),
        "--degrees",
        str(args.degrees),
        "--circle-forward",
        str(args.circle_forward),
        "--circle-yaw",
        str(args.circle_yaw),
        "--turn-yaw-max",
        str(args.turn_yaw_max),
        "--yaw-sign",
        str(args.yaw_sign),
        "--countdown",
        str(args.countdown),
        "--dry-run-hold",
        str(args.dry_hold),
    ]
    if args.enable_output:
        command.extend(["--enable-output", "--confirm", OUTPUT_CONFIRMATION])
    return command


def read_state(state_path: Path) -> dict:
    if not state_path.exists():
        raise SystemExit("No pool test has been started yet")
    return json.loads(state_path.read_text(encoding="utf-8"))


def show_log(log_path: Path, line_limit: int = 120) -> None:
    print(f"Log: {log_path}")
    if not log_path.exists():
        print("Log has not been created yet")
        return
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    print("\n".join(lines[-line_limit:]))


def start_test(args: argparse.Namespace) -> int:
    validate_start(args)
    systemd_run = shutil.which("systemd-run")
    if systemd_run is None:
        raise SystemExit("systemd-run was not found")

    root, runtime, logs, state_path = project_paths()
    runtime.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    unit = f"isas-pool-{args.test.replace('-', '_')}-{stamp}"
    log_path = logs / f"{unit}.log"
    command = runner_command(args, root)
    systemd_command = [
        systemd_run,
        "--user",
        f"--unit={unit}",
        "--collect",
        "--property=Type=exec",
        "--property=Restart=no",
        "--property=TimeoutStopSec=15",
        f"--property=WorkingDirectory={root}",
        f"--property=StandardOutput=append:{log_path}",
        f"--property=StandardError=append:{log_path}",
        *command,
    ]
    result = subprocess.run(
        systemd_command,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or result.stdout.strip())

    state = {
        "unit": unit,
        "log": str(log_path),
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "test": args.test,
        "real_output": bool(args.enable_output),
        "runner_command": command,
    }
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(result.stdout.strip())
    print(f"Unit: {unit}")
    print(f"Log: {log_path}")
    print("Wi-Fi/SSH may disconnect; the unit will continue locally.")
    print("Status: python tools/pool_test_service.py status")
    print("Stop:   python tools/pool_test_service.py stop")
    return 0


def status_test() -> int:
    _, _, _, state_path = project_paths()
    state = read_state(state_path)
    unit = state["unit"]
    print(
        f"Unit: {unit}\nTest: {state['test']}\n"
        f"Real output: {state['real_output']}\nStarted: {state['started_at']}"
    )
    subprocess.run(
        [
            "systemctl",
            "--user",
            "show",
            unit,
            "--property=ActiveState,SubState,Result,ExecMainStatus",
        ],
        check=False,
    )
    show_log(Path(state["log"]))
    return 0


def stop_test() -> int:
    _, _, _, state_path = project_paths()
    state = read_state(state_path)
    unit = state["unit"]
    print(f"Stopping {unit}; runner will neutral and DISARM")
    subprocess.run(["systemctl", "--user", "stop", unit], check=False)
    show_log(Path(state["log"]))
    return 0


def main() -> int:
    args = parser().parse_args()
    if args.action == "start":
        return start_test(args)
    if args.action == "status":
        return status_test()
    if args.action == "stop":
        return stop_test()
    raise SystemExit(f"unsupported action: {args.action}")


if __name__ == "__main__":
    sys.exit(main())
