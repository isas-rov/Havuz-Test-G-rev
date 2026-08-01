#!/usr/bin/env bash
# Persistent convenience functions for /home/admin/isas/software pool tests.
#
# Vertical is a single mixer z command: physical M3 (OUT5) and M4 (OUT6)
# receive the same thrust demand. There is no M3/M4 power split here.
#
# Logical motor number (ArduSub board order) → physical label:
#   1→M1  2→M2  3→M5  4→M6  5→M3(vertical)  6→M4(vertical)

POOL_TEST_ROOT="/home/admin/isas/software"

_pool_test_run() {
    (
        cd "$POOL_TEST_ROOT" || exit 1
        "$POOL_TEST_ROOT/.venv/bin/python" tools/pool_test_service.py "$@"
    )
}

_pool_usage() {
    echo "Usage:"
    echo "  pool-motor    MOTOR_NUMBER PWM SECONDS [COUNTDOWN]"
    echo "  pool-forward  FORWARD SECONDS [COUNTDOWN]"
    echo "  pool-vertical VERTICAL SECONDS [COUNTDOWN]"
    echo "  pool-combined FORWARD VERTICAL SECONDS [COUNTDOWN]"
    echo "  pool-turn     YAW SECONDS [COUNTDOWN]"
    echo "  pool-status | pool-stop | pool-audit [--lines N] [--full]"
    echo ""
    echo "Ranges:"
    echo "  motor number = 1..6 (5=physical M3, 6=physical M4)"
    echo "  motor PWM    = 1100..1900 except neutral 1500; start with 1525 / 1475"
    echo "  motor seconds= 1..3"
    echo "  forward/yaw  = -1000..1000 except 0"
    echo "  vertical     = 0..1000 except neutral 500"
    echo "                 (this vehicle: 1000≈down, 0≈up; both verticals equal)"
    echo "  move seconds = 1..60   turn seconds = 0.2..60"
    echo ""
    echo "Examples:"
    echo "  pool-motor 6 1525 2 10"
    echo "  pool-motor 5 1525 2 10"
    echo "  pool-forward -300 3 10"
    echo "  pool-vertical 600 3 10"
}

_pool_is_int() {
    [[ "$1" =~ ^-?[0-9]+$ ]]
}

pool-motor() {
    if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
        _pool_usage
        return 2
    fi
    local motor="$1" pwm="$2" seconds="$3" countdown="${4:-15}"
    if ! _pool_is_int "$motor" || [ "$motor" -lt 1 ] || [ "$motor" -gt 6 ]; then
        echo "ERROR: MOTOR_NUMBER must be an integer 1..6 (5=M3, 6=M4)."
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
    if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
        _pool_usage
        return 2
    fi
    local vertical="$1" seconds="$2" countdown="${3:-15}"
    if ! _pool_is_int "$vertical" \
        || [ "$vertical" -lt 0 ] || [ "$vertical" -gt 1000 ] \
        || [ "$vertical" -eq 500 ]; then
        echo "ERROR: VERTICAL must be an integer 0..1000 except neutral 500."
        echo "Both physical M3 and M4 get the same mixer demand."
        echo "Example down: pool-vertical 600 3 10"
        echo "Example up:   pool-vertical 400 3 10"
        return 2
    fi
    if ! _pool_is_int "$seconds" || [ "$seconds" -lt 1 ] || [ "$seconds" -gt 60 ]; then
        echo "ERROR: SECONDS must be an integer 1..60."
        return 2
    fi
    _pool_test_run start \
        --test vertical --vertical "$vertical" --duration "$seconds" \
        --countdown "$countdown" \
        --enable-output --confirm MOTORS_ARE_CLEAR \
        --confirm-high-output HIGH_OUTPUT_RESTRAINED \
        --confirm-long-vertical LONG_FULL_OUTPUT_RESTRAINED
}

pool-combined() {
    if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
        _pool_usage
        return 2
    fi
    local forward="$1" vertical="$2" seconds="$3" countdown="${4:-15}"
    if ! _pool_is_int "$forward" || [ "$forward" -eq 0 ] \
        || [ "$forward" -lt -1000 ] || [ "$forward" -gt 1000 ]; then
        echo "ERROR: FORWARD must be an integer -1000..1000 except 0."
        return 2
    fi
    if ! _pool_is_int "$vertical" \
        || [ "$vertical" -lt 0 ] || [ "$vertical" -gt 1000 ] \
        || [ "$vertical" -eq 500 ]; then
        echo "ERROR: VERTICAL must be an integer 0..1000 except neutral 500."
        return 2
    fi
    if ! _pool_is_int "$seconds" || [ "$seconds" -lt 1 ] || [ "$seconds" -gt 60 ]; then
        echo "ERROR: SECONDS must be an integer 1..60."
        return 2
    fi
    _pool_test_run start \
        --test combined --forward "$forward" --vertical "$vertical" \
        --duration "$seconds" --straight-yaw-trim 0 --countdown "$countdown" \
        --enable-output --confirm MOTORS_ARE_CLEAR \
        --confirm-all-motors ALL_MOTORS_RESTRAINED \
        --confirm-high-output HIGH_OUTPUT_RESTRAINED \
        --confirm-long-forward LONG_FULL_OUTPUT_RESTRAINED \
        --confirm-long-vertical LONG_FULL_OUTPUT_RESTRAINED
}

pool-turn() {
    if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
        _pool_usage
        return 2
    fi
    local yaw="$1" seconds="$2" countdown="${3:-15}"
    if ! _pool_is_int "$yaw" || [ "$yaw" -eq 0 ] \
        || [ "$yaw" -lt -1000 ] || [ "$yaw" -gt 1000 ]; then
        echo "ERROR: YAW must be an integer -1000..1000 except 0."
        return 2
    fi
    # turn seconds may be fractional (e.g. 2.5); only reject empty/non-numeric lightly
    if ! [[ "$seconds" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
        echo "ERROR: turn SECONDS must be a number 0.2..60."
        return 2
    fi
    _pool_test_run start \
        --test turn-right --degrees 30 --turn-yaw "$yaw" \
        --turn-seconds "$seconds" --yaw-sign 1 --countdown "$countdown" \
        --enable-output --confirm MOTORS_ARE_CLEAR \
        --confirm-high-output HIGH_OUTPUT_RESTRAINED \
        --confirm-long-turn LONG_FULL_OUTPUT_RESTRAINED
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
