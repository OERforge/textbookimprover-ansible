#!/usr/bin/env python3
"""Hold the retryable test plugin to the results downloads really give.

The get_url results are as ansible-core reported them against a local server
that failed each way: 2.16.3 (Ubuntu 24.04's), 2.19.11 (Debian 13's), 2.20.1
(Ubuntu 26.04's), and 2.21.6 each worded them alike, but for a body cut
short, which 2.16 reports only as a checksum that doesn't match. The curl
results are curl 8.5.0's exit codes for the same, with --fail and
--write-out %{http_code}. The git results are as ansible.builtin.git reported
them with git 2.43.0 (Ubuntu 24.04's) and 2.47.3 (Debian 13's), both built with
GnuTLS, against a server that failed each way over both of git's protocols.
Needs python3 alone:

    python3 tests/unit/test_retryable.py
"""

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

spec = importlib.util.spec_from_file_location(
    "retryable_test", os.path.join(ROOT, "plugins", "test", "retryable.py"))
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)

failures = []


def check(what, result, expected):
    got = plugin.retryable(result)
    ok = got is expected
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        failures.append(what)
        print("     expected %s, got %s" % (expected, got))


def failed(msg, **rest):
    return dict(failed=True, changed=False, msg=msg, **rest)


CERT_MSG = ("Request failed: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] "
            "certificate verify failed: unable to get local issuer certificate "
            "(_ssl.c:%s)>")
CHECKSUM_MSG = ("The checksum for /tmp/retry2-partial-True did not match "
                "b0746a3ff99a6a9ed4b2dc770ea2a64f13ae742b027df17cbae0232d41774fe4; it was "
                "1be86fbe66183f707658aa07e095d28b425b2967c68d99e94b22f763b9887181.")

# Measured with all four releases unless named.
check("get_url: done", {"changed": True, "status_code": 200, "msg": "OK (300000 bytes)"}, False)
check("get_url: done, nothing to change", {"changed": False, "status_code": 200, "msg": "OK"}, False)
check("get_url: skipped", {"skipped": True, "changed": False}, False)
check("get_url: dropped before an answer",
      failed("Connection failure: Remote end closed connection without response"), True)
check("get_url: refused",
      failed("Request failed: <urlopen error [Errno 111] Connection refused>"), True)
check("get_url: a name not found",
      failed("Request failed: <urlopen error [Errno -2] Name or service not known>"), True)
check("get_url: no answer in time", failed("Connection failure: timed out"), True)
check("get_url: no more of the body in time",
      failed("failed to create temporary content file: timed out"), True)
check("get_url: reset in the body",
      failed("failed to create temporary content file: [Errno 104] Connection reset by peer"), True)
check("get_url 2.19 and later: cut short",
      failed("Incomplete read, (rsp.length=299000, cl=300000, st.st_size=1000) "
             "failed to read remaining 299000 bytes"), True)
check("get_url 2.16: cut short, with a checksum", failed(CHECKSUM_MSG), True)
check("get_url: 429", failed("Request failed", status_code=429, response="HTTP Error 429"), True)
check("get_url: 503", failed("Request failed", status_code=503, response="HTTP Error 503"), True)
check("get_url: 404", failed("Request failed", status_code=404, response="HTTP Error 404"), False)
check("get_url: 403", failed("Request failed", status_code=403, response="HTTP Error 403"), False)
check("get_url 2.16: an untrusted certificate", failed(CERT_MSG % "1000"), False)
check("get_url 2.21: an untrusted certificate", failed(CERT_MSG % "1035"), False)
KEY_USAGE_MSG = ("Request failed: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate "
                 "verify failed: CA cert does not include key usage extension (_ssl.c:%s)>")
check("get_url 2.19: a CA certificate OpenSSL refuses", failed(KEY_USAGE_MSG % "1029"), False)
check("get_url 2.20: a CA certificate OpenSSL refuses", failed(KEY_USAGE_MSG % "1081"), False)
check("get_url: a folder that isn't there",
      failed("Destination /nowhere does not exist"), False)
check("get_url: a checksum written wrong",
      failed("The checksum parameter has to be in format <algorithm>:<checksum>"), False)

check("curl: done", {"rc": 0, "stdout": "200", "changed": True}, False)
check("curl: skipped, the file there", {"rc": 0, "stdout": "skipped, since x exists", "changed": False}, False)
check("curl: an empty answer", {"failed": True, "rc": 52, "stdout": "000"}, True)
check("curl: cut short", {"failed": True, "rc": 18, "stdout": "200"}, True)
check("curl: refused", {"failed": True, "rc": 7, "stdout": "000"}, True)
check("curl: no answer in time", {"failed": True, "rc": 28, "stdout": "000"}, True)
check("curl: no more of the body in time", {"failed": True, "rc": 28, "stdout": "200"}, True)
check("curl: reset in the body", {"failed": True, "rc": 56, "stdout": "200"}, True)
check("curl: a name not found", {"failed": True, "rc": 6, "stdout": "000"}, True)
check("curl: 429", {"failed": True, "rc": 22, "stdout": "429"}, True)
check("curl: 503", {"failed": True, "rc": 22, "stdout": "503"}, True)
check("curl: 404", {"failed": True, "rc": 22, "stdout": "404"}, False)
check("curl: an untrusted certificate", {"failed": True, "rc": 60, "stdout": "000"}, False)
check("curl: a protocol refused", {"failed": True, "rc": 1, "stdout": "000"}, False)
check("curl: no curl", {"failed": True, "rc": 2, "msg": "[Errno 2] No such file or directory: b'curl'",
                        "cmd": "curl"}, False)


def git_failed(cmd, err):
    return {"failed": True, "changed": False, "rc": 128, "cmd": cmd, "msg": err, "stderr": err + " ", "stdout": ""}


LS = "/usr/bin/git ls-remote https://127.0.0.1:18446/x/repo.git -h"
CLONE = "/usr/bin/git clone --origin origin --depth 1 --branch master https://127.0.0.1:18446/x/repo.git /tmp/c"
ACCESS = "fatal: unable to access 'https://127.0.0.1:18446/x/repo.git/': "
CUT = ("Cloning into '/tmp/c'...\nerror: RPC failed; curl 56 GnuTLS recv error (-110): The TLS connection "
       "was non-properly terminated.\nerror: 6302 bytes of body are still expected\nfetch-pack: unexpected "
       "disconnect while reading sideband packet\nfatal: early EOF\nfatal: fetch-pack: invalid index-pack output")
check("git: done", {"changed": True, "before": None, "after": "9ddacf1", "cmd": CLONE}, False)
check("git: dropped before an answer",
      git_failed(LS, ACCESS + "GnuTLS recv error (-110): The TLS connection was non-properly terminated."), True)
check("git: cut short in the pack", git_failed(CLONE, CUT), True)
check("git: reset in the pack",
      git_failed(CLONE, CUT.replace("GnuTLS recv error (-110): The TLS connection was non-properly terminated.",
                                    "Recv failure: Connection reset by peer")), True)
check("git: cut short in the dumb protocol's pack",
      git_failed(CLONE, "Cloning into '/tmp/c'...\nerror: Unable to get pack file https://127.0.0.1:18445/x/"
                        "objects/pack/pack-a0ca.pack\nGnuTLS recv error (-110): The TLS connection was "
                        "non-properly terminated.\nerror: Unable to find 9ddacf1 under https://127.0.0.1:18445/x/"),
      True)
check("git: refused", git_failed(LS, ACCESS.replace("18446", "1") +
      "Failed to connect to 127.0.0.1 port 1 after 0 ms: Couldn't connect to server"), True)
check("git 2.47: refused", git_failed(LS, ACCESS.replace("18446", "1") +
      "Failed to connect to 127.0.0.1 port 1 after 0 ms: Could not connect to server"), True)
check("git: a name not found",
      git_failed(LS, "fatal: unable to access 'https://no-such-host.invalid/x.git/': "
                     "Could not resolve host: no-such-host.invalid"), True)
check("git: under the low-speed limit",
      git_failed(LS, ACCESS + "Operation too slow. Less than 1000 bytes/sec transferred the last 5 seconds"), True)
check("git: 503 at the first request", git_failed(LS, ACCESS + "The requested URL returned error: 503"), True)
check("git: 429 at the first request", git_failed(LS, ACCESS + "The requested URL returned error: 429"), True)
check("git: 503 on the fetch",
      git_failed(CLONE, "Cloning into '/tmp/c'...\nerror: RPC failed; HTTP 503 curl 22 The requested URL "
                        "returned error: 503\nfatal: expected 'packfile'"), True)
check("git: 429 on the fetch",
      git_failed(CLONE, "Cloning into '/tmp/c'...\nerror: RPC failed; HTTP 429 curl 22 The requested URL "
                        "returned error: 429\nfatal: expected 'packfile'"), True)
check("git: no such repository",
      git_failed("/usr/bin/git ls-remote https://127.0.0.1:18445/x/", "fatal: repository 'https://127.0.0.1:18445/x/' not found"),
      False)
check("git 2.43: an untrusted certificate",
      git_failed(LS, ACCESS + "server certificate verification failed. CAfile: none CRLfile: none"), False)
check("git 2.47: an untrusted certificate",
      git_failed(LS, ACCESS + "server verification failed: certificate signer not trusted. "
                              "(CAfile: /etc/ssl/certs/ca-certificates.crt CRLfile: none)"), False)
check("git: a command given as a list", dict(git_failed(LS, ACCESS + "The requested URL returned error: 503"),
                                             cmd=LS.split()), True)

try:
    plugin.retryable("not a result")
except TypeError:
    print("ok   anything but a result is refused")
else:
    print("FAIL anything but a result is refused")
    failures.append("anything but a result is refused")

tests = plugin.TestModule().tests()
if tests.get("retryable") is not plugin.retryable:
    print("FAIL the plugin offers retryable")
    failures.append("the plugin offers retryable")

if failures:
    print("\n%d failed" % len(failures))
    sys.exit(1)
print("\nall passed")
