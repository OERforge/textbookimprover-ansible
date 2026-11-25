#!/bin/bash
# One scenario, run as root inside a fresh container of a supported release,
# with the collection mounted at /collection (tests/run-scenarios.sh starts it).
#
# It installs ansible-core from apt, makes an ordinary user with sudo, runs a
# playbook as that user, runs it again to see that nothing changes, then runs
# the user step alone with sudo taken away. With TI_TEST_BOOTSTRAP set, it
# does each of those through bootstrap.sh instead, which installs ansible-core
# and git itself and is given the user's sudo password at a terminal.
#
# Optional, in the environment:
#   TI_TEST_CA       a file of CA certificates to trust, for a network whose
#                    proxy inspects HTTPS (given to Node, pip, and uv as well)
#   TI_TEST_SOURCES  an apt sources file to use in place of the image's
#   TI_TEST_BINDEP   a folder holding bindep and its dependencies, to run
#                    tests/unit/test_bindep.py against this host
#   TI_TEST_SUITES   the TextbookImprover suites to run as the user afterward
#                    (tests/run-*.py names, space-separated), or "all"
#   TI_TEST_EXTRA    more -e options for every play
#   TI_TEST_PANDOCS  the Pandocs to run the suites with, each in turn: versions
#                    the play installed (pandoc_versions), or 3.9 for the
#                    suites' stand-in for it; the play's default if unset
#   TI_TEST_SKIPS    the skips the suites may leave (tests/check-skips.py):
#                    a file of patterns, or "none" not to check them;
#                    tests/skips/<playbook>.txt if unset
#   TI_TEST_PLAYBOOK the collection's playbook to run: user (the default) or
#                    developer
#   TI_TEST_BOOTSTRAP  set to anything, to run the playbook through
#                    bootstrap.sh, fetching the collection from /collection
#                    at the commit checked out there
#   TI_TEST_PROXY    an HTTP proxy for apt and the play's downloads, for a
#                    container that reaches the network only through one
#                    (tests/run-scenarios.sh then shares the host's network)
set -eu -o pipefail

say() { printf '\n== %s\n' "$*"; }
export DEBIAN_FRONTEND=noninteractive

proxy_env=()
playbook="${TI_TEST_PLAYBOOK:-user}"
case "$playbook" in
    user|developer) ;;
    *) echo "TI_TEST_PLAYBOOK is $playbook; it's user or developer." >&2; exit 2 ;;
esac
if [ -n "${TI_TEST_PROXY:-}" ]; then
    printf 'Acquire::http::Proxy "%s";\nAcquire::https::Proxy "%s";\n' \
        "$TI_TEST_PROXY" "$TI_TEST_PROXY" > /etc/apt/apt.conf.d/90test-proxy
    # A minimal image has no CA bundle until ca-certificates is installed,
    # and apt's own user may not be able to read the file where it's mounted.
    if [ -n "${TI_TEST_CA:-}" ]; then
        install -m 0644 "$TI_TEST_CA" /etc/apt/test-ca.crt
        printf 'Acquire::https::CAInfo "/etc/apt/test-ca.crt";\n' >> /etc/apt/apt.conf.d/90test-proxy
    fi
    for name in http_proxy https_proxy HTTP_PROXY HTTPS_PROXY; do
        export "$name=$TI_TEST_PROXY"
        proxy_env+=("$name=$TI_TEST_PROXY")
    done
    export no_proxy=localhost,127.0.0.1 NO_PROXY=localhost,127.0.0.1
    proxy_env+=(no_proxy=localhost,127.0.0.1 NO_PROXY=localhost,127.0.0.1)
fi
if [ -n "${TI_TEST_SOURCES:-}" ]; then
    cp "$TI_TEST_SOURCES" /etc/apt/sources.list
fi
if [ -n "${TI_TEST_CA:-}" ]; then
    mkdir -p /usr/local/share/ca-certificates
    awk '/BEGIN CERTIFICATE/ {n++} n {print > ("/usr/local/share/ca-certificates/test-ca-" n ".crt")}' \
        "$TI_TEST_CA"
    # Node and pip may keep lists of their own; give them the system's, which
    # update-ca-certificates makes below.
    proxy_env+=(NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt
                PIP_CERT=/etc/ssl/certs/ca-certificates.crt
                SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt)
fi

apt-get update -qq
if [ -n "${TI_TEST_BOOTSTRAP:-}" ]; then
    say "sudo from apt; bootstrap.sh installs ansible-core and git"
    apt-get install -y -qq --no-install-recommends sudo ca-certificates >/dev/null
else
    say "ansible-core from apt"
    apt-get install -y -qq --no-install-recommends ansible-core sudo ca-certificates >/dev/null
    ansible --version | head -1
fi
update-ca-certificates >/dev/null 2>&1 || true

say "an ordinary user with sudo"
useradd -m -s /bin/bash tester
if [ -n "${TI_TEST_BOOTSTRAP:-}" ]; then
    # A password sudo asks for, as on a machine of one's own; made here, for
    # this container alone.
    tester_password=$(head -c 12 /dev/urandom | od -An -tx1 | tr -d ' \n')
    printf 'tester:%s\n' "$tester_password" | chpasswd
    usermod -aG sudo tester
    # bootstrap.sh fetches the collection from /collection, which another
    # user owns, so git is told to trust it.
    printf '[safe]\n\tdirectory = *\n' > ~tester/.gitconfig
    chown tester: ~tester/.gitconfig
else
    echo 'tester ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/tester
fi
mkdir -p /opt/collections/ansible_collections/oerforge
ln -s /collection /opt/collections/ansible_collections/oerforge/textbookimprover

as_tester() {
    sudo -u tester -H env ANSIBLE_COLLECTIONS_PATH=/opt/collections \
        ANSIBLE_FORCE_COLOR=0 ${proxy_env[@]+"${proxy_env[@]}"} "$@"
}
play() {
    if [ -n "${TI_TEST_BOOTSTRAP:-}" ]; then
        # At a terminal, which script(1) gives it, typing the password once.
        printf '%s\n' "$tester_password" |
            as_tester script -qec \
                "sh /collection/bootstrap.sh --repository /collection --ref HEAD --yes --profile $playbook $* -- ${TI_TEST_EXTRA:-}" \
                /dev/null
        return
    fi
    # shellcheck disable=SC2086
    as_tester ansible-playbook -i localhost, -c local ${TI_TEST_EXTRA:-} \
        "oerforge.textbookimprover.$playbook" "$@"
}

if [ -n "${TI_TEST_BINDEP:-}" ] && [ -z "${TI_TEST_BOOTSTRAP:-}" ]; then
    say "the bindep lookup against bindep itself, on this host"
    cat > /tmp/facts.yml <<'PLAY'
- hosts: all
  gather_facts: true
  tasks:
    - ansible.builtin.copy:
        content: "{{ ansible_facts | to_json }}"
        dest: /tmp/facts.json
        mode: "0644"
PLAY
    as_tester ansible-playbook -i localhost, -c local \
        -e ansible_python_interpreter=/usr/bin/python3 /tmp/facts.yml > /dev/null
    PYTHONPATH="$TI_TEST_BINDEP" python3 /collection/tests/unit/test_bindep.py /tmp/facts.json
fi

# The play's last lines, or through bootstrap.sh, which says more after them,
# its recap.
ending() {
    if [ -n "${TI_TEST_BOOTSTRAP:-}" ]; then
        sed -n '/PLAY RECAP/{n;p;}'
    else
        tail -4
    fi
}

say "the $playbook playbook, first run"
play | tee /tmp/first.log | tail -25

say "the $playbook playbook, second run: nothing should change"
play | tee /tmp/second.log | ending
if ! grep -Eq 'changed=0 +unreachable=0 +failed=0' /tmp/second.log; then
    echo "FAIL: the second run changed something"
    exit 1
fi

say "the user step alone, with sudo taken away"
if [ -n "${TI_TEST_BOOTSTRAP:-}" ]; then
    gpasswd -d tester sudo >/dev/null
    play --user-only | ending
else
    rm /etc/sudoers.d/tester
    play --tags user | ending
fi

say "what the user's shell has"
as_tester bash -ic 'echo "T=$T"; command -v pandoc; pandoc --version | head -1;
    git -C "$T" log -1 --format="%h %s";
    if command -v lualatex >/dev/null; then
        command -v lualatex; lualatex --version | head -1
    fi
    for v in EPUBCHECK_JAR VNU_JAR VERAPDF VERAPDF_WCAG; do
        [ -n "${!v:-}" ] && echo "$v=${!v}"
    done
    [ -n "${EPUBCHECK_JAR:-}" ] && java -jar "$EPUBCHECK_JAR" --version 2>&1 | head -1
    [ -n "${VNU_JAR:-}" ] && echo "vnu $(java -jar "$VNU_JAR" --version 2>&1)"
    [ -n "${VERAPDF:-}" ] && "$VERAPDF" --version 2>&1 | head -1
    ls ~/.local/bin | grep "^pandoc-" | tr "\n" " "; echo
    if command -v python3.9 >/dev/null; then command -v python3.9; python3.9 --version; fi
    if command -v soffice >/dev/null; then soffice --version; fi
    [ -n "${CNX_COOKBOOK:-}" ] && echo "CNX_COOKBOOK=$CNX_COOKBOOK $(git -C "$CNX_COOKBOOK" rev-parse --short HEAD)"
    for v in PLAYWRIGHT_BROWSERS_PATH PUPPETEER_EXECUTABLE_PATH; do
        [ -n "${!v:-}" ] && echo "$v=${!v}"
    done
    if [ -n "${PLAYWRIGHT_BROWSERS_PATH:-}" ]; then
        command -v python3; python3 -m playwright --version
        if command -v ace-puppeteer >/dev/null; then
            command -v node; node --version; echo "ace $(ace-puppeteer --version)"
        fi
        python3 "$T/bin/check-output.py" --wcag 2>&1 | grep -E "axe-core|Ace|sandbox|network"
    fi
    true' 2>/dev/null
{ grep -h -A4 "Check that it.s recent enough" /tmp/first.log | grep -o "LaTeX [0-9-]*" | head -1; } || true

# The suites under each Pandoc TI_TEST_PANDOCS names: one the play
# installed, by a link named pandoc first on the PATH, or 3.9, the suites'
# own stand-in for it (tests/pandoc39) over the play's newest Pandoc.
# Why a Pandoc's suites failed, where a log kept only by the runner shows
# it: run-all.sh's summary of the suites that failed and their FAIL and
# ERROR lines, which it writes on stderr, and the last lines of each
# failed suite's own output, where a traceback or a stopped run shows
# though it has no FAIL line. A single suite's run (not "all") shows the
# end of its output.
show_why () {
    local log="/tmp/suites-$1.log" err="/tmp/suites-$1.err" names
    echo "--- why, with Pandoc $1"
    if [ "$TI_TEST_SUITES" != all ]; then
        tail -n 40 "$log"
        tail -n 20 "$err"
        return
    fi
    sed -n '/^[0-9]* suite(s) failed:/,$p' "$err" | head -n 60
    names=$(sed -n 's/^[0-9]* suite(s) failed://p' "$err" | tail -n 1)
    if [ -z "$names" ]; then
        # run-all.sh stopped before its summary: the end of what it wrote.
        tail -n 40 "$log"
        tail -n 20 "$err"
        return
    fi
    awk -v names="$names" '
        BEGIN { n = split(names, list, " "); for (i = 1; i <= n; i++) want[list[i]] = 1 }
        function flush() {
            if (name in want) {
                print "--- the end of " name "'"'"'s output"
                start = count > 30 ? count - 29 : 1
                for (i = start; i <= count; i++) print kept[i]
            }
            count = 0
        }
        /^=== / { flush(); name = $2; next }
        name != "" { kept[++count] = $0 }
        END { flush() }
    ' "$log" | head -n 200
}
suites_failed=()
skips_failed=()
allowed_skips=${TI_TEST_SKIPS:-/collection/tests/skips/$playbook.txt}
if [ -n "${TI_TEST_SUITES:-}" ]; then
    for version in ${TI_TEST_PANDOCS:-default}; do
        case $version in
            default) front='' ;;
            3.9) front='$T/tests/pandoc39:' ;;
            *)
                mkdir -p "/opt/pandoc-$version"
                ln -sf "/home/tester/.local/bin/pandoc-$version" "/opt/pandoc-$version/pandoc"
                front="/opt/pandoc-$version:" ;;
        esac
        say "TextbookImprover's suites, as the user, with Pandoc ${version}: ${TI_TEST_SUITES}"
        if [ "$TI_TEST_SUITES" = all ]; then
            command='cd "$T" && pandoc --version | head -1 && tests/run-all.sh -j 2'
        else
            command='cd "$T"/tests && pandoc --version | head -1'
            for suite in $TI_TEST_SUITES; do
                command="$command && python3 $suite"
            done
        fi
        # run-all.sh lists the skips, and any suite it didn't run, on stderr.
        if ! as_tester bash -ic "PATH=\"$front\$PATH\"; $command" \
                > "/tmp/suites-$version.log" 2> "/tmp/suites-$version.err"; then
            suites_failed+=("$version")
            failed=yes
        else
            failed=
        fi
        head -1 "/tmp/suites-$version.log"
        grep -E '^(FAIL|  FAIL)|All suites passed|passed$' "/tmp/suites-$version.log" | tail -4 || true
        if [ -n "$failed" ]; then
            show_why "$version"
        fi
        if [ "$TI_TEST_SUITES" != all ]; then
            echo "skips: $(grep -c '^  skip' "/tmp/suites-$version.log"), not checked: not every suite ran"
        elif [ "$allowed_skips" = none ] || [ ! -f "$allowed_skips" ]; then
            # The list as run-all.sh gives it, so that one can be made from it.
            sed -n '/^[0-9]* check(s) skipped/,/^[0-9]* suite(s) failed/p' "/tmp/suites-$version.err"
            grep '^skipped: ' "/tmp/suites-$version.err" || true
            echo "skips not checked: no list of the skips allowed (TI_TEST_SKIPS)"
        elif ! python3 /collection/tests/check-skips.py "/tmp/suites-$version.err" \
                "$allowed_skips" "$version"; then
            skips_failed+=("$version")
        fi
    done
fi
if [ ${#suites_failed[@]} -gt 0 ]; then
    say "FAIL: the suites failed with Pandoc ${suites_failed[*]}"
    exit 1
fi
if [ ${#skips_failed[@]} -gt 0 ]; then
    say "FAIL: the suites skipped what the playbook should have made possible, with Pandoc ${skips_failed[*]}"
    exit 1
fi
say "done"
