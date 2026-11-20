#!/usr/bin/env python3
"""Hold the bindep lookup plugin to bindep's own answers.

Needs ansible-core and bindep importable. With a file of a host's facts
(`ansible localhost -m setup` written as JSON), also checks that the plugin
makes the same platform atoms from them as bindep makes on that host:

    python3 tests/unit/test_bindep.py [facts.json]
"""

import importlib.util
import itertools
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

spec = importlib.util.spec_from_file_location(
    "bindep_lookup", os.path.join(ROOT, "plugins", "lookup", "bindep.py"))
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)

from bindep import depends  # noqa: E402

failures = []


def check(what, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        failures.append(what)
        if detail:
            print("     " + detail)


def bindep_names(text, profiles):
    return [rule[0] for rule in depends.Depends(text).active_rules(profiles)]


PLATFORMS = {
    "Ubuntu 24.04": {"ubuntu", "ubuntu-noble", "ubuntu-24", "ubuntu-24.04", "dpkg", "base-py3"},
    "Ubuntu 26.04": {"ubuntu", "ubuntu-resolute", "ubuntu-26", "ubuntu-26.04", "dpkg", "base-py3"},
    "Debian 13": {"debian", "debian-trixie", "debian-13", "dpkg", "base-py3"},
    "Rocky 10.2": {"rocky", "rocky-red", "rocky-10", "rocky-10.2", "rpm", "redhat", "base-py3"},
}
PROFILES = ["default", "pdf", "validators", "browser", "slides", "test"]

# Rules that use every kind of selector, since neither file has a negation
# or a group that matches on the platforms above.
SELECTORS = """\
plain
neg-platform [!platform:dpkg]
neg-profile [!pdf]
pos-and-neg [platform:dpkg !platform:ubuntu-24.04]
platform-and-profile [platform:rpm test]
group [(platform:dpkg pdf)]
group-with-neg [(platform:ubuntu !test)]
two-groups [(platform:ubuntu pdf) (platform:debian test)]
group-and-profile [(platform:ubuntu-26 pdf) validators]
versioned >=1.0
versioned-selector [pdf] >=2.0,<3.0
commented [browser]  # a comment
"""

def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


texts = {"the collection's bindep.txt": read(os.path.join(ROOT, "bindep.txt")),
         "rules with every kind of selector": SELECTORS}
fixture = os.path.join(os.path.dirname(depends.__file__), "tests", "bindep.txt")
if os.path.exists(fixture):
    texts["bindep's own test file"] = read(fixture)

for label, text in texts.items():
    rules = plugin.parse(text, label)
    check(f"{label}: as many rules as bindep reads",
          len(rules) == len(depends.Depends(text)._rules))
    wrong = []
    for platform, atoms in PLATFORMS.items():
        for count in range(0, 3):
            for chosen in itertools.combinations(PROFILES, count):
                profiles = set(chosen) | {"platform:" + atom for atom in atoms}
                ours = plugin.active(rules, profiles)
                theirs = bindep_names(text, profiles)
                if ours != theirs:
                    wrong.append(f"{platform} {sorted(chosen)}: {ours} against {theirs}")
    check(f"{label}: the same packages as bindep on four platforms, "
          f"for every one or two of {len(PROFILES)} profiles", not wrong,
          "; ".join(wrong[:3]))

# A host's facts, as Ansible gathered them, and the atoms bindep made on that
# host, both measured.
MEASURED = {
    "Debian 13.7": (
        {"distribution": "Debian", "distribution_release": "trixie",
         "distribution_version": "13.7", "distribution_major_version": "13"},
        {"debian", "debian-trixie", "debian-13", "dpkg", "base-py3"}),
}
for label, (facts, theirs) in MEASURED.items():
    ours = plugin.platform_atoms(facts)
    theirs = {"platform:" + atom for atom in theirs}
    check(f"{label}'s platform atoms from its facts are bindep's there", ours == theirs,
          f"ours only: {sorted(ours - theirs)}; bindep's only: {sorted(theirs - ours)}")

if len(sys.argv) > 1:
    with open(sys.argv[1], encoding="utf-8") as handle:
        data = json.load(handle)
    facts = data.get("ansible_facts", data)
    facts = {key[len("ansible_"):] if key.startswith("ansible_") else key: value
             for key, value in facts.items()}
    ours = plugin.platform_atoms(facts)
    theirs = set(depends.Depends("").platform_profiles())
    check(f"this host's platform atoms from Ansible's facts are bindep's "
          f"({facts.get('distribution')} {facts.get('distribution_version')})",
          ours == theirs, f"ours only: {sorted(ours - theirs)}; bindep's only: {sorted(theirs - ours)}")

print(f"{len(failures)} failed" if failures else "all checks passed")
sys.exit(1 if failures else 0)
