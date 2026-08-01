"""Competition-video mission plan with no direct hardware I/O.

The module deliberately describes intent only.  A tested vehicle adapter must turn
these steps into MAVLink commands.  Keeping the mission plan independent from the
Pixhawk prevents unit tests and dry runs from ever arming a real vehicle.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, List, Tuple


class MotionKind(str, Enum):
    WAIT = "wait"
    DIVE = "dive"
    STRAIGHT = "straight"
    TURN_RIGHT = "turn_right"
    CIRCLE_RIGHT = "circle_right"
    STOP = "stop"


@dataclass(frozen=True)
class MissionStep:
    name: str
    kind: MotionKind
    minimum_seconds: float = 0.0
    degrees: float = 0.0
    diameter_m: float = 0.0
    target_distance_m: float = 0.0

    def validate(self) -> None:
        if self.minimum_seconds < 0.0:
            raise ValueError(f"{self.name}: duration cannot be negative")
        if self.kind is MotionKind.DIVE and self.minimum_seconds <= 0.0:
            raise ValueError(f"{self.name}: dive duration must be positive")
        if self.kind is MotionKind.STRAIGHT and self.minimum_seconds < 15.0:
            raise ValueError(f"{self.name}: straight movement must last at least 15 s")
        if self.kind is MotionKind.STRAIGHT and self.target_distance_m <= 0.0:
            raise ValueError(f"{self.name}: target distance must be positive")
        if self.kind is MotionKind.TURN_RIGHT and self.degrees <= 0.0:
            raise ValueError(f"{self.name}: turn angle must be positive")
        if self.kind is MotionKind.CIRCLE_RIGHT:
            if self.degrees < 360.0:
                raise ValueError(f"{self.name}: circle must be at least one full turn")
            if self.diameter_m < 1.0:
                raise ValueError(f"{self.name}: circle diameter must be at least 1 m")


@dataclass(frozen=True)
class VideoMissionPlan:
    steps: Tuple[MissionStep, ...]

    @classmethod
    def competition_default(cls, dive_seconds: float = 0.0) -> "VideoMissionPlan":
        """Return the advanced-category video sequence.

        Open-loop MANUAL route (no compass / depth hold):
        wait → optional timed dive → 20 s straight → 90° → 20 s straight →
        ~2 m circle → 90° → 20 s straight → 90° → 20 s straight → stop.

        Straight legs use 20 seconds. Circle diameter and turn angles are
        pool-calibrated labels; timing comes from runner CLI parameters.
        Without a barometer, dive_seconds=0 means the operator places depth
        before start. A positive dive_seconds inserts an open-loop vertical
        thrust step after the clearance wait.
        """
        steps: List[MissionStep] = [
            MissionStep("operator_clearance", MotionKind.WAIT, minimum_seconds=5.0),
        ]
        if dive_seconds > 0.0:
            steps.append(
                MissionStep(
                    "open_loop_dive",
                    MotionKind.DIVE,
                    minimum_seconds=float(dive_seconds),
                )
            )
        steps.extend(
            (
                MissionStep(
                    "straight_1",
                    MotionKind.STRAIGHT,
                    minimum_seconds=20.0,
                    target_distance_m=3.0,
                ),
                MissionStep("right_90_1", MotionKind.TURN_RIGHT, degrees=90.0),
                MissionStep(
                    "straight_2",
                    MotionKind.STRAIGHT,
                    minimum_seconds=20.0,
                    target_distance_m=3.0,
                ),
                MissionStep(
                    "circle_2m_target",
                    MotionKind.CIRCLE_RIGHT,
                    degrees=360.0,
                    diameter_m=2.0,
                ),
                MissionStep(
                    "circle_exit_right_90", MotionKind.TURN_RIGHT, degrees=90.0
                ),
                MissionStep(
                    "straight_3",
                    MotionKind.STRAIGHT,
                    minimum_seconds=20.0,
                    target_distance_m=3.0,
                ),
                MissionStep("right_90_2", MotionKind.TURN_RIGHT, degrees=90.0),
                MissionStep(
                    "straight_4",
                    MotionKind.STRAIGHT,
                    minimum_seconds=20.0,
                    target_distance_m=3.0,
                ),
                MissionStep("stop", MotionKind.STOP),
            )
        )
        plan = cls(steps=tuple(steps))
        plan.validate()
        return plan

    def validate(self) -> None:
        for step in self.steps:
            step.validate()

        straight_steps = [
            step for step in self.steps if step.kind is MotionKind.STRAIGHT
        ]
        if len(straight_steps) != 4:
            raise ValueError("video mission must contain exactly four straight legs")
        if not self.steps or self.steps[-1].kind is not MotionKind.STOP:
            raise ValueError("video mission must end with STOP")

    def summary_lines(self) -> Tuple[str, ...]:
        """Human-readable step list for dry-run / pre-arm prints."""
        lines = []
        for index, step in enumerate(self.steps, start=1):
            extra = ""
            if step.kind is MotionKind.STRAIGHT:
                extra = (
                    f" duration={step.minimum_seconds:.1f}s "
                    f"target_distance={step.target_distance_m:.1f}m"
                )
            elif step.kind is MotionKind.TURN_RIGHT:
                extra = f" intended={step.degrees:.0f}deg (timed open-loop)"
            elif step.kind is MotionKind.CIRCLE_RIGHT:
                extra = (
                    f" intended={step.degrees:.0f}deg "
                    f"diameter={step.diameter_m:.1f}m (timed open-loop)"
                )
            elif step.kind is MotionKind.DIVE:
                extra = f" duration={step.minimum_seconds:.1f}s (open-loop vertical)"
            elif step.kind is MotionKind.WAIT:
                extra = f" duration={step.minimum_seconds:.1f}s"
            lines.append(
                f"[{index:02d}/{len(self.steps):02d}] {step.name:24} "
                f"kind={step.kind.value}{extra}"
            )
        return tuple(lines)

    def __iter__(self) -> Iterable[MissionStep]:
        return iter(self.steps)
