#!/bin/bash
# One scenario, run as root inside a fresh container of a supported release,
# with the collection mounted at /collection (tests/run-scenarios.sh starts it).
#
# It installs ansible-core from apt, as bootstrap.sh will, makes an ordinary
# user with sudo, runs the user playbook as that user, runs it again to see
# that nothing changes, then runs the user step alone with sudo taken away.
#
# Optional, in the environment:
#   TI_TEST_CA       a file of CA certificates to trust, for a network whose
#                    proxy inspects HTTPS (given to Node and pip as well)
#   TI_TEST_SOURCES  an apt sources file to use in place of the image's
#   TI_TEST_BINDEP   a folder holding bindep and its dependencies, to run
#                    tests/unit/test_bindep.py against this host
#   TI_TEST_SUITES   the TextbookImprover suites to run as the user afterward
#                    (tests/run-*.py names, space-separated), or "all"
#   TI_TEST_EXTRA    more -e options for every play
#   TI_TEST_PROXY    an HTTP proxy for apt and the play's downloads, for a
#                    container that reaches the network only through one
#                    (tests/run-scenarios.sh then shares the host's network)
set -eu -o pipefail

say() { printf '\n== %s\n' "$*"; }
export DEBIAN_FRONTEND=noninteractive

proxy_env=()
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
                PIP_CERT=/etc/ssl/certs/ca-certificates.crt)
fi

say "ansible-core from apt"
apt-get update -qq
apt-get install -y -qq --no-install-recommends ansible-core sudo ca-certificates >/dev/null
update-ca-certificates >/dev/null 2>&1 || true
ansible --version | head -1

say "an ordinary user with sudo"
useradd -m -s /bin/bash tester
echo 'tester ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/tester
mkdir -p /opt/collections/ansible_collections/oerforge
ln -s /collection /opt/collections/ansible_collections/oerforge/textbookimprover

as_tester() {
    sudo -u tester -H env ANSIBLE_COLLECTIONS_PATH=/opt/collections \
        ANSIBLE_FORCE_COLOR=0 ${proxy_env[@]+"${proxy_env[@]}"} "$@"
}
play() {
    # shellcheck disable=SC2086
    as_tester ansible-playbook -i localhost, -c local ${TI_TEST_EXTRA:-} \
        oerforge.textbookimprover.user "$@"
}

if [ -n "${TI_TEST_BINDEP:-}" ]; then
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

say "the user playbook, first run"
play | tee /tmp/first.log | tail -25

say "the user playbook, second run: nothing should change"
play | tee /tmp/second.log | tail -4
if ! grep -Eq 'changed=0 +unreachable=0 +failed=0' /tmp/second.log; then
    echo "FAIL: the second run changed something"
    exit 1
fi

say "the user step alone, with sudo taken away"
rm /etc/sudoers.d/tester
play --tags user | tail -4

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

if [ -n "${TI_TEST_SUITES:-}" ]; then
    say "TextbookImprover's suites, as the user: ${TI_TEST_SUITES}"
    if [ "$TI_TEST_SUITES" = all ]; then
        as_tester bash -ic 'cd "$T" && tests/run-all.sh -j 2' 2>/dev/null
    else
        for suite in $TI_TEST_SUITES; do
            as_tester bash -ic "cd \"\$T\"/tests && python3 $suite" 2>/dev/null | tail -3
        done
    fi
fi
say "done"
