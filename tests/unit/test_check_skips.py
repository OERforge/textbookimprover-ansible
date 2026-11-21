#!/usr/bin/env python3
"""tests/check-skips.py on a stderr as tests/run-all.sh writes it, and
every list in tests/skips/ read as patterns."""

import glob
import importlib.util
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.dirname(os.path.dirname(HERE))

spec = importlib.util.spec_from_file_location("check_skips", os.path.join(TOP, "tests", "check-skips.py"))
cs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs)

failures = 0


def check(what, ok):
    global failures
    print(("ok   " if ok else "FAIL ") + what)
    failures += not ok


ERRORS = """\
some suite's own warning
2 check(s) skipped, which passing doesn't cover:
  run-slides-tests.py: skip  LibreOffice not found; saving a deck as PowerPoint needs it
  run-unit-tests.py: skip  not root, or no setpriv
1 suite(s) failed: run-pdf-tests.py
  run-pdf-tests.py: FAIL  something
"""

ALLOWED = """\
# a comment
run-unit-tests\\.py: skip +not root, or no setpriv
3.9: run-slides-tests\\.py: skip +LibreOffice not found
run-cnx-tests\\.py: skip +set CNX_COOKBOOK
"""

skips, suites, count = cs.read_skips(ERRORS)
check("the skip lines are read, and nothing after the list of failures",
      skips == ["run-slides-tests.py: skip  LibreOffice not found; saving a deck as PowerPoint needs it",
                "run-unit-tests.py: skip  not root, or no setpriv"] and suites is None
      and count == 2)

unexpected, unused = cs.check(skips, suites, cs.read_allowed(ALLOWED, "3.14"))
check("a skip no pattern allows is named; a 3.9 pattern doesn't count with another Pandoc",
      unexpected == [skips[0]] and [n for n, _ in unused] == [4])
unexpected, unused = cs.check(skips, suites, cs.read_allowed(ALLOWED, "3.9"))
check("with the stand-in, its patterns count too", unexpected == [] and [n for n, _ in unused] == [4])

skips, suites, count = cs.read_skips("skipped: run-filter-tests.py (pandoc not found)\n")
check("a suite not run is read", skips == [] and suites == "run-filter-tests.py (pandoc not found)")


def run(errors, allowed, pandoc):
    with tempfile.TemporaryDirectory() as folder:
        e, a = os.path.join(folder, "e"), os.path.join(folder, "a")
        open(e, "w").write(errors)
        open(a, "w").write(allowed)
        return cs.main(["check-skips.py", e, a, pandoc])


check("the script fails on a skip not allowed", run(ERRORS, ALLOWED, "3.14") == 1)
check("and passes where every skip is allowed", run(ERRORS, ALLOWED, "3.9") == 0)
check("and fails on a suite not run", run("skipped: run-epub-tests.py (pandoc 3.8 is older than 3.9)\n", ALLOWED, "3.14") == 1)

lists = sorted(glob.glob(os.path.join(TOP, "tests", "skips", "*.txt")))
for path in lists:
    try:
        with open(path, encoding="utf-8") as f:
            patterns = cs.read_allowed(f.read(), "3.9")
        ok = len(patterns) > 0
    except SystemExit:
        ok = False
    check(f"tests/skips/{os.path.basename(path)} is a list of patterns", ok)
check("there are lists for both playbooks", {os.path.basename(p) for p in lists} >= {"user.txt", "developer.txt"})

sys.exit(1 if failures else 0)
