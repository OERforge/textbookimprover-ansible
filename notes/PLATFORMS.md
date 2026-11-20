# Platforms

What's known about each distribution the collection supports or may support, and how each fact is known: "measured" means run on that release, in a container built from its own package archive, on the date given; "read" means taken from a page or a package index and not tried.

## Ubuntu 24.04 LTS (noble)

- **ansible-core** from `apt`: 2.16.3, which ran the `user` playbook (measured 2026-11-19). It's the oldest ansible-core the collection is tested with, so `meta/runtime.yml` asks for 2.16 or later.
- **Python**: 3.12.3, with `python3-yaml`, `python3-html5lib`, `python3-lxml`, `python3-pypdf`, and `python3-pil` from `apt` importing (measured 2026-11-19). The Python packages are in `universe`.
- **bindep's platform atoms** (`ubuntu`, `ubuntu-noble`, `ubuntu-24`, `ubuntu-24.04`, `dpkg`, `base-py3`) are the lookup plugin's from Ansible's facts (measured 2026-11-19, bindep 2.14.0).
- **Java**: OpenJDK 17, 21, and 25 (measured 2026-11-13).
- **Node**: 18.19.1, too old for Ace, which needs 20 (measured 2026-11-14).
- **Pandoc** from `apt` is 3.1.3, which TextbookImprover refuses; the collection installs Pandoc's own releases.
- **TeX Live** from `apt` is 2023's; TextbookImprover needs LaTeX 2026-06-01 or later, so the collection installs TinyTeX or TeX Live itself.
- **bubblewrap** 0.9.0, in `main`. Its AppArmor profile, `bwrap-userns-restrict`, is an extra profile in `apparmor-profiles`, under `/usr/share/apparmor/extra-profiles/`, which nothing loads until it's copied into `/etc/apparmor.d/` (read in the packages, 2026-11-19).

## Ubuntu 26.04 LTS (resolute)

- **ansible-core** from `apt`: 2.20.1, which ran the `user` playbook (measured 2026-11-19).
- **Python**: 3.14.4, with the same five packages from `apt` importing (measured 2026-11-19). ansible-core 2.20.1 warns when it has to discover the Python itself, so the playbooks name `/usr/bin/python3`.
- **bindep's platform atoms** (`ubuntu`, `ubuntu-resolute`, `ubuntu-26`, `ubuntu-26.04`, `dpkg`, `base-py3`) are the lookup plugin's from Ansible's facts (measured 2026-11-19, bindep 2.14.0).
- **Java**: OpenJDK 17, 21, and 25 (measured 2026-11-13).
- **Node**: 22.22.1, but `npm` 9.2.0, older than the 10 Ace asks for, and `apt install nodejs npm` would install 382 packages (measured 2026-11-20). So Node comes from its own release, as on 24.04.
- **TeX Live** from `apt` is 2025's (measured 2026-11-13), still too old.
- **bubblewrap** 0.11.1, in `main`; the `apparmor` package itself installs `bwrap-userns-restrict` in `/etc/apparmor.d/` (read in the packages, 2026-11-19).

## Debian 13 (trixie)

Measured 2026-11-19 on 13.7, built with `debootstrap --variant=minbase` from `deb.debian.org` (its Release file signed by Debian's archive key), in a container.

- **Release**: `/etc/os-release` says `VERSION_ID="13"`, where `/etc/debian_version` says `13.7`. Ansible's `distribution_version` is the second, `distribution_major_version` the first; bindep's platform atoms use the first (`platform:debian-13`, never `debian-13.7`), and so does the lookup plugin.
- **ansible-core**: 2.19.11, from `apt`.
- **Python**: 3.13.5.
- **Java**: OpenJDK 21 (21.0.12), and 25; not 17 (read). Hence `openjdk-21-jre-headless` in `bindep.txt`.
- **Node**: 20.19.2 with Debian's security updates, but `npm` 9.2.0, and `apt install nodejs npm` would install 382 packages (measured 2026-11-20). So Node comes from its own release.
- **`gpgv`**: not installed with `apt`, which checks the archive with Sequoia's `sqv` on Debian 13; Ubuntu's `apt` still brings `gpgv`. Hence `gpgv [platform:dpkg]` in `bindep.txt`, since the roles check signatures with it.
- **User namespaces**: not restricted by AppArmor as Ubuntu restricts them, by default (read).
- **WSL**: not yet tried (`wsl --install Debian`).

## The browser checks, on all three

Measured 2026-11-20 with Playwright 1.65.2 and its headless Chromium 159.0.8154.6, in containers of each release.

- **Playwright's driver** is a Node binary of its own, which needs `libatomic1`; a minimal image lacks it, and nothing starts without it ("libatomic.so.1: cannot open shared object file").
- **Playwright's platform names**: `ubuntu24.04-x64`, `ubuntu26.04-x64`, and `debian13-x64`, each officially supported by 1.65.2. Its lists of packages for the headless Chromium are the same on the three, but that Debian's has no `xfonts-cyrillic`; `bindep.txt` has them, less Xvfb, which only a browser with a window uses.
- **Chromium's sandbox**: in a container under Docker's default seccomp profile, neither Chromium's sandbox nor the check's own namespaces start ("unshare: Operation not permitted"), and `--wcag` says so and goes on; with `--security-opt seccomp=unconfined --security-opt apparmor=unconfined`, on 24.04, both started. Not yet tried on a machine running Ubuntu itself, where AppArmor restricts unprivileged user namespaces.

## The developer playbook, on all three

Measured 2026-11-20 in containers of each release.

- **LibreOffice** from `apt`'s `libreoffice-impress`: 24.2.7.2 on Ubuntu 24.04, 26.2.6.3 on 26.04, and 25.2.3.2 on Debian 13.
- **fontTools and python-docx** from `apt` on all three, under their `python3-` names.
- **Python 3.9.25** from uv 0.13.9, the same build on all three, since uv brings its own.
- **TeX Live's mirror**: CTAN's mirror service (`mirror.ctan.org`) sends each request to a mirror near the asker, a different one from one request to the next, so a network that allows only named hosts needs `tex_repository` set to one it allows.
- **TextbookImprover's suites** at `main` (459273a) on 26.04 with the full TeX Live: all passed, with one skip, `setpriv` as root, which only a run as root can check.

## The Red Hat family, later

Read, not installed, except where it says so.

- **Python packages**: pypdf isn't in EPEL, and EPEL 9's pikepdf is 2.16.1, so those two would come from `pip`.
- **Java** 21 alone on EL 10; **LibreOffice** gone from RHEL 10.
- **Chromium**: 17 libraries missing on Rocky Linux 10.2's base image (measured 2026-11-11), all in BaseOS and AppStream by one report.
- **ansible-core**: 2.22 needs Python 3.13 and 2.21 needs 3.12 (read from PyPI, 2026-11-14), so on EL 9, whose Python is 3.9, a local play needs an older ansible-core or a newer Python.
