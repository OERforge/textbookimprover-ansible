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
- **Node**: 22.22.1 (measured 2026-11-14), so `nodejs` and `npm` come from `apt`.
- **TeX Live** from `apt` is 2025's (measured 2026-11-13), still too old.
- **bubblewrap** 0.11.1, in `main`; the `apparmor` package itself installs `bwrap-userns-restrict` in `/etc/apparmor.d/` (read in the packages, 2026-11-19).

## Debian 13 (trixie)

Measured 2026-11-19 on 13.7, built with `debootstrap --variant=minbase` from `deb.debian.org` (its Release file signed by Debian's archive key), in a container.

- **Release**: `/etc/os-release` says `VERSION_ID="13"`, where `/etc/debian_version` says `13.7`. Ansible's `distribution_version` is the second, `distribution_major_version` the first; bindep's platform atoms use the first (`platform:debian-13`, never `debian-13.7`), and so does the lookup plugin.
- **ansible-core**: 2.19.11, from `apt`.
- **Python**: 3.13.5.
- **Java**: OpenJDK 21 (21.0.12), and 25; not 17 (read). Hence `openjdk-21-jre-headless` in `bindep.txt`.
- **Node**: 20.19.2 with Debian's security updates, so `nodejs` and `npm` come from `apt`.
- **`gpgv`**: not installed with `apt`, which checks the archive with Sequoia's `sqv` on Debian 13; Ubuntu's `apt` still brings `gpgv`. Hence `gpgv [platform:dpkg]` in `bindep.txt`, since the roles check signatures with it.
- **User namespaces**: not restricted by AppArmor as Ubuntu restricts them, by default (read).
- **WSL**: not yet tried (`wsl --install Debian`).

## The Red Hat family, later

Read, not installed, except where it says so.

- **Python packages**: pypdf isn't in EPEL, and EPEL 9's pikepdf is 2.16.1, so those two would come from `pip`.
- **Java** 21 alone on EL 10; **LibreOffice** gone from RHEL 10.
- **Chromium**: 17 libraries missing on Rocky Linux 10.2's base image (measured 2026-11-11), all in BaseOS and AppStream by one report.
- **ansible-core**: 2.22 needs Python 3.13 and 2.21 needs 3.12 (read from PyPI, 2026-11-14), so on EL 9, whose Python is 3.9, a local play needs an older ansible-core or a newer Python.
