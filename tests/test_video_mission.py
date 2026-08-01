import pytest

from isas.control.video_mission import (
    MissionStep,
    MotionKind,
    VideoMissionPlan,
)


def test_competition_plan_is_valid_and_has_four_straights() -> None:
    plan = VideoMissionPlan.competition_default()
    straights = [step for step in plan if step.kind is MotionKind.STRAIGHT]
    assert len(straights) == 4
    assert all(step.minimum_seconds >= 15.0 for step in straights)
    assert all(step.minimum_seconds == 20.0 for step in straights)
    assert all(step.target_distance_m == 3.0 for step in straights)
    assert plan.steps[0].kind is MotionKind.WAIT
    assert plan.steps[-1].kind is MotionKind.STOP
    assert not any(step.kind is MotionKind.DIVE for step in plan)


def test_competition_plan_can_insert_open_loop_dive() -> None:
    plan = VideoMissionPlan.competition_default(dive_seconds=3.0)
    dive = next(step for step in plan if step.kind is MotionKind.DIVE)
    assert dive.minimum_seconds == 3.0
    assert plan.steps[0].kind is MotionKind.WAIT
    assert plan.steps[1].kind is MotionKind.DIVE
    assert len([s for s in plan if s.kind is MotionKind.STRAIGHT]) == 4


def test_competition_circle_meets_minimums() -> None:
    plan = VideoMissionPlan.competition_default()
    circle = next(step for step in plan if step.kind is MotionKind.CIRCLE_RIGHT)
    assert circle.degrees >= 360.0
    assert circle.diameter_m >= 1.0
    assert circle.diameter_m == 2.0


def test_mission_summary_lists_every_step() -> None:
    plan = VideoMissionPlan.competition_default(dive_seconds=2.0)
    lines = plan.summary_lines()
    assert len(lines) == len(plan.steps)
    assert any("open_loop_dive" in line for line in lines)
    assert lines[-1].endswith("kind=stop") or "kind=stop" in lines[-1]


def test_short_straight_is_rejected() -> None:
    step = MissionStep(
        "too_short",
        MotionKind.STRAIGHT,
        minimum_seconds=14.9,
        target_distance_m=3.0,
    )
    with pytest.raises(ValueError, match="at least 15"):
        step.validate()
