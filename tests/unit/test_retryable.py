#!/usr/bin/env python3
"""Hold the retryable test plugin to the results downloads really give.

The get_url results are as ansible-core reported them against a local server
that failed each way: 2.16.3 (Ubuntu 24.04's), 2.19.11 (Debian 13's), 2.20.1
(Ubuntu 26.04's), and 2.21.6 each worded them alike, but for a body cut
short, which 2.16 reports only as a checksum that doesn't match. The curl
results are curl 8.5.0's exit codes for the same, with --fail and
--write-out %{http_code}. Needs python3 alone:

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
