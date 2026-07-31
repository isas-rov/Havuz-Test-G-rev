"""Competition-video mission plan with no direct hardware I/O.

The module deliberately describes intent only.  A tested vehicle adapter must turn
these steps into MAVLink commands.  Keeping the mission plan independent from the
Pixhawk prevents unit tests and dry runs from ever arming a real vehicle.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Tuple


class MotionKind(str, Enum):
    WAIT = "wait"
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
    def competition_default(cls) -> "VideoMissionPlan":
        """Return the 13 July 2026 advanced-category video sequence.

        Straight legs use 20 seconds, giving five seconds of margin over the rule.
        The requested circle target is 2 m diameter; without position or velocity
        feedback this remains a pool-calibrated target rather than a measurement.
        The extra 90 degree turn after the circle follows the route diagram and
        points the vehicle toward the third side of the rectangular route.
        """
        plan = cls(
            steps=(
                MissionStep("operator_clearance", MotionKind.WAIT, minimum_seconds=5.0),
                MissionStep(
                    "straight_1", MotionKind.STRAIGHT,
                    minimum_seconds=20.0, target_distance_m=3.0,
                ),
                MissionStep("right_90_1", MotionKind.TURN_RIGHT, degrees=90.0),
                MissionStep(
                    "straight_2", MotionKind.STRAIGHT,
                    minimum_seconds=20.0, target_distance_m=3.0,
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
                    "straight_3", MotionKind.STRAIGHT,
                    minimum_seconds=20.0, target_distance_m=3.0,
                ),
                MissionStep("right_90_2", MotionKind.TURN_RIGHT, degrees=90.0),
                MissionStep(
                    "straight_4", MotionKind.STRAIGHT,
                    minimum_seconds=20.0, target_distance_m=3.0,
                ),
                MissionStep("stop", MotionKind.STOP),
            )
        )
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

    def __iter__(self) -> Iterable[MissionStep]:
        return iter(self.steps)
