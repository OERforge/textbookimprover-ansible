#!/bin/bash
# Started as "sh script", which may not be bash: start again with bash.
if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi
# Run tests/scenario.sh in a fresh container of each image given, with Docker:
#
#   tests/run-scenarios.sh ubuntu:24.04 ubuntu:26.04 debian:13
#
# The environment variables tests/scenario.sh reads are passed on; a file
# they name is mounted read-only at the same path. With TI_TEST_PROXY set, the
# container shares the host's network, so that it can reach a proxy listening
# on the host's own address.
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
status=0
for image in "$@"; do
    printf '\n######## %s\n' "$image"
    mounts=(-v "$here:/collection:ro")
    envs=()
    for name in TI_TEST_CA TI_TEST_SOURCES TI_TEST_BINDEP TI_TEST_SUITES TI_TEST_EXTRA TI_TEST_PROXY TI_TEST_PLAYBOOK TI_TEST_BOOTSTRAP TI_TEST_PANDOCS TI_TEST_SKIPS; do
        value=${!name:-}
        [ -n "$value" ] || continue
        envs+=(-e "$name=$value")
        if [ -e "$value" ]; then
            mounts+=(-v "$value:$value:ro")
        fi
    done
    network=()
    if [ -n "${TI_TEST_PROXY:-}" ]; then
        network=(--network host)
    fi
    if ! docker run --rm ${network[@]+"${network[@]}"} "${mounts[@]}" "${envs[@]}" "$image" \
            bash /collection/tests/scenario.sh; then
        echo "FAILED: $image"
        status=1
    fi
done
exit $status
