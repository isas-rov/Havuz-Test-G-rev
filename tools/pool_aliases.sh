#!/usr/bin/env bash
# Persistent convenience functions for /home/admin/isas/software pool tests.

POOL_TEST_ROOT="/home/admin/isas/software"

_pool_test_run() {
    (
        cd "$POOL_TEST_ROOT" || exit 1
        "$POOL_TEST_ROOT/.venv/bin/python" tools/pool_test_service.py "$@"
    )
}

_pool_usage() {
    echo "Usage:"
    echo "  pool-forward  FORWARD SECONDS [COUNTDOWN]"
    echo "  pool-vertical VERTICAL SECONDS [COUNTDOWN]"
    echo "  pool-combined FORWARD VERTICAL SECONDS [COUNTDOWN]"
    echo "  pool-turn      YAW SECONDS [COUNTDOWN]"
    echo "Ranges: axes=-1000..1000, movement seconds=1..60, turn seconds=0.2..60"
}

pool-forward() {
    if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
        _pool_usage
        return 2
    fi
    local forward="$1" seconds="$2" countdown="${3:-15}"
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
