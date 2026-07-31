import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_all_tool_scripts_compile() -> None:
    tools = Path(__file__).resolve().parents[1] / "tools"
    for path in tools.rglob("*.py"):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")


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


def test_pool_service_uses_unbuffered_python(tmp_path: Path) -> None:
    service = load_pool_service()
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    args = service.parser().parse_args(["start", "--test", "straight"])
    command = service.runner_command(args, tmp_path)
    assert command[1] == "-u"
    assert "--enable-output" not in command


def test_pool_service_forwards_individual_motor_settings(tmp_path: Path) -> None:
    service = load_pool_service()
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    args = service.parser().parse_args(
        ["start", "--test", "motor", "--motor-number", "6", "--motor-pwm", "1475"]
    )
    command = service.runner_command(args, tmp_path)
    assert command[command.index("--motor-number") + 1] == "6"
    assert command[command.index("--motor-pwm") + 1] == "1475"


def test_runner_allows_twenty_second_straight_test() -> None:
    runner_module = load_video_runner()
    args = runner_module.parse_args([])
    args.test = "straight"
    args.duration = 20.0
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


@pytest.mark.parametrize("pwm", [1100, 1499, 1500, 1501, 1900])
def test_runner_rejects_unsafe_motor_pwm(pwm: int) -> None:
    runner_module = load_video_runner()
    args = runner_module.parse_args([])
    args.test = "motor"
    args.duration = 1.0
    args.motor_pwm = pwm
    if pwm in (1499, 1501):
        runner_module.validate_controls(args)
    else:
        with pytest.raises(ValueError, match="motor-pwm"):
            runner_module.validate_controls(args)


class FakeCommandMav:
    def __init__(self) -> None:
        self.calls = []
        self.manual_calls = []

    def command_int_send(self, *args) -> None:
        self.calls.append(args)

    def manual_control_send(self, *args) -> None:
        self.manual_calls.append(args)


def test_runner_translates_human_motor_number_to_ardusub_output_index() -> None:
    runner_module = load_video_runner()
    runner_module.mavutil = SimpleNamespace(
        mavlink=SimpleNamespace(MAV_FRAME_GLOBAL=0, MAV_CMD_DO_MOTOR_TEST=209)
    )
    mav = FakeCommandMav()
    master = SimpleNamespace(target_system=1, target_component=1, mav=mav)
    runner = runner_module.ArduSubRunner(master, SimpleNamespace(yaw_sign=1))
    runner.send_gcs_heartbeat = lambda: None
    runner.send_motor_test_pwm(6, 1525)
    assert len(mav.calls) == 1
    packet = mav.calls[0]
    assert packet[6] == 5.0  # user-facing M6 -> ArduSub's zero-based channel 5
    assert packet[7] == runner_module.MOTOR_TEST_THROTTLE_PWM
    assert packet[8] == 1525.0
    assert mav.manual_calls[0][1:5] == (0, 0, 500, 0)


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
