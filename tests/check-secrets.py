#!/usr/bin/env python3
# Fail if anything git tracks looks like a secret: a file named like a key, a
# vault password, or an inventory; a private key's header in any file; or a
# setting named like a password or token with a plain value. Then check that
# .gitignore and galaxy.yml's build_ignore keep out every name below, since
# ansible-galaxy packs what's in the folder and doesn't read .gitignore.
#
#   python3 tests/check-secrets.py
#
# It first runs on files it plants in a folder of its own, and fails if it
# misses one or flags one it shouldn't, so a change to it can't quietly make it
# pass everything.
import fnmatch
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SELF = os.path.relpath(os.path.abspath(__file__), ROOT)

# Names that are never to be committed or packed, matched against a file's or
# folder's own name. A trailing slash marks a folder.
NAMES = [
    "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*",
    "*.pem", "*.key", "*.p12", "*.pfx",
    ".vault_pass*", "vault_pass*", ".vault-password*", "*.vault-password",
    ".env", ".env.*", "*.token",
    "inventory", "inventory.*", "inventories/", "hosts", "hosts.yml",
    "hosts.yaml", "hosts.ini", "host_vars/", "group_vars/",
]

# A private key's first line, whatever the kind of key. Built from two parts so
# this file doesn't hold it.
KEY_HEADER = re.compile("-----BEGIN [A-Z0-9 ]*" + "PRIVATE KEY-----")

SECRET_NAME = r"[A-Za-z0-9_]*(?:password|passwd|passphrase|become_pass|vault_pass|token|secret|api_?key|access_key)[A-Za-z0-9_]*"
# key: value, in YAML or JSON, the key perhaps quoted.
YAML_SETTING = re.compile(r"""^\s*(?:-\s*)?["']?(?P<key>""" + SECRET_NAME + r""")["']?\s*:\s*(?P<value>.*)$""", re.I)
# key=value, as in an INI inventory or an environment file.
INI_SETTING = re.compile(r"""(?:^|\s)(?P<key>""" + SECRET_NAME + r""")\s*=\s*(?P<value>\S*)""", re.I)

# Content isn't checked in these, which talk about settings rather than set
# them; their names still are.
PROSE = ("*.md", "*.py")


def plain(value):
    """Whether a setting's value is a secret in plain text."""
    value = value.split(" #", 1)[0].strip().strip(",").strip("\"'")
    if value in ("", "~", "null", "None", "{}", "[]"):
        return False
    if value.startswith(("!vault", "$ANSIBLE_VAULT;", "$", "{{")) or "lookup(" in value:
        return False
    if value.endswith(("_file", "_path")):
        return False
    return True


def named(path):
    """The pattern in NAMES that a path, or a folder on it, matches."""
    parts = path.split("/")
    for index, part in enumerate(parts):
        folder = index < len(parts) - 1
        for pattern in NAMES:
            if pattern.endswith("/"):
                if folder and fnmatch.fnmatchcase(part, pattern[:-1]):
                    return pattern
            elif fnmatch.fnmatchcase(part, pattern):
                return pattern
    return None


def scan(root, paths):
    """Each problem found, as "path: what"."""
    problems = []
    for path in paths:
        pattern = named(path)
        if pattern:
            problems.append(f"{path}: its name matches {pattern}")
        full = os.path.join(root, path)
        if path == SELF or not os.path.isfile(full):
            continue
        try:
            with open(full, encoding="utf-8") as handle:
                lines = handle.read().splitlines()
        except UnicodeDecodeError:
            continue
        prose = any(fnmatch.fnmatchcase(os.path.basename(path), p) for p in PROSE)
        for number, line in enumerate(lines, 1):
            if KEY_HEADER.search(line):
                problems.append(f"{path}:{number}: a private key")
            if prose or line.lstrip().startswith(("#", ";")):
                continue
            match = YAML_SETTING.match(line)
            if match and match.group("key").endswith(("_file", "_path")):
                match = None
            if match and plain(match.group("value")):
                problems.append(f"{path}:{number}: {match.group('key')} has a value in plain text")
                continue
            for match in INI_SETTING.finditer(line):
                if not match.group("key").endswith(("_file", "_path")) and plain(match.group("value")):
                    problems.append(f"{path}:{number}: {match.group('key')} has a value in plain text")
    return problems


# What the self-test plants: each path, its content, and whether it's to be
# flagged. Secrets are written in pieces so this file holds none whole.
PW = "pass" + "word"
PLANTED = [
    ("deploy/id_ed25519", "x\n", True),
    (".vault_pass", "x\n", True),
    ("certs/site.key", "x\n", True),
    ("inventory.ini", "localhost\n", True),
    ("playbooks/group_vars/all.yml", "ti_user: me\n", True),
    ("notes.txt", "-----BEGIN OPENSSH " + "PRIVATE KEY-----\n", True),
    ("vars/plain.yml", f"ansible_become_{PW}: hunter2\n", True),
    ("vars/token.yml", "github_token: \"ghp_abc\"\n", True),
    ("test.ini", f"[all]\nbox ansible_{PW}=hunter2\n", True),
    ("vars/vault.yml", f"ansible_become_{PW}: !vault |\n  $ANSIBLE_VAULT;1.1;AES256\n  6162\n", False),
    ("vars/lookup.yml", f"api_token: \"{{{{ lookup('env', 'API_TOKEN') }}}}\"\n", False),
    ("vars/empty.yml", f"db_{PW}:\nssh_private_key_file: ~/.ssh/id\n", False),
    ("run.sh", "TOKEN=$(cat file)\n", False),
    ("README.md", f"Set ansible_become_{PW}: hunter2 in a vault.\n", False),
    ("roles/x/tasks/main.yml", "- name: Use the token\n  debug: msg=hi\n", False),
]


def self_test():
    failures = []
    with tempfile.TemporaryDirectory() as root:
        for path, content, _ in PLANTED:
            os.makedirs(os.path.dirname(os.path.join(root, path)), exist_ok=True)
            with open(os.path.join(root, path), "w", encoding="utf-8") as handle:
                handle.write(content)
        for path, _, flagged in PLANTED:
            found = scan(root, [path])
            if bool(found) != flagged:
                failures.append(f"{path}: {'missed' if flagged else 'flagged: ' + '; '.join(found)}")
    return failures


def ignore_lists():
    """What .gitignore and build_ignore leave out of NAMES."""
    missing = []
    with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as handle:
        gitignore = {line.strip() for line in handle}
    with open(os.path.join(ROOT, "galaxy.yml"), encoding="utf-8") as handle:
        galaxy = handle.read()
    build_ignore = set(re.findall(r"""^\s*-\s*["']?([^"'\n]+?)["']?\s*$""",
                                  galaxy.split("build_ignore:", 1)[1], re.M))
    for pattern in NAMES:
        if pattern not in gitignore:
            missing.append(f".gitignore lacks {pattern}")
        bare = pattern.rstrip("/")
        for wanted in (bare, "*/" + bare):
            if wanted not in build_ignore:
                missing.append(f"galaxy.yml's build_ignore lacks {wanted}")
    return missing


def main():
    status = 0
    for label, problems in (
            ("the check finds what it plants, and only that", self_test()),
            (".gitignore and build_ignore keep out every name", ignore_lists()),
            ("nothing git tracks looks like a secret",
             scan(ROOT, subprocess.run(["git", "-C", ROOT, "ls-files"], check=True,
                                       capture_output=True, text=True).stdout.splitlines()))):
        print(("ok  " if not problems else "FAIL") + " " + label)
        for problem in problems:
            print("     " + problem)
        status |= bool(problems)
    return status


if __name__ == "__main__":
    sys.exit(main())
