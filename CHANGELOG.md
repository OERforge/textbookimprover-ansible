# Changelog

What changed, newest first, as [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) has it.

## [Unreleased]

### Added

- **The `user` playbook's first four roles.** `base` stops on a platform the collection isn't tested on, installs the system packages every profile needs with `apt` (the only step that needs `sudo`), and makes the user's folders and puts `~/.local/bin` first on the shell's `PATH`. `python` checks that the Python is 3.9 or later and that each module a run imports is there. `pandoc` installs each release in `pandoc_versions` from its tarball into `~/.local/opt/`, checked against a pinned SHA-256, and links them into `~/.local/bin`. `textbookimprover` clones a release at its tag and checks that the tag names the commit pinned for it, or clones a branch, tag, or commit with `ti_source: git`, and sets `T`. Every task that writes in the user's home is tagged `user`, so `--tags user` updates without a password.
- **`bindep.txt`** lists every system package by platform and profile, and **the lookup plugin `oerforge.textbookimprover.bindep`** chooses from it as bindep does, from the host's facts, so nothing is installed on the host to decide what to install. Against bindep 2.14.0 it chose the same packages for every one or two of the six profiles on four platforms, from this file, from bindep's own test file, and from a set of rules using every kind of selector, and made the same platform atoms from Ansible's facts as bindep made on Ubuntu 24.04 and 26.04.
- **Tests**: `tests/run-scenarios.sh` and `tests/scenario.sh` run the playbook in a fresh container as an ordinary user, twice, then the user step with `sudo` taken away; `tests/unit/test_bindep.py` holds the lookup plugin to bindep.
- **Secrets kept out.** `.gitignore` and `galaxy.yml`'s `build_ignore` both leave out keys, vault passwords, tokens, `.env` files, and inventories with their `host_vars` and `group_vars`, since `ansible-galaxy` packs whatever is in the folder and doesn't read `.gitignore`. `tests/check-secrets.py` fails on any such file git tracks, on a private key in any file, and on a setting named like a password or token whose value is neither vault-encrypted nor a lookup, and checks that the two lists agree with it.
- **`notes/PLATFORMS.md`**, what's known about each distribution.
