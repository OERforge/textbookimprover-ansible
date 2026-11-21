#!/usr/bin/env python3
"""check-skips.py ERRORS ALLOWED [PANDOC] -- hold a run of TextbookImprover's
suites to the skips a profile allows.

ERRORS is what tests/run-all.sh wrote to stderr: after "N check(s) skipped,
which passing doesn't cover:" a line "  <suite>: skip <text>" for each skip,
and "skipped: ..." for suites it didn't run at all. ALLOWED is a file of
patterns, one a line, each a Python regular expression matched from the
start of "<suite>: skip <text>"; a line beginning "3.9: " applies only when
PANDOC is 3.9, the suites' stand-in; # begins a comment.

Prints each skip no pattern allows, and each pattern no skip matched (a
check that now runs, which is good news, or a pattern gone stale), and
exits 1 on a skip not allowed or a suite not run. Run by tests/scenario.sh.
"""

import re
import sys

HEADER = re.compile(r"^(\d+) check\(s\) skipped, which passing doesn't cover:$")
FAILED = re.compile(r"^\d+ suite\(s\) failed:")


def read_skips(text):
    """The skip lines, each "<suite>: skip <text>", the "skipped:" line's
    suites, or None, and the count of checks skipped run-all.sh gives."""
    skips, suites, inside, count = [], None, False, 0
    for line in text.splitlines():
        if line.startswith("skipped: "):
            suites = line[len("skipped: "):]
        elif HEADER.match(line):
            inside, count = True, int(HEADER.match(line).group(1))
        elif FAILED.match(line):
            inside = False
        elif inside and line.startswith("  "):
            skips.append(line.strip())
        elif inside:
            inside = False
    return skips, suites, count


def read_allowed(text, pandoc):
    patterns = []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("3.9: "):
            if pandoc != "3.9":
                continue
            line = line[len("3.9: "):]
        try:
            patterns.append((number, re.compile(line)))
        except re.error as e:
            raise SystemExit(f"check-skips: line {number} of the allowed skips: {e}")
    return patterns


def check(skips, suites, patterns):
    """The skips no pattern allows, and the patterns no skip matched."""
    unexpected = [s for s in skips if not any(p.match(s) for _, p in patterns)]
    unused = [(n, p.pattern) for n, p in patterns if not any(p.match(s) for s in skips)]
    return unexpected, unused


def main(argv):
    if len(argv) not in (3, 4):
        print(__doc__.split("\n\n")[0], file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8", errors="replace") as f:
        skips, suites, count = read_skips(f.read())
    with open(argv[2], encoding="utf-8") as f:
        patterns = read_allowed(f.read(), argv[3] if len(argv) == 4 else "")
    unexpected, unused = check(skips, suites, patterns)
    print(f"skips: {count} check(s) in {len(skips)} line(s), {len(unexpected)} not allowed")
    for skip in unexpected:
        print(f"  NOT ALLOWED  {skip}")
    for number, pattern in unused:
        print(f"  not seen     line {number}: {pattern}")
    if suites:
        print(f"  NOT RUN      {suites}")
    return 1 if unexpected or suites else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
