#!/bin/bash
# Started as "sh script", which may not be bash: start again with bash.
if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi
# Run every check whose needs are met, and say which were skipped and why.
#
#   tests/run-all.sh                  the quick checks
#   tests/run-all.sh --containers     and the playbook in a fresh container of
#                                     each image in TI_TEST_IMAGES
#   tests/run-all.sh --suites         and TextbookImprover's suites in each
#                                     container afterward (implies --containers)
#   tests/run-all.sh --no-skip        a check that can't run fails (the
#                                     containers only when asked for)
#
# The checks, and what each needs:
#   secrets     tests/check-secrets.py: python3 and git
#   bindep      tests/unit/test_bindep.py: bindep importable by python3, or a
#               folder holding it named by TI_TEST_BINDEP
#   pins        tests/unit/test_update_pins.py: python3 and PyYAML
#   skips       tests/unit/test_check_skips.py: python3
#   retry       tests/unit/test_retryable.py: python3
#   lint        ansible-lint on PATH (run offline, at its production profile)
#   shell       dash and shellcheck on PATH, for bootstrap.sh, which is POSIX sh
#   containers  tests/run-scenarios.sh: Docker, and the network
#
# TI_TEST_IMAGES is "ubuntu:24.04 ubuntu:26.04" if unset. Everything else
# tests/scenario.sh reads (TI_TEST_CA, TI_TEST_SOURCES, TI_TEST_BINDEP,
# TI_TEST_EXTRA, TI_TEST_BOOTSTRAP, TI_TEST_SKIPS) is passed on to the
# containers as it is.
set -u
here=$(cd "$(dirname "$0")/.." && pwd)

containers=false
suites=false
no_skip=false
for arg in "$@"; do
    case $arg in
        --containers) containers=true ;;
        --suites) containers=true; suites=true ;;
        --no-skip) no_skip=true ;;
        -h|--help) sed -n '/^# Run every check/,/^set -u/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
        *) echo "run-all.sh: unknown option $arg (try --help)" >&2; exit 2 ;;
    esac
done

passed=()
failed=()
skipped=()

skip() {
    if $no_skip && [ "${3:-}" != asked ]; then
        printf 'FAIL %s: can'"'"'t run: %s\n' "$1" "$2"
        failed+=("$1 (can't run: $2)")
    else
        printf 'skip %s: %s\n' "$1" "$2"
        skipped+=("$1 ($2)")
    fi
}

run() {
    local name=$1
    shift
    printf '\n######## %s\n' "$name"
    if "$@"; then
        passed+=("$name")
    else
        printf 'FAIL %s\n' "$name"
        failed+=("$name")
    fi
}

have() { command -v "$1" >/dev/null 2>&1; }

# secrets
if ! have python3; then
    skip secrets "no python3"
elif ! have git || ! git -C "$here" rev-parse --git-dir >/dev/null 2>&1; then
    skip secrets "not in a git clone, or no git"
else
    run secrets python3 "$here/tests/check-secrets.py"
fi

# bindep
bindep_path=${TI_TEST_BINDEP:+$TI_TEST_BINDEP${PYTHONPATH:+:$PYTHONPATH}}
bindep_path=${bindep_path:-${PYTHONPATH:-}}
if ! have python3; then
    skip bindep "no python3"
elif ! PYTHONPATH=$bindep_path python3 -c 'import bindep.depends' >/dev/null 2>&1; then
    skip bindep "python3 can't import bindep; pip install bindep, or name a folder holding it in TI_TEST_BINDEP"
else
    run bindep env PYTHONPATH="$bindep_path" python3 "$here/tests/unit/test_bindep.py"
fi

# pins: util/update-pins.py's parts that need no network
if ! have python3; then
    skip pins "no python3"
elif ! python3 -c 'import yaml' >/dev/null 2>&1; then
    skip pins "python3 can't import yaml; apt install python3-yaml"
else
    run pins python3 "$here/tests/unit/test_update_pins.py"
fi

# skips: tests/check-skips.py, and the lists of skips each playbook allows
if have python3; then
    run skips python3 "$here/tests/unit/test_check_skips.py"
else
    skip skips "no python3"
fi

# retry: the rule for trying a download again, against the results downloads
# really give
if have python3; then
    run retry python3 "$here/tests/unit/test_retryable.py"
else
    skip retry "no python3"
fi

# lint: ansible-lint wants the collection where Ansible would find it, so it
# gets a link in a folder of its own.
lint() {
    local top status
    top=$(mktemp -d) || return 1
    mkdir -p "$top/ansible_collections/oerforge"
    ln -s "$here" "$top/ansible_collections/oerforge/textbookimprover"
    (cd "$top/ansible_collections/oerforge/textbookimprover" &&
        ANSIBLE_COLLECTIONS_PATH=$top ansible-lint --offline)
    status=$?
    rm -rf "$top"
    return $status
}
if ! have ansible-lint; then
    skip lint "no ansible-lint on PATH; pipx install ansible-lint"
else
    run lint lint
fi

# shell: bootstrap.sh is POSIX sh throughout, so dash, which is Debian's and
# Ubuntu's sh, has to parse it, and ShellCheck finds nothing in it as sh.
# And it's one group, read whole before any of it runs, so every copy of it
# cut short at a line's end, from its first command on, fails to parse, and
# runs nothing.
shell_check() {
    dash -n "$here/bootstrap.sh" && shellcheck -s sh "$here/bootstrap.sh" || return 1
    local lines first n
    lines=$(wc -l < "$here/bootstrap.sh")
    first=$(grep -n -v -m 1 -e '^#' -e '^$' "$here/bootstrap.sh" | cut -d: -f1)
    for ((n = first; n < lines; n++)); do
        if head -n "$n" "$here/bootstrap.sh" | dash -n 2>/dev/null; then
            echo "bootstrap.sh cut short after line $n of $lines parses, so it would run" >&2
            return 1
        fi
    done
}
if ! have dash; then
    skip shell "no dash; apt install dash"
elif ! have shellcheck; then
    skip shell "no shellcheck on PATH; apt install shellcheck, or pipx install shellcheck-py"
else
    run shell shell_check
fi

# containers
if ! $containers; then
    skip containers "not asked for; --containers runs them" asked
elif ! have docker; then
    skip containers "no docker"
elif ! docker info >/dev/null 2>&1; then
    skip containers "docker is there but its daemon isn't answering"
else
    read -r -a images <<<"${TI_TEST_IMAGES:-ubuntu:24.04 ubuntu:26.04}"
    if $suites; then
        run containers env TI_TEST_SUITES=all "$here/tests/run-scenarios.sh" "${images[@]}"
    else
        run containers env -u TI_TEST_SUITES "$here/tests/run-scenarios.sh" "${images[@]}"
    fi
fi

printf '\n######## summary\n'
for name in ${passed[@]+"${passed[@]}"}; do printf 'ok   %s\n' "$name"; done
for name in ${skipped[@]+"${skipped[@]}"}; do printf 'skip %s\n' "$name"; done
for name in ${failed[@]+"${failed[@]}"}; do printf 'FAIL %s\n' "$name"; done
if [ ${#failed[@]} -gt 0 ]; then
    exit 1
fi
if [ ${#passed[@]} -eq 0 ]; then
    echo "Nothing ran."
    exit 1
fi
