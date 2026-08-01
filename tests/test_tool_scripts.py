import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_all_tool_scripts_compile() -> None:
    tools = Path(__file__).resolve().parents[1] / "tools"
    for path in tools.rglob("*.py"):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")


def test_pool_aliases_expose_adjustable_power_and_duration() -> None:
    aliases = (
        Path(__file__).resolve().parents[1] / "tools" / "pool_aliases.sh"
    ).read_text(encoding="utf-8")
    for function in (
        "pool-motor()",
        "pool-forward()",
        "pool-vertical()",
        "pool-combined()",
        "pool-turn()",
        "pool-mission()",
        "pool-status()",
        "pool-stop()",
        "pool-audit()",
    ):
        assert function in aliases
    assert 'local motor="$1" pwm="$2" seconds="$3"' in aliases
    assert 'local forward="$1" seconds="$2"' in aliases
    assert 'local vertical="$1" seconds="$2"' in aliases
    assert 'local forward="$1" vertical="$2" seconds="$3"' in aliases
    assert 'local yaw="$1" seconds="$2"' in aliases
    assert "--test motor --motor-number" in aliases
    assert "--test mission" in aliases
    assert "--confirm-full-mission FULL_MISSION_TUNED" in aliases
    assert "Both physical M3 and M4 get the same mixer demand." in aliases
    assert "--confirm-long-forward LONG_FULL_OUTPUT_RESTRAINED" in aliases
    assert "--confirm-long-vertical LONG_FULL_OUTPUT_RESTRAINED" in aliases


def test_pool_service_rejects_invalid_motor_duration_early() -> None:
    service = load_pool_service()
    args = service.parser().parse_args(
        ["start", "--test", "motor", "--duration", "5", "--motor-pwm", "1525"]
    )
    with pytest.raises(SystemExit, match="between 1 and 3 seconds"):
        service.validate_start(args)
    args = service.parser().parse_args(
        ["start", "--test", "motor-all", "--duration", "6", "--motor-pwm", "1900"]
    )
    with pytest.raises(SystemExit, match="between 1 and 5 seconds"):
        service.validate_start(args)


def test_pool_service_forwards_full_mission_interlocks(tmp_path: Path) -> None:
    service = load_pool_service()
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "video_mission_runner.py").write_text("", encoding="utf-8")
    args = service.parser().parse_args(
        [
            "start",
            "--test",
            "mission",
            "--forward",
            "-500",
            "--dive-seconds",
            "3",
            "--dive-vertical",
            "1000",
            "--enable-output",
            "--confirm",
            "MOTORS_ARE_CLEAR",
            "--confirm-full-mission",
            "FULL_MISSION_TUNED",
            "--confirm-high-output",
            "HIGH_OUTPUT_RESTRAINED",
            "--confirm-long-forward",
            "LONG_FULL_OUTPUT_RESTRAINED",
        ]
    )
    command = service.runner_command(args, tmp_path)
    assert command[command.index("--test") + 1] == "mission"
    assert command[command.index("--forward") + 1] == "-500"
    assert command[command.index("--dive-seconds") + 1] == "3.0"
    assert command[command.index("--dive-vertical") + 1] == "1000"
    assert "--confirm-full-mission" in command
    assert command[command.index("--confirm-full-mission") + 1] == (
        "FULL_MISSION_TUNED"
    )
    assert "--confirm-high-output" in command
    assert "--confirm-long-forward" in command


def test_runner_requires_full_mission_confirmation() -> None:
    runner_module = load_video_runner()
    source = (
        Path(__file__).resolve().parents[1] / "tools" / "video_mission_runner.py"
    ).read_text(encoding="utf-8")
    assert "MISSION_CONFIRMATION = \"FULL_MISSION_TUNED\"" in source
    assert "confirm_full_mission" in source
    args = runner_module.parse_args(
        ["--test", "mission", "--enable-output", "--confirm", "MOTORS_ARE_CLEAR"]
    )
    # Direct main() path checks the mission interlock; keep a source contract too.
    assert "full mission remains locked" in source
    assert args.confirm_full_mission is None


def test_pool_alias_installer_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    path = Path(__file__).resolve().parents[1] / "tools" / "install_pool_aliases.py"
    spec = importlib.util.spec_from_file_location("install_pool_aliases_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.Path, "home", lambda: tmp_path)
    assert module.main() == 0
    assert module.main() == 0
    bashrc = (tmp_path / ".bashrc").read_text(encoding="utf-8")
    assert bashrc.count(module.SOURCE_LINE) == 1


def load_pool_service():
    path = Path(__file__).resolve().parents[1] / "tools" / "pool_test_service.py"
    spec = importlib.util.spec_from_file_location("pool_test_service_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_video_runner():
    path = Path(__file__).resolve().parents[1] / "tools" / "video_mission_runner.py"
    spec = importlib.util.spec_from_file_location("video_mission_runner_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pool_service_real_output_requires_confirmation() -> None:
    service = load_pool_service()
    args = service.parser().parse_args(
        ["start", "--test", "straight", "--enable-output", "--confirm", "WRONG"]
    )
    with pytest.raises(SystemExit, match="output remains locked"):
        service.validate_start(args)


def test_pool_service_full_mission_has_second_interlock() -> None:
    service = load_pool_service()
    args = service.parser().parse_args(
        [
            "start",
            "--test",
            "mission",
            "--enable-output",
            "--confirm",
            "MOTORS_ARE_CLEAR",
        ]
    )
    with pytest.raises(SystemExit, match="full mission remains locked"):
        service.validate_start(args)


def test_pool_service_all_motors_has_extra_interlock() -> None:
    service = load_pool_service()
    args = service.parser().parse_args(
        [
            "start",
            "--test",
            "motor-all",
            "--enable-output",
            "--confirm",
            "MOTORS_ARE_CLEAR",
        ]
    )
    with pytest.raises(SystemExit, match="simultaneous motor output remains locked"):
        service.validate_start(args)


def test_pool_service_high_vertical_has_extra_interlock() -> None:
    service = load_pool_service()
    args = service.parser().parse_args(
        [
            "start",
            "--test",
            "vertical",
            "--vertical",
            "600",
            "--duration",
            "1",
            "--enable-output",
            "--confirm",
            "MOTORS_ARE_CLEAR",
        ]
    )
    with pytest.raises(SystemExit, match="high vertical output remains locked"):
        service.validate_start(args)


def test_pool_service_long_vertical_has_extra_interlock() -> None:
    service = load_pool_service()
    args = service.parser().parse_args(
        [
            "start",
            "--test",
            "vertical",
            "--vertical",
            "1000",
            "--duration",
            "20",
            "--enable-output",
            "--confirm",
            "MOTORS_ARE_CLEAR",
            "--confirm-high-output",
            "HIGH_OUTPUT_RESTRAINED",
        ]
    )
    with pytest.raises(SystemExit, match="long vertical output remains locked"):
        service.validate_start(args)


def test_pool_service_long_high_forward_has_extra_interlocks() -> None:
    service = load_pool_service()
    args = service.parser().parse_args(
        [
            "start",
            "--test",
            "straight",
            "--forward",
            "1000",
            "--duration",
            "20",
            "--enable-output",
            "--confirm",
            "MOTORS_ARE_CLEAR",
        ]
    )
    with pytest.raises(SystemExit, match="high forward output remains locked"):
        service.validate_start(args)
    args.confirm_high_output = "HIGH_OUTPUT_RESTRAINED"
    with pytest.raises(SystemExit, match="long high forward output remains locked"):
        service.validate_start(args)


def test_pool_service_long_high_turn_has_extra_interlocks() -> None:
    service = load_pool_service()
    args = service.parser().parse_args(
        [
            "start",
            "--test",
            "turn-right",
            "--turn-yaw",
            "1000",
            "--turn-seconds",
            "60",
            "--enable-output",
            "--confirm",
            "MOTORS_ARE_CLEAR",
        ]
    )
    with pytest.raises(SystemExit, match="high turn output remains locked"):
        service.validate_start(args)
    args.confirm_high_output = "HIGH_OUTPUT_RESTRAINED"
    with pytest.raises(SystemExit, match="long high turn output remains locked"):
        service.validate_start(args)


def test_pool_service_uses_unbuffered_python(tmp_path: Path) -> None:
    service = load_pool_service()
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    args = service.parser().parse_args(["start", "--test", "straight"])
    command = service.runner_command(args, tmp_path)
    assert command[1] == "-u"
    assert "--enable-output" not in command
    audit_path = Path(command[command.index("--audit-log") + 1])
    assert audit_path.parts[-3:] == ("logs", "pool_tests", "pixhawk-audit.jsonl")


def test_pool_service_forwards_individual_motor_settings(tmp_path: Path) -> None:
    service = load_pool_service()
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    args = service.parser().parse_args(
        ["start", "--test", "motor", "--motor-number", "6", "--motor-pwm", "1300"]
    )
    command = service.runner_command(args, tmp_path)
    assert command[command.index("--motor-number") + 1] == "6"
    assert command[command.index("--motor-pwm") + 1] == "1300"


def test_pool_service_forwards_all_motor_interlock(tmp_path: Path) -> None:
    service = load_pool_service()
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    args = service.parser().parse_args(
        [
            "start",
            "--test",
            "motor-all",
            "--duration",
            "3",
            "--enable-output",
            "--confirm",
            "MOTORS_ARE_CLEAR",
            "--confirm-all-motors",
            "ALL_MOTORS_RESTRAINED",
        ]
    )
    service.validate_start(args)
    command = service.runner_command(args, tmp_path)
    assert command[command.index("--confirm-all-motors") + 1] == (
        "ALL_MOTORS_RESTRAINED"
    )


def test_pool_service_forwards_open_loop_calibration_settings(
    tmp_path: Path,
) -> None:
    service = load_pool_service()
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    args = service.parser().parse_args(
        [
            "start",
            "--test",
            "turn-right",
            "--turn-yaw",
            "70",
            "--turn-seconds",
            "1.4",
            "--circle-seconds",
            "9",
            "--straight-yaw-trim",
            "-8",
        ]
    )
    command = service.runner_command(args, tmp_path)
    assert command[command.index("--turn-yaw") + 1] == "70"
    assert command[command.index("--turn-seconds") + 1] == "1.4"
    assert command[command.index("--circle-seconds") + 1] == "9.0"
    assert command[command.index("--straight-yaw-trim") + 1] == "-8"


def test_pool_service_forwards_long_vertical_interlock(tmp_path: Path) -> None:
    service = load_pool_service()
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    args = service.parser().parse_args(
        [
            "start",
            "--test",
            "vertical",
            "--vertical",
            "1000",
            "--duration",
            "20",
            "--enable-output",
            "--confirm",
            "MOTORS_ARE_CLEAR",
            "--confirm-high-output",
            "HIGH_OUTPUT_RESTRAINED",
            "--confirm-long-vertical",
            "LONG_FULL_OUTPUT_RESTRAINED",
        ]
    )
    service.validate_start(args)
    command = service.runner_command(args, tmp_path)
    assert command[command.index("--confirm-long-vertical") + 1] == (
        "LONG_FULL_OUTPUT_RESTRAINED"
    )


def test_pool_service_forwards_long_high_forward_interlocks(tmp_path: Path) -> None:
    service = load_pool_service()
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    args = service.parser().parse_args(
        [
            "start",
            "--test",
            "straight",
            "--forward",
            "1000",
            "--duration",
            "20",
            "--enable-output",
            "--confirm",
            "MOTORS_ARE_CLEAR",
            "--confirm-high-output",
            "HIGH_OUTPUT_RESTRAINED",
            "--confirm-long-forward",
            "LONG_FULL_OUTPUT_RESTRAINED",
        ]
    )
    service.validate_start(args)
    command = service.runner_command(args, tmp_path)
    assert command[command.index("--confirm-high-output") + 1] == (
        "HIGH_OUTPUT_RESTRAINED"
    )
    assert command[command.index("--confirm-long-forward") + 1] == (
        "LONG_FULL_OUTPUT_RESTRAINED"
    )


def test_pool_service_combined_full_output_forwards_all_interlocks(
    tmp_path: Path,
) -> None:
    service = load_pool_service()
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    args = service.parser().parse_args(
        [
            "start",
            "--test",
            "combined",
            "--forward",
            "-1000",
            "--vertical",
            "1000",
            "--duration",
            "20",
            "--enable-output",
            "--confirm",
            "MOTORS_ARE_CLEAR",
            "--confirm-all-motors",
            "ALL_MOTORS_RESTRAINED",
            "--confirm-high-output",
            "HIGH_OUTPUT_RESTRAINED",
            "--confirm-long-forward",
            "LONG_FULL_OUTPUT_RESTRAINED",
            "--confirm-long-vertical",
            "LONG_FULL_OUTPUT_RESTRAINED",
        ]
    )
    service.validate_start(args)
    command = service.runner_command(args, tmp_path)
    assert command[command.index("--test") + 1] == "combined"
    assert command[command.index("--forward") + 1] == "-1000"
    assert command[command.index("--vertical") + 1] == "1000"
    assert command[command.index("--confirm-all-motors") + 1] == (
        "ALL_MOTORS_RESTRAINED"
    )
    assert "--confirm-high-output" in command
    assert "--confirm-long-forward" in command
    assert "--confirm-long-vertical" in command


def test_pool_service_forwards_long_high_turn_interlocks(tmp_path: Path) -> None:
    service = load_pool_service()
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    args = service.parser().parse_args(
        [
            "start",
            "--test",
            "turn-right",
            "--turn-yaw",
            "-1000",
            "--turn-seconds",
            "60",
            "--enable-output",
            "--confirm",
            "MOTORS_ARE_CLEAR",
            "--confirm-high-output",
            "HIGH_OUTPUT_RESTRAINED",
            "--confirm-long-turn",
            "LONG_FULL_OUTPUT_RESTRAINED",
        ]
    )
    service.validate_start(args)
    command = service.runner_command(args, tmp_path)
    assert command[command.index("--turn-yaw") + 1] == "-1000"
    assert command[command.index("--turn-seconds") + 1] == "60.0"
    assert "--confirm-high-output" in command
    assert "--confirm-long-turn" in command


def test_runner_allows_sixty_second_straight_test() -> None:
    runner_module = load_video_runner()
    args = runner_module.parse_args([])
    args.test = "straight"
    args.duration = 60.0
    runner_module.validate_controls(args)


def test_runner_allows_full_forward_range_for_sixty_seconds() -> None:
    runner_module = load_video_runner()
    for forward in (-1000, 1000):
        args = runner_module.parse_args(
            ["--test", "straight", "--duration", "60", "--forward", str(forward)]
        )
        runner_module.validate_controls(args)


def test_runner_allows_combined_full_output_for_sixty_seconds() -> None:
    runner_module = load_video_runner()
    args = runner_module.parse_args(
        [
            "--test",
            "combined",
            "--duration",
            "60",
            "--forward",
            "-1000",
            "--vertical",
            "1000",
        ]
    )
    runner_module.validate_controls(args)


@pytest.mark.parametrize("forward", [-1001, 0, 1001])
def test_runner_rejects_forward_outside_protocol_range(forward: int) -> None:
    runner_module = load_video_runner()
    args = runner_module.parse_args(["--test", "straight", "--forward", str(forward)])
    with pytest.raises(ValueError, match="forward magnitude"):
        runner_module.validate_controls(args)


def test_runner_allows_three_second_individual_motor_test() -> None:
    runner_module = load_video_runner()
    args = runner_module.parse_args(
        [
            "--test",
            "motor",
            "--duration",
            "3",
        ]
    )
    runner_module.validate_controls(args)


def test_runner_allows_three_second_simultaneous_motor_test() -> None:
    runner_module = load_video_runner()
    args = runner_module.parse_args(
        ["--test", "motor-all", "--duration", "3", "--motor-pwm", "1525"]
    )
    runner_module.validate_controls(args)


def test_runner_allows_guarded_one_second_vertical_600() -> None:
    runner_module = load_video_runner()
    args = runner_module.parse_args(
        ["--test", "vertical", "--duration", "1", "--vertical", "600"]
    )
    runner_module.validate_controls(args)


def test_runner_allows_full_range_sixty_second_vertical() -> None:
    runner_module = load_video_runner()
    for vertical in (0, 1000):
        args = runner_module.parse_args(
            ["--test", "vertical", "--duration", "60", "--vertical", str(vertical)]
        )
        runner_module.validate_controls(args)


def test_runner_rejects_vertical_beyond_protocol_range_or_sixty_seconds() -> None:
    runner_module = load_video_runner()
    args = runner_module.parse_args(
        ["--test", "vertical", "--duration", "60.1", "--vertical", "600"]
    )
    with pytest.raises(ValueError, match="between 1 and 60 seconds"):
        runner_module.validate_controls(args)
    for vertical in (-1, 1001):
        args = runner_module.parse_args(
            ["--test", "vertical", "--duration", "1", "--vertical", str(vertical)]
        )
        with pytest.raises(ValueError, match="between 0 and 1000"):
            runner_module.validate_controls(args)


def test_runner_rejects_excessive_open_loop_times() -> None:
    runner_module = load_video_runner()
    args = runner_module.parse_args(["--turn-seconds", "60.1"])
    with pytest.raises(ValueError, match="turn-seconds"):
        runner_module.validate_controls(args)

    args = runner_module.parse_args(["--circle-seconds", "60.1"])
    with pytest.raises(ValueError, match="circle-seconds"):
        runner_module.validate_controls(args)


def test_runner_allows_full_turn_range_for_sixty_seconds() -> None:
    runner_module = load_video_runner()
    for yaw in (-1000, 1000):
        args = runner_module.parse_args(
            [
                "--test",
                "turn-right",
                "--turn-yaw",
                str(yaw),
                "--turn-seconds",
                "60",
            ]
        )
        runner_module.validate_controls(args)


@pytest.mark.parametrize("yaw", [-1001, 0, 1001])
def test_runner_rejects_turn_outside_protocol_range(yaw: int) -> None:
    runner_module = load_video_runner()
    args = runner_module.parse_args(["--test", "turn-right", "--turn-yaw", str(yaw)])
    with pytest.raises(ValueError, match="turn-yaw magnitude"):
        runner_module.validate_controls(args)


def test_runner_has_no_compass_heading_feedback() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "tools" / "video_mission_runner.py"
    ).read_text(encoding="utf-8")
    assert "ATTITUDE" not in source
    assert "yaw_degrees" not in source
    assert "yaw_hold_command" not in source
    assert "STABILIZE" not in source
    assert 'runner.set_manual()' in source
    assert 'runner.set_acro()' not in source
    assert "ESC_NEUTRAL_SETTLE_SECONDS = 5.0" in source
    assert "runner.require_neutral_motor_outputs" in source
    assert "runner.set_manual()" in source
    assert "GCS_SOURCE_SYSTEM = 255" in source
    assert "source_system=GCS_SOURCE_SYSTEM" in source
    assert "source_system=254" not in source


@pytest.mark.parametrize("pwm", [1100, 1300, 1499, 1501, 1700, 1900])
def test_runner_allows_full_configured_motor_pwm_range(pwm: int) -> None:
    runner_module = load_video_runner()
    args = runner_module.parse_args([])
    args.test = "motor"
    args.duration = 1.0
    args.motor_pwm = pwm
    runner_module.validate_controls(args)


@pytest.mark.parametrize("pwm", [1099, 1500, 1901])
def test_runner_rejects_motor_pwm_outside_configured_range_or_neutral(pwm: int) -> None:
    runner_module = load_video_runner()
    args = runner_module.parse_args([])
    args.test = "motor"
    args.duration = 1.0
    args.motor_pwm = pwm
    with pytest.raises(ValueError, match="motor-pwm"):
        runner_module.validate_controls(args)


class FakeCommandMav:
    def __init__(self) -> None:
        self.calls = []
        self.manual_calls = []

    def command_long_send(self, *args) -> None:
        self.calls.append(args)

    def manual_control_send(self, *args) -> None:
        self.manual_calls.append(args)


class FakeTelemetryMessage:
    def __init__(self, message_type: str, **values) -> None:
        self.message_type = message_type
        self.values = values

    def get_type(self) -> str:
        return self.message_type

    def to_dict(self) -> dict:
        return {"mavpackettype": self.message_type, **self.values}


class FakeTelemetryMaster:
    def __init__(self) -> None:
        self.messages = {
            "HEARTBEAT": FakeTelemetryMessage("HEARTBEAT", base_mode=128),
            "SERVO_OUTPUT_RAW": FakeTelemetryMessage(
                "SERVO_OUTPUT_RAW", servo1_raw=1525
            ),
        }

    def recv_match(self, **_kwargs):
        return None


def test_pixhawk_audit_appends_events_and_all_cached_telemetry(tmp_path: Path) -> None:
    runner_module = load_video_runner()
    audit_path = tmp_path / "pixhawk-audit.jsonl"
    audit = runner_module.PixhawkAuditLog(audit_path, "motor", "/dev/test")
    audit.capture(FakeTelemetryMaster(), "ARM_CONFIRMED", duration=0)
    record = __import__("json").loads(audit_path.read_text(encoding="utf-8"))
    assert record["event"] == "ARM_CONFIRMED"
    assert record["data"]["armed_from_heartbeat"] is True
    assert set(record["telemetry"]) == {"HEARTBEAT", "SERVO_OUTPUT_RAW"}


def test_motor_output_neutral_check_rejects_non_neutral_channel(tmp_path: Path) -> None:
    runner_module = load_video_runner()
    audit = runner_module.PixhawkAuditLog(
        tmp_path / "audit.jsonl", "motor", "/dev/test"
    )
    master = FakeTelemetryMaster()
    master.messages["SERVO_OUTPUT_RAW"] = FakeTelemetryMessage(
        "SERVO_OUTPUT_RAW",
        servo1_raw=1500,
        servo2_raw=1500,
        servo3_raw=1500,
        servo4_raw=1500,
        servo5_raw=1900,
        servo6_raw=1100,
    )
    runner = runner_module.ArduSubRunner(
        master, SimpleNamespace(yaw_sign=1), audit
    )
    with pytest.raises(RuntimeError, match="not neutral"):
        runner.require_neutral_motor_outputs("TEST_NEUTRAL")


def test_runner_translates_human_motor_number_to_ardusub_output_index() -> None:
    runner_module = load_video_runner()
    runner_module.mavutil = SimpleNamespace(
        mavlink=SimpleNamespace(MAV_CMD_DO_MOTOR_TEST=209)
    )
    mav = FakeCommandMav()
    master = SimpleNamespace(target_system=1, target_component=1, mav=mav)
    runner = runner_module.ArduSubRunner(master, SimpleNamespace(yaw_sign=1))
    runner.send_gcs_heartbeat = lambda: None
    runner.send_motor_test_pwm(6, 1525)
    assert len(mav.calls) == 1
    packet = mav.calls[0]
    assert packet[4] == 5.0  # user-facing M6 -> ArduSub's zero-based channel 5
    assert packet[5] == runner_module.MOTOR_TEST_THROTTLE_PWM
    assert packet[6] == 1525.0
    assert packet[9] == runner_module.MOTOR_TEST_ORDER_BOARD == 2
    assert mav.manual_calls[0][1:5] == (0, 0, 500, 0)


def test_runner_all_motor_batch_targets_each_output_once() -> None:
    runner_module = load_video_runner()
    runner_module.mavutil = SimpleNamespace(
        mavlink=SimpleNamespace(MAV_CMD_DO_MOTOR_TEST=209)
    )
    mav = FakeCommandMav()
    master = SimpleNamespace(target_system=1, target_component=1, mav=mav)
    runner = runner_module.ArduSubRunner(master, SimpleNamespace(yaw_sign=1))
    runner.send_gcs_heartbeat = lambda: None
    runner.command_all_motors(1525)
    assert len(mav.manual_calls) == 1
    assert len(mav.calls) == 6
    assert [packet[4] for packet in mav.calls] == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    assert all(packet[6] == 1525.0 for packet in mav.calls)


class FakeArmMaster:
    def __init__(self) -> None:
        self.arm_requested = False
        self.disarm_requested = False
        self.next_armed = False

    def arducopter_arm(self) -> None:
        self.arm_requested = True
        self.next_armed = True

    def arducopter_disarm(self) -> None:
        self.disarm_requested = True
        self.next_armed = False

    def recv_match(self, **_kwargs):
        return SimpleNamespace(base_mode=128 if self.next_armed else 0)

    def motors_armed(self) -> bool:
        return self.next_armed


def test_runner_arm_does_not_use_version_specific_wait_api() -> None:
    runner_module = load_video_runner()
    master = FakeArmMaster()
    runner = runner_module.ArduSubRunner(master, SimpleNamespace(yaw_sign=1))
    runner.send_gcs_heartbeat = lambda: None
    runner.arm()
    assert master.arm_requested


def test_runner_disarm_does_not_use_version_specific_wait_api() -> None:
    runner_module = load_video_runner()
    master = FakeArmMaster()
    master.next_armed = True
    runner = runner_module.ArduSubRunner(master, SimpleNamespace(yaw_sign=1))
    runner.neutral = lambda _seconds=1.0: None
    runner.send_gcs_heartbeat = lambda: None
    runner.disarm()
    assert master.disarm_requested
