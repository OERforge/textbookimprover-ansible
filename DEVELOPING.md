# Developing the collection

Using the playbooks needs nothing installed beforehand: `bootstrap.sh` installs `ansible-core` and `git` with `apt` and does the rest (README, Running it). Changing the collection needs more: the tools its checks run, Docker for the checks in containers, and a few programs `util/update-pins.py` calls. The playbooks install none of these, since TextbookImprover doesn't need them, and its `developer` profile is for working on TextbookImprover, not on the collection.

The commands below are for Ubuntu 24.04 and 26.04 and Debian 13.

## A clone to work in

```bash
git clone https://github.com/OERforge/textbookimprover-ansible.git ~/src/textbookimprover-ansible
```

To run the playbooks from it, use `sh bootstrap.sh --collection ~/src/textbookimprover-ansible`, which runs the clone as it is, or run `ansible-playbook` yourself (README, By hand). Either needs `ansible-core` 2.16 or later; each target's own, from `apt`, is enough.

## The quick checks

`tests/run-all.sh` runs every check whose needs are met and says which it skipped and why (README, Testing). For all of them:

```bash
sudo apt install git python3 python3-venv python3-yaml dash shellcheck
python3 -m venv ~/.local/share/textbookimprover-ansible-dev
~/.local/share/textbookimprover-ansible-dev/bin/pip install ansible-lint==26.11.0 bindep==2.14.0
```

Then, in each terminal you run the checks from:

```bash
. ~/.local/share/textbookimprover-ansible-dev/bin/activate
tests/run-all.sh --no-skip
```

`--no-skip` makes a check that can't run a failure, so the run says what's missing. The venv has to be active, not just on hand: the bindep check imports bindep with whatever `python3` is first on `PATH`.

Why each tool comes from where it does:

- `ansible-lint` and bindep come from PyPI, at the versions CI uses (`.github/workflows/checks.yml`). Ubuntu 24.04's `apt` has `ansible-lint` 6.17.2, much older, and no bindep at all. pip installs the newest `ansible-core` the venv's Python takes along with `ansible-lint`. That's for linting only; the playbooks run with whichever `ansible-playbook` comes first on `PATH`.
- `dash` and ShellCheck come from `apt`. ShellCheck is 0.9.0 on Ubuntu 24.04, 0.10.0 on Debian 13, and 0.11.0 on Ubuntu 26.04, and its releases differ in what they flag: 0.11.0 passed what 0.9.0 flags. CI runs 24.04's, so a script that passes a newer ShellCheck can still fail there.
- PyYAML comes from `apt` for `util/update-pins.py` outside the venv; inside it, `ansible-lint` brings its own.

## The checks in containers

`tests/run-all.sh --containers` runs the `user` playbook in a fresh container of each image, and `--suites` adds TextbookImprover's suites. Both need Docker:

```bash
sudo apt install docker.io
```

Docker's daemon runs as root. A user in the `docker` group can do anything root can on that machine, so either run the scenarios with `sudo`, or add yourself to the group (`sudo usermod -aG docker "$USER"`, then log in again) only on a machine where that's acceptable. Rootless Podman would avoid it, but the scripts call `docker`, and they haven't been tried with Podman.

What a run needs besides:

- **Images**: `ubuntu:24.04` and `ubuntu:26.04` from Docker Hub unless `TI_TEST_IMAGES` names others, and `debian:13` for Debian. Docker Hub limits anonymous pulls, so a pull may be refused for a while after many.
- **Disk**: the `user` playbook with every part, and the suites' output, came to 3.8 GB in one container. With `TI_TEST_PLAYBOOK=developer`, the full TeX Live alone is 4.9 GB, so check `df` before running two side by side.
- **Time**: on two processors, about 40 minutes for the `user` playbook's three runs and the suites with one Pandoc, and about 55 for the `developer` playbook's.

## New pins

`util/update-pins.py` needs PyYAML, and:

- `gpg` and `gpgv`, to check signatures;
- `curl`, for TeX Live's snapshots;
- npm 10 or later, to add a release of Ace. The Node the `browser_checks` role installs has one.

GitHub's API allows few requests an hour without a token. With `GITHUB_TOKEN` set, the script sends the token to GitHub's API and nowhere else. A token that can only read public repositories is enough.
