# textbookimprover-ansible

Ansible playbooks that set up a machine to use or develop [TextbookImprover](https://github.com/OERforge/textbookimprover): Pandoc, TextbookImprover itself, LuaLaTeX for tagged PDFs, the validators, the browser checks, and the rest of what its [installation page](https://github.com/OERforge/textbookimprover/blob/main/docs/installation.md) asks for.

**Only part of it works yet.** The `user` playbook installs the system packages a book's conversion needs, checks the Python, and installs Pandoc, TeX for a PDF target, the validators, the browser checks, TextbookImprover, and, when asked, the fonts for OpenStax's books; a `developer` playbook adds what working on TextbookImprover needs; and `bootstrap.sh` runs either of them with one command.

Licensed MIT. See `LICENSE`.

## What it does

- **Follows TextbookImprover's installation page**, which stays the one description of what TextbookImprover needs. Where the playbooks find the page wrong or incomplete, the fix goes into the page.
- **Runs on Ubuntu 24.04 LTS, Ubuntu 26.04 LTS, and Debian 13**, on a machine of their own or under WSL 2, x86_64 first. Elsewhere a play stops at once and lists what's supported. Other distributions come later, so no package's name is in a task: they're in `bindep.txt`, by platform and profile.
- **Installs into one user's home folder**, so that updating needs no `sudo`. System packages come from `apt`, and that step alone asks for a password.
- **Checks every download before it's used.** Each is a release by default, checked against a SHA-256 written into the collection in advance (`roles/*/vars/pins.yml`), or against its publisher's signature where it can't be pinned. A TextbookImprover release is a clone at its tag, checked against the commit pinned for it. TeX's packages are checked by `tlmgr` against TeX Live's signature, and the play fails if it says it couldn't check them.
- **Offers profiles**: `user`, for converting books, and `developer`, for working on TextbookImprover. Either way, TextbookImprover's own test suites are the check that the machine is set up right.

It's an Ansible collection, `oerforge.textbookimprover`, using only the modules that come with ansible-core, 2.16 or later.

## Running it

On the machine to set up, in a terminal, as the person who'll use TextbookImprover:

```bash
curl -fsSLO https://raw.githubusercontent.com/OERforge/textbookimprover-ansible/main/bootstrap.sh
sh bootstrap.sh
```

It asks which setup the machine is for, `user` (converting books) or `developer` (working on TextbookImprover), and which optional parts to install: TeX for PDF output, the validators, the browser checks, and the fonts for OpenStax's books. Then it asks for your `sudo` password, once, installs `ansible-core` and `git` with `apt` if they're missing, fetches the collection, and runs the playbook on the machine, which can take a while the first time. Open a new terminal afterward ([The shell's settings](#the-shells-settings), below). If the download stops partway, `curl` says so, and the part it got does nothing when run: the shell reads the whole script before it runs any of it. That's so with `curl … | sh` too.

Run it again to update everything. `sh bootstrap.sh --user-only` updates what's in your home folder without asking for a password, `--reconfigure` asks the questions again, `--profile` chooses the setup without asking (saved with the answers on the first run or with `--reconfigure`), and options after `--` go to `ansible-playbook`, so `sh bootstrap.sh -- -e tex_update=true` checks TeX against its snapshot again. TeX's packages move on when the collection's date for them does (`tex_snapshot`, below). `--help` lists the rest. What it keeps, and where:

- **Its answers**, as an inventory in `~/.config/textbookimprover-ansible/inventory/`: the profile in `~/.config/textbookimprover-ansible/profile` and the other answers in the inventory's `group_vars/all/bootstrap.yml`, which `--reconfigure` rewrites. Settings of your own (Settings, below) go in its `host_vars/localhost.yml`, which win over the answers, and which `bootstrap.sh` makes once and never changes.
- **The collection**, as a clone in `~/.local/share/textbookimprover-ansible/ansible_collections/oerforge/textbookimprover/`, which each run updates, and which it refuses to touch if you've changed anything in it. It runs the playbooks from there and from nowhere else, so a copy of the collection installed elsewhere isn't used; `--collection` names a copy of your own to use as it is. Until the collection has a release, `bootstrap.sh` uses its `main` branch, with nothing to check it against; after, it'll use the newest release it knows and check that the release's tag names the commit it expects, as the `textbookimprover` role does for TextbookImprover.

### By hand

Without `bootstrap.sh`, on the machine to set up:

```bash
sudo apt install ansible-core git
git clone https://github.com/OERforge/textbookimprover-ansible.git ~/src/textbookimprover-ansible
mkdir -p ~/.ansible/collections/ansible_collections/oerforge
ln -s ~/src/textbookimprover-ansible ~/.ansible/collections/ansible_collections/oerforge/textbookimprover
ansible-playbook -i localhost, -c local -K oerforge.textbookimprover.user
```

`-K` asks for your `sudo` password, which only the system packages need. Without a PDF target in mind, `-e ti_tex=false` leaves TeX out; `-e ti_validators=false` leaves out the validators, and `-e ti_browser_checks=false` the browser checks. To update later without a password, run the user step alone:

```bash
ansible-playbook -i localhost, -c local oerforge.textbookimprover.user --tags user
```

### The shell's settings

Open a new terminal after the play: it adds blocks to `~/.bashrc` putting `~/.local/bin` and TeX's commands on your `PATH`, setting `T` to TextbookImprover's folder, and setting `EPUBCHECK_JAR`, `VNU_JAR`, `VERAPDF`, and `VERAPDF_WCAG` to the validators, and putting the browser checks' virtual environment first on your `PATH`, so that `python3` is its Python, as the installation page's examples expect.

The blocks go at the end of `~/.bashrc`, so in a new terminal they take the place of any settings of your own made earlier in it: if you've already set up TextbookImprover by hand, with a virtual environment you activate or `VERAPDF` pointing at a veraPDF of your own, the play's copies are the ones a new terminal finds. Nothing of yours is removed, and activating your own environment afterward still puts it first. To try the playbooks without that, run them as another user made for the purpose.

To keep your own settings in force, put the play's in a file of their own: set `ti_shell_rc` in your `host_vars` (for `bootstrap.sh`, `~/.config/textbookimprover-ansible/inventory/host_vars/localhost.yml`), for example `ti_shell_rc: "{{ ti_home }}/.config/textbookimprover-ansible/shell.sh"`, and run the play again. It takes its blocks out of `~/.bashrc`, leaving your lines there as they are, and writes them in that file instead; `. ~/.config/textbookimprover-ansible/shell.sh` in a terminal then gives that terminal the play's settings. The blocks are plain `sh`, so the file can be sourced from either shell. Taking the setting out moves them back. The play notes the file it used in `~/.config/textbookimprover-ansible/shell-file`, and `bootstrap.sh`'s last lines name it.

### For working on TextbookImprover

The `developer` playbook installs everything the `user` playbook does, with these differences:

- TextbookImprover is a clone of `main` in `~/tools/textbookimprover/`, which the play makes once and never updates or touches afterward, since it's yours to work in.
- TeX is the full TeX Live, which has the languages TinyTeX lacks.
- Every Pandoc the collection pins is installed side by side, the newest as `pandoc`.
- LibreOffice Impress comes from `apt`.
- The test suites' Python packages (fontTools, python-docx) come from `apt`.
- Python 3.9, which the portability suite compiles with, is installed by uv and linked as `~/.local/bin/python3.9`.
- OpenStax's cookbook is cloned at the commit TextbookImprover's CNX ports were made from, named by `CNX_COOKBOOK`, which turns on the CNX suite's comparisons with it.

It's `bootstrap.sh`'s second choice, or by hand:

```bash
ansible-playbook -i localhost, -c local -K oerforge.textbookimprover.developer
```

Each of these is a default of the `developer` profile, which any setting changes (below): `tex_distribution: tinytex`, `pandoc_versions: ["3.14"]`, `ti_libreoffice: false`, `developer_python39: false`, or `developer_cookbook: false`.

### Settings

Every setting can go in an inventory, so that a machine's choices are kept in a file, and `-e` changes any of them for one run. `bootstrap.sh` makes one, whose `host_vars/localhost.yml` is for settings of your own. By hand, an inventory for the machine itself, kept wherever you like, but outside the collection's folder:

```yaml
# ~/textbookimprover-machine.yml
all:
  hosts:
    localhost:
      ansible_connection: local
      ti_libreoffice: true
      pandoc_versions: ["3.14", "3.13"]
      tex_extra_packages: [babel-german, hyphen-german]
```

```bash
ansible-playbook -i ~/textbookimprover-machine.yml -K oerforge.textbookimprover.user
```

The same settings can go in a `host_vars/localhost.yml` beside an inventory file in a folder of its own, given with `-i` as the folder. The roles' defaults come first, then the inventory's settings (`group_vars` before `host_vars`, as Ansible always takes them), then `-e`. Each playbook sets one thing itself, `ti_profile` (`user` or `developer`), which the defaults follow, so the two playbooks differ only in their defaults and in the `developer` role.

The switches for the optional parts, each `true` or `false`:

- `ti_tex`, `ti_validators`, and `ti_browser_checks`: on in both profiles.
- `ti_libreoffice`: on in `developer`, off in `user`.
- `ti_fonts`: off in both. The fonts for OpenStax's books, which no other book needs: Noto Sans Math, and TeX Live's Noto Emoji.
- `verapdf_wcag`, `browser_checks_ace`, `browser_checks_venv_on_path`, `developer_python39`, and `developer_cookbook`: the parts of a role, each on by default.

A download that fails in a way that may pass (no answer, the connection lost, the body cut short, or an answer of 408, 429, or a server's error) is tried again `ti_download_retries` times (3 by default), `ti_download_delay` seconds apart (10), and checked again each time; `0` tries each once. A checksum that doesn't match is tried again too, since ansible-core 2.16, Ubuntu 24.04's, reports a body cut short only that way, so a file that's really wrong stops the play at the last try, with the checksum's message. veraPDF's WCAG modules, from Maven Central, whose "too many requests" can last minutes, are tried at least six times, twenty seconds apart. Anything else, a refused or untrusted certificate or a 404 among them, stops the play at once. The `git` clones of TextbookImprover and the cookbook are tried again in the same way, and a clone that stalls, under 1,000 bytes a second for a minute, fails and is tried again rather than waiting forever.

Inventories, like keys and passwords, are kept out of the collection's commits and builds (Testing, below), so one put in the collection's folder by mistake isn't committed.

### What goes where

- Pandoc's releases in `~/.local/opt/pandoc-<version>/`, linked as `~/.local/bin/pandoc-<version>`, the first of `pandoc_versions` as `~/.local/bin/pandoc` too. Several can sit side by side: `-e '{"pandoc_versions": ["3.14", "3.13"]}'`.
- TextbookImprover in `~/tools/textbookimprover-<release>/`, or `~/tools/textbookimprover/` for a clone of `main` (`ti_source: git`, the `developer` profile's default). `ti_dir` puts it elsewhere, and `ti_version` names the release, or the branch, tag, or commit for `git`.
- TeX: TinyTeX in `~/.TinyTeX/`, as the installation page has it, with the page's packages added (`tex_extra_packages` adds more). Or, with `tex_distribution: texlive` (the `developer` profile's default), TeX Live from its own installer in `~/.local/opt/texlive/2026/`, the full scheme by default (`texlive_scheme`), which has every package but takes several gigabytes; without its documentation and sources, as the role installs it, it took 17 minutes here. A TinyTeX already there is kept, so `tinytex_version` says only which bundle a new one starts from.
- TeX's packages are one day's, from that day's snapshot of TeX Live's repository, which [texlive.info](https://texlive.info/tlnet-archive/) keeps: `tex_snapshot`, a date (2026-11-20 by default) whose snapshot's database the collection pins by its SHA-512, checked against TeX Live's signature, so that a package released since changes nothing until the date is moved. `util/update-pins.py add tex_snapshot <date>` pins another, and `ti_pins.tex_snapshot` gives one in the inventory. Each run brings TeX to the date, and a TeX already there is left alone with no request made:
  - **Forward**, `tlmgr` updates every package from the new date's snapshot.
  - **Back**, `tlmgr` never takes a package back with an update, and won't read a repository older than the TeX at all (it judges by `texlive-scripts`, which changes almost every day, so a TeX even a day newer is refused). Where it does read the snapshot, the packages it would keep newer are installed again from it with `tlmgr install --reinstall`. Where it doesn't, the role installs the whole TeX again from the snapshot, if the role installed it: TinyTeX's bundle in a few minutes, or the full TeX Live's several gigabytes in a quarter of an hour. The TeX there is renamed `<folder>.previous` until the new one is installed, and put back if that fails, so there has to be room for both meanwhile. A run stopped partway is finished by the next: if the new TeX's packages were all in (the role's mark of the date says so), the old one is removed, and if not, what there is of the new one is removed and the old one put back. `<folder>.previous` is the role's own, so leave it be. Packages added by hand with `tlmgr` go with the old TeX, so name them in `tex_extra_packages`. A TeX the role didn't install stops the run instead, saying what to do.
  - `-e tex_update=true` compares TeX with the snapshot again, for a package changed by hand since.
- `tex_held_packages` holds a package at a date of its own, as `ltx-talk: "2026-11-19"`: a way back from a release that breaks something while the rest moves on. After the rest, the role reads that day's database itself, checked against its pin and TeX Live's signature, checks the package's container (and its `x86_64-linux` one, if it has one) against the database's SHA-512, since `tlmgr install --file` doesn't, and installs it; every update leaves it out. The date needs a pin, as `tex_snapshot`'s does, and the package has to be in `tex_snapshot`'s snapshot too, which installs it first with what it depends on. Taken out of the list, the package is installed again from the rest's repository.
- `tex_snapshot: latest` installs TeX as the installation page does, from the packages of the day it runs, and after that updates only with `-e tex_update=true`, so that a run changes nothing unasked. `tex_repository` then names the mirror `tlmgr` uses: a network that allows only named hosts needs a fixed one, such as `https://ctan.math.illinois.edu/systems/texlive/tlnet`, since CTAN's mirror service, the default, sends each request to a different mirror. With a date, the one host is `texlive.info`, which refuses Ansible's own downloads and lets `curl` through, as `tlmgr` uses it, so the role downloads from it with `curl`.
- The validators, each in a folder of its own version under `~/.local/opt/`: epubcheck, the Nu HTML checker from npm's `vnu-jar` (where each version is one file, unlike the GitHub release named `latest`, which is rebuilt in place), and veraPDF from its installer, checked against veraPDF's signature as well as its pin. veraPDF's WCAG modules, for `--wcag`, go in `~/.local/opt/verapdf-wcag-<version>/`: nine jars from Maven Central and two profiles, each pinned for that veraPDF; `-e verapdf_wcag=false` leaves them out. Java 21 comes from `apt`.
- The browser checks, for `--wcag`: Playwright from PyPI in a virtual environment, `~/.local/opt/textbookimprover-venv/`, which sees the system's Python packages too and whose `bin` goes first on `PATH` (`-e browser_checks_venv_on_path=false` leaves it off, and the tools are then run with its Python by name). Its headless Chromium in `~/.local/opt/ms-playwright/`, named by `PLAYWRIGHT_BROWSERS_PATH`: the role fetches and checks the archive itself, since Playwright checks only a download's length, and marks it the way Playwright does, so Playwright takes it for one it installed. Its libraries and fonts come from `apt`, Playwright's own list less Xvfb, so updating needs no `sudo`, where `playwright install --with-deps` asks each time. DAISY's Ace in `~/.local/opt/ace-<version>/`, installed with `npm ci` from a lock file in the collection that gives every package's SHA-512, and linked as `~/.local/bin/ace-puppeteer`, with `PUPPETEER_EXECUTABLE_PATH` naming Playwright's Chromium; and Node for it in `~/.local/opt/node-v<version>-linux-x64/`, linked as `node`, `npm`, and `npx`, from Node's own release, checked against Node's signed checksums as well as its pin, since the distributions' `npm` is older than Ace asks for. `-e browser_checks_ace=false` leaves out Ace and Node.
- For the `developer` playbook: uv in `~/.local/opt/uv-<version>/`, not put on `PATH`, so a uv of your own is left alone, with its Pythons in `~/.local/opt/uv-python/`, its own cache, and none of your uv settings read; and OpenStax's cookbook in `~/tools/openstax-cookbook/`.
- With `ti_fonts`: Noto Sans Math from notofonts' release, checked against its pin (notofonts publishes no checksum), unpacked in `~/.local/opt/noto-sans-math-<version>/`, and its `NotoSansMath-Regular.ttf` copied into `~/.local/share/fonts/`, where a copy already there is kept. LuaTeX's font list is made again when it doesn't name that copy. Of two files with one name, the list keeps the first it reads, and it reads the system's fonts first, so where a package has a copy, as the `pdf` profile's `fonts-noto-core` has (its 2.001, which has no math table), the role names that one file in a luaotfload blacklist in your own TeX tree (`kpsewhich -var-value=TEXMFHOME`, then `tex/luatex/luaotfload/luaotfload-blacklist.cnf`; for TinyTeX that's `~/.TinyTeX/texmf-local`, whose `ls-R` the role makes again so the file is found) and makes the list from nothing. The play ends by having LuaLaTeX set a formula in the font, as TextbookImprover names it. TeX Live's `noto-emoji` goes in with the TeX packages.
- Checked downloads in `~/.cache/textbookimprover-ansible/`, so a second run downloads nothing.

A release the collection has no checksum or commit for stops the play, which names the variable that adds one (`ti_pins`). A pin given that way can add a version, never replace one the collection has.

## New releases

`util/update-pins.py`, for the collection's maintainers, writes the pins and checks them; the playbooks never run it. It needs Python, PyYAML, `git`, `gpg`, and `gpgv`, and for Ace, npm 10 or later.

```bash
util/update-pins.py check                       # which releases are newer than the defaults
util/update-pins.py add vnu 26.11.20 --default  # pin one, and make it the default
util/update-pins.py verify node 26.13.1         # download a pinned one again and check it
```

`add` downloads a release and checks it against everything its publisher offers before writing the pin into the role's `vars/pins.yml`, newest first, with the file's comments left as they are:

- **Pandoc, TinyTeX, epubcheck, uv, and Noto Sans Math**: the SHA-256 GitHub computes for each release asset, read from GitHub's API (with `GITHUB_TOKEN` if it's set, since the API allows few requests an hour without one), and uv's own checksum file. Where the API can't be read, it says so, and `--require-github-digest` makes that a failure.
- **The Nu checker**: npm's SHA-512 of its tarball.
- **veraPDF**: its signature, with the key in `roles/validators/files/verapdf.asc`, whose fingerprint is checked first. The WCAG modules for a new veraPDF are pinned by hand, as the pins' comment says.
- **Node**: its `SHASUMS256.txt`'s signature, with the keys in `roles/browser_checks/files/nodejs/`, each file named by its key's fingerprint. A release signed by a key the collection doesn't keep stops it; the key is added from Node's own list of releasers.
- **Playwright**: PyPI's digests for its wheel and for greenlet's wheels for Python 3.12, 3.13, and 3.14; and the headless Chromium its `browsers.json` names, from Playwright's address, checked against the MD5 Google's bucket gives.
- **Ace**: a lock file made by npm, in `roles/browser_checks/files/ace/<version>/`, which must have every package from npm's registry with a SHA-512, with the install scripts the role doesn't run named, and with what `npm audit` finds in it.
- **TextbookImprover**: the commit its release's tag names.

A pin is never replaced: for a version already pinned, `add` and `verify` check the download against the pin, and any difference stops the script. `check --strict` exits 1 when anything is newer, for a scheduled job.

## Testing

`tests/run-all.sh` runs every check whose needs are met and says which it skipped and why; `--help` lists its options.

```bash
tests/run-all.sh                 # the quick checks
tests/run-all.sh --containers    # and the playbook in fresh containers
tests/run-all.sh --suites        # and TextbookImprover's suites in each
```

The checks, and what each needs:

- **`tests/check-secrets.py`** (Python and git) fails if anything git tracks looks like a key, a vault password, an inventory, or a password or token in plain text, and if `.gitignore` or `galaxy.yml`'s `build_ignore` lets any such name through. It's quick enough to run before each commit.
- **`tests/unit/test_update_pins.py`** (Python and PyYAML) holds `util/update-pins.py`'s parts that need no network, on a copy of the roles: where a new pin goes, that a pin is never replaced, and how a default is set.
- **`tests/unit/test_check_skips.py`** (Python) holds `tests/check-skips.py` to a list of skips as `run-all.sh` writes it, and reads each list in `tests/skips/`.
- **`tests/unit/test_retryable.py`** (Python) holds the rule for trying a download again, the test plugin `oerforge.textbookimprover.retryable`, to the results `get_url`, `curl`, and `git` gave for each kind of failure on the targets' own releases.
- **`tests/unit/test_bindep.py`** (bindep importable, or a folder holding it named by `TI_TEST_BINDEP`) holds the lookup plugin to bindep's own answers.
- **`ansible-lint`**, which passes at its `production` profile; `.ansible-lint` says why one rule is skipped.
- **The shell check** (`dash` and `shellcheck`): `bootstrap.sh` is POSIX `sh` throughout, since some will start it as `sh bootstrap.sh`, so `dash` has to parse it and ShellCheck has to find nothing in it as `sh`.
- **`tests/run-scenarios.sh`** (Docker and the network) runs `tests/scenario.sh` in a fresh container of each image in `TI_TEST_IMAGES` (Ubuntu 24.04 and 26.04 if unset; Debian 13 too, given an image of it): it installs `ansible-core` from `apt`, makes an ordinary user with `sudo`, runs the playbook as that user, runs it again to check that nothing changes, and runs the user step with `sudo` taken away. With `--suites` it then runs TextbookImprover's suites as that user, and with `TI_TEST_BINDEP` set it runs the bindep check on each host too. `TI_TEST_PANDOCS` runs the suites once with each Pandoc it names that the play installed, and with `3.9`, under the suites' own stand-in for Pandoc 3.9 (which TextbookImprover 0.10 doesn't pass: run it with `-e ti_source=git`). After a run of every suite, `tests/check-skips.py` holds the checks they skipped to the playbook's list in `tests/skips/` (each line a pattern matched against `run-all.sh`'s list, a line marked `3.9:` for the stand-in alone), and the scenario fails on a skip the list doesn't name or a suite not run at all, since a skip there means the play left out something the suites need; it names any pattern no skip matched, too. `TI_TEST_SKIPS` gives another list, or `none` to check nothing, as for a run with parts of the play switched off. With `TI_TEST_BOOTSTRAP` set, it runs each play through `bootstrap.sh` instead, at a terminal `script` gives it, as a user whose `sudo` asks for a password: `bootstrap.sh` installs `ansible-core` and `git` and fetches the collection from the clone being tested, at the commit checked out there. On a network a container reaches only through a proxy, `TI_TEST_PROXY` names it: the container then shares the host's network, and `apt` and the play's downloads go through the proxy, with `TI_TEST_CA` for the certificates it signs with.

`--no-skip` makes a check that can't run a failure.

On GitHub, `.github/workflows/checks.yml` runs the quick checks with `--no-skip` on every push and pull request, on Ubuntu 24.04 with its own `dash` and ShellCheck and with `ansible-lint` 26.11.0 and bindep 2.14.0 from PyPI. On `main`, every Monday, and when started by hand, it also runs the `user` playbook and TextbookImprover's suites in a fresh container of Ubuntu 24.04, Ubuntu 26.04, and Debian 13, each on a runner of its own. It needs no secret, and its token can only read the repository.

`notes/PLATFORMS.md` has what's known about each distribution, and how each fact is known.
