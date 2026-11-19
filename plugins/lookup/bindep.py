# MIT License; see LICENSE at the top of the collection.

DOCUMENTATION = r"""
name: bindep
author: TextbookImprover's contributors
short_description: The system packages bindep.txt names for a host
description:
  - Reads the collection's C(bindep.txt) and returns the packages whose
    selectors match the host's platform and the profiles given, as bindep
    itself would choose them.
  - Evaluated where Ansible runs, from the host's facts, so nothing has to be
    installed on the host to decide what to install there.
  - Version constraints in C(bindep.txt) are read and ignored.
options:
  _terms:
    description: Not used.
    required: false
  profiles:
    description: The profiles to choose, as bindep's own command line takes them.
    type: list
    elements: str
    default: [default]
  file:
    description: A C(bindep.txt) other than the collection's own.
    type: path
"""

EXAMPLES = r"""
- name: Install what converting a book needs
  ansible.builtin.apt:
    name: "{{ query('oerforge.textbookimprover.bindep', profiles=['default']) }}"
"""

RETURN = r"""
_raw:
  description: The packages, in the order the file lists them.
  type: list
  elements: str
"""

import os
import re

from ansible.errors import AnsibleLookupError
from ansible.plugins.lookup import LookupBase

# A rule is a name, then an optional selector in brackets, then optional
# version constraints, as bindep's grammar has them (bindep/depends.py).
RULE = re.compile(
    r"^(?P<name>[A-Za-z0-9/][A-Za-z0-9.+\-_/]+)"
    r"(?:[ ]+\[(?P<selector>[^\]]*)\])?"
    r"(?:[ ]+(?P<version>(?:<=|<|!=|==|>=|>)[^ #]+))?"
    r"[ ]*(?:#.*)?$")
PROFILE = re.compile(r"^(!?)([a-z0-9:.\-]+)$")
TOKEN = re.compile(r"\(([^()]*)\)|([^\s()]+)")

# bindep's truth table for a platform vote against a profile vote: False is
# a definite no, True a definite yes, None no selector of that kind.
INCLUDE = {
    (False, False): False, (False, None): False, (False, True): False,
    (None, False): False, (None, None): True, (None, True): True,
    (True, False): False, (True, None): True, (True, True): True,
}

DPKG = ("debian", "ubuntu", "pop")
RPM = ("amzn", "centos", "rhel", "fedora", "ol", "oracle", "rocky", "almalinux")


def parse_profile(text, where):
    match = PROFILE.match(text)
    if not match:
        raise AnsibleLookupError(f"{where}: {text!r} isn't a profile or a platform")
    return (match.group(1) != "!", match.group(2))


def parse(text, where="bindep.txt"):
    """The rules: (name, selector), each selector a list of (sense, profile)
    pairs and lists of them, the lists being bindep's parenthesized groups."""
    rules = []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = RULE.match(line)
        if not match:
            raise AnsibleLookupError(f"{where}, line {number}: can't read {line!r}")
        selector = []
        for group, single in TOKEN.findall(match.group("selector") or ""):
            if single:
                selector.append(parse_profile(single, f"{where}, line {number}"))
            else:
                selector.append([parse_profile(item, f"{where}, line {number}")
                                 for item in group.split()])
        rules.append((match.group("name"), selector))
    return rules


def platform_atoms(facts):
    """The platform profiles bindep makes for a host, from Ansible's facts
    (bindep's Depends.platform_profiles, for the families it names)."""
    distro_id = "".join((facts.get("distribution") or "").split()).lower()
    codename = (facts.get("distribution_release") or "").lower()
    release = (facts.get("distribution_version") or "").lower()
    atoms = {distro_id}
    bits = codename.split()
    for count in range(1, len(bits) + 1):
        atoms.add(distro_id + "-" + "-".join(bits[:count]))
    bits = release.split(".") if release else []
    for count in range(1, len(bits) + 1):
        atoms.add(distro_id + "-" + ".".join(bits[:count]))
    if distro_id in DPKG:
        atoms.update(("dpkg", "base-py3"))
    elif distro_id in RPM:
        atoms.update(("rpm", "redhat", "base-py3"))
    return {"platform:" + atom for atom in atoms}


def _match_all(group, profiles):
    return all((name in profiles) == sense for sense, name in group)


def _evaluate(partition, profiles):
    """bindep's Depends._evaluate: True, False, or None for no selectors."""
    if not partition:
        return None
    positive = match_found = group_found = group_match_found = False
    for item in partition:
        if isinstance(item, list):
            group_found = True
            if _match_all(item, profiles):
                group_match_found = True
            continue
        sense, name = item
        if sense:
            positive = True
            if name in profiles:
                match_found = True
        elif name in profiles:
            return False
    if group_match_found or match_found:
        return True
    return not group_found and not positive


def active(rules, profiles):
    """The names of the rules that apply, as bindep's Depends.active_rules."""
    profiles = set(profiles)
    names = []
    for name, selector in rules:
        platform, user = [], []
        for item in selector:
            if not isinstance(item, list) and item[1].startswith("platform:"):
                platform.append(item)
            else:
                user.append(item)
        if INCLUDE[_evaluate(platform, profiles), _evaluate(user, profiles)]:
            names.append(name)
    return names


class LookupModule(LookupBase):

    def run(self, terms, variables=None, **kwargs):
        self.set_options(var_options=variables, direct=kwargs)
        path = self.get_option("file") or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "bindep.txt")
        try:
            with open(path, encoding="utf-8") as handle:
                rules = parse(handle.read(), path)
        except OSError as error:
            raise AnsibleLookupError(f"can't read {path}: {error}")
        facts = (variables or {}).get("ansible_facts") or {}
        if not facts.get("distribution"):
            raise AnsibleLookupError("no facts for this host: gather them first")
        profiles = set(self.get_option("profiles")) | platform_atoms(facts)
        return active(rules, profiles)
