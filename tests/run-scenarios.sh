#!/bin/bash
# Run tests/scenario.sh in a fresh container of each image given, with Docker:
#
#   tests/run-scenarios.sh ubuntu:24.04 ubuntu:26.04 debian:13
#
# The environment variables tests/scenario.sh reads are passed on; a file
# they name is mounted read-only at the same path.
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
status=0
for image in "$@"; do
    printf '\n######## %s\n' "$image"
    mounts=(-v "$here:/collection:ro")
    envs=()
    for name in TI_TEST_CA TI_TEST_SOURCES TI_TEST_BINDEP TI_TEST_SUITES TI_TEST_EXTRA; do
        value=${!name:-}
        [ -n "$value" ] || continue
        envs+=(-e "$name=$value")
        if [ -e "$value" ]; then
            mounts+=(-v "$value:$value:ro")
        fi
    done
    if ! docker run --rm "${mounts[@]}" "${envs[@]}" "$image" \
            bash /collection/tests/scenario.sh; then
        echo "FAILED: $image"
        status=1
    fi
done
exit $status
