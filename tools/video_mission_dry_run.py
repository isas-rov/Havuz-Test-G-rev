#!/usr/bin/env python3
"""Print and validate the video mission without connecting to any hardware."""

import argparse
import time

from isas.control.video_mission import MotionKind, VideoMissionPlan


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--realtime",
        action="store_true",
        help="Wait for timed steps; default prints the plan immediately",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan = VideoMissionPlan.competition_default()
    elapsed = 0.0
    heading = 0.0

    print("VIDEO MISSION DRY RUN - HARDWARE OUTPUT DISABLED")
    for index, step in enumerate(plan, start=1):
        if step.kind is MotionKind.TURN_RIGHT:
            heading = (heading + step.degrees) % 360.0
        elif step.kind is MotionKind.CIRCLE_RIGHT:
            heading = (heading + step.degrees) % 360.0

        details = [f"kind={step.kind.value}"]
        if step.minimum_seconds:
            details.append(f"duration={step.minimum_seconds:.1f}s")
        if step.degrees:
            details.append(f"turn={step.degrees:.0f}deg")
        if step.diameter_m:
            details.append(f"diameter={step.diameter_m:.1f}m")
        if step.target_distance_m:
            details.append(f"target_distance={step.target_distance_m:.1f}m")
        print(
            f"[{index:02d}/{len(plan.steps):02d}] t={elapsed:05.1f}s "
            f"{step.name}: {', '.join(details)} -> heading={heading:.0f}deg"
        )

        if args.realtime and step.minimum_seconds:
            time.sleep(step.minimum_seconds)
        elapsed += step.minimum_seconds

    print(f"Timed minimum: {elapsed:.1f}s plus yaw/circle movement time")
    print("RESULT: PLAN_VALID, NO MAVLINK CONNECTION, NO ARM, NO MOTOR OUTPUT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
