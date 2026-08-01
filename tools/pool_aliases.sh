#!/usr/bin/env bash
# Persistent convenience functions for /home/admin/isas/software pool tests.
#
# EMERGENCY FORWARD-ONLY CONFIG (2026-08-02):
# Physical M4 and M6 ESCs failed. Working physical M3 was moved to the old M6
# slot on MAIN OUT 4. Vertical thrusters and full mission are cancelled for now.
#
# Logical motor (ArduSub) → current physical:
#   1→M1 (sol ön yatay)
#   2→M2 (sağ ön yatay)
#   3→M5 (sol arka yatay)
#   4→M3 relocated (sağ arka yatay, eski M6 yeri)
#   5→unused (eski M3 dikey)
#   6→unused (yanmış M4 dikey)

POOL_TEST_ROOT="/home/admin/isas/software"

_pool_test_run() {
    (
        cd "$POOL_TEST_ROOT" || exit 1
        "$POOL_TEST_ROOT/.venv/bin/python" tools/pool_test_service.py "$@"
    )
}

_pool_usage() {
    echo "FORWARD-ONLY mode (verticals/mission cancelled)"
    echo "Usage:"
    echo "  pool-motor    MOTOR_NUMBER PWM SECONDS [COUNTDOWN]"
    echo "  pool-forward  FORWARD SECONDS [COUNTDOWN]"
    echo "  pool-status | pool-stop | pool-audit [--lines N] [--full]"
    echo ""
    echo "Motor numbers now:"
    echo "  1=M1  2=M2  3=M5  4=M3(relocated to old M6/OUT4)"
    echo "  5/6 = unused (do not use)"
    echo "PWM=1100..1900 except 1500; motor seconds=1..3"
    echo "forward=-1000..1000 except 0; this vehicle often uses negative forward"
    echo ""
    echo "Examples:"
    echo "  pool-motor 4 1525 2 10"
    echo "  pool-forward -300 3 10"
}

_pool_is_int() {
    [[ "$1" =~ ^-?[0-9]+$ ]]
}

_pool_verticals_cancelled() {
    echo "LOCKED: vertical thrusters cancelled (M4 burned, M3 moved to OUT4)."
    echo "Use only pool-motor 1..4 and pool-forward for now."
    return 3
}

pool-motor() {
    if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
        _pool_usage
        return 2
    fi
    local motor="$1" pwm="$2" seconds="$3" countdown="${4:-15}"
    if ! _pool_is_int "$motor" || [ "$motor" -lt 1 ] || [ "$motor" -gt 6 ]; then
        echo "ERROR: MOTOR_NUMBER must be an integer 1..6."
        return 2
    fi
    if [ "$motor" -eq 5 ] || [ "$motor" -eq 6 ]; then
        echo "ERROR: motor $motor is unused in forward-only rewire."
        echo "Relocated M3 is on motor 4 / MAIN OUT 4."
        return 2
    fi
    if ! _pool_is_int "$pwm" || [ "$pwm" -lt 1100 ] || [ "$pwm" -gt 1900 ] || [ "$pwm" -eq 1500 ]; then
        echo "ERROR: PWM must be 1100..1900 and must not be neutral 1500."
        echo "Safe first try: pool-motor $motor 1525 2 10"
        return 2
    fi
    if ! _pool_is_int "$seconds" || [ "$seconds" -lt 1 ] || [ "$seconds" -gt 3 ]; then
        echo "ERROR: motor SECONDS must be an integer 1..3."
        return 2
    fi
    _pool_test_run start \
        --test motor --motor-number "$motor" --motor-pwm "$pwm" \
        --duration "$seconds" --countdown "$countdown" \
        --enable-output --confirm MOTORS_ARE_CLEAR
}

pool-forward() {
    if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
        _pool_usage
        return 2
    fi
    local forward="$1" seconds="$2" countdown="${3:-15}"
    if ! _pool_is_int "$forward" || [ "$forward" -eq 0 ] \
        || [ "$forward" -lt -1000 ] || [ "$forward" -gt 1000 ]; then
        echo "ERROR: FORWARD must be an integer -1000..1000 except 0."
        echo "This vehicle often uses negative forward (example: -300)."
        return 2
    fi
    if ! _pool_is_int "$seconds" || [ "$seconds" -lt 1 ] || [ "$seconds" -gt 60 ]; then
        echo "ERROR: SECONDS must be an integer 1..60."
        return 2
    fi
    _pool_test_run start \
        --test straight --forward "$forward" --duration "$seconds" \
        --straight-yaw-trim 0 --countdown "$countdown" \
        --enable-output --confirm MOTORS_ARE_CLEAR \
        --confirm-high-output HIGH_OUTPUT_RESTRAINED \
        --confirm-long-forward LONG_FULL_OUTPUT_RESTRAINED
}

pool-vertical() {
    _pool_verticals_cancelled
}

pool-combined() {
    _pool_verticals_cancelled
}

pool-turn() {
    echo "LOCKED: turn/mission work paused until forward-only rewire is verified."
    echo "First confirm pool-forward with motors 1-4, then we re-enable turns."
    return 3
}

pool-mission() {
    echo "LOCKED: full mission cancelled while running forward-only after ESC failure."
    echo "Repair/replace burned ESCs before re-enabling mission."
    return 3
}

pool-status() {
    _pool_test_run status
}

pool-stop() {
    _pool_test_run stop
}

pool-audit() {
    _pool_test_run audit "$@"
}

pool-help() {
    _pool_usage
}
