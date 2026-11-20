# textbookimprover-ansible

Ansible playbooks that set up a machine to use or develop [TextbookImprover](https://github.com/OERforge/textbookimprover): Pandoc, TextbookImprover itself, LuaLaTeX for tagged PDFs, the validators, the browser checks, and the rest of what its [installation page](https://github.com/OERforge/textbookimprover/blob/main/docs/installation.md) asks for.

**Only part of it works yet.** The `user` playbook installs the system packages a book's conversion needs, checks the Python, and installs Pandoc, TeX for a PDF target, the validators, the browser checks, and TextbookImprover; a `developer` playbook adds what working on TextbookImprover needs; and `bootstrap.sh` runs either of them with one command. The fonts for OpenStax's books come next.

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

It asks which setup the machine is for, `user` (converting books) or `developer` (working on TextbookImprover), and which optional parts to install: TeX for PDF output, the validators, and the browser checks. Then it asks for your `sudo` password, once, installs `ansible-core` and `git` with `apt` if they're missing, fetches the collection, and runs the playbook on the machine, which can take a while the first time. Open a new terminal afterward ([The shell's settings](#the-shells-settings), below).

Run it again to update everything. `sh bootstrap.sh --user-only` updates what's in your home folder without asking for a password, `--reconfigure` asks the questions again, `--profile` chooses the setup without asking (saved with the answers on the first run or with `--reconfigure`), and options after `--` go to `ansible-playbook`, so `sh bootstrap.sh -- -e tex_update=true` brings TeX up to date as well. `--help` lists the rest. What it keeps, and where:

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
      tex_repository: https://ctan.math.illinois.edu/systems/texlive/tlnet
```

```bash
ansible-playbook -i ~/textbookimprover-machine.yml -K oerforge.textbookimprover.user
```

The same settings can go in a `host_vars/localhost.yml` beside an inventory file in a folder of its own, given with `-i` as the folder. The roles' defaults come first, then the inventory's settings (`group_vars` before `host_vars`, as Ansible always takes them), then `-e`. Each playbook sets one thing itself, `ti_profile` (`user` or `developer`), which the defaults follow, so the two playbooks differ only in their defaults and in the `developer` role.

The switches for the optional parts, each `true` or `false`:

- `ti_tex`, `ti_validators`, and `ti_browser_checks`: on in both profiles.
- `ti_libreoffice`: on in `developer`, off in `user`.
- `verapdf_wcag`, `browser_checks_ace`, `browser_checks_venv_on_path`, `developer_python39`, and `developer_cookbook`: the parts of a role, each on by default.

Inventories, like keys and passwords, are kept out of the collection's commits and builds (Testing, below), so one put in the collection's folder by mistake isn't committed.

### What goes where

- Pandoc's releases in `~/.local/opt/pandoc-<version>/`, linked as `~/.local/bin/pandoc-<version>`, the first of `pandoc_versions` as `~/.local/bin/pandoc` too. Several can sit side by side: `-e '{"pandoc_versions": ["3.14", "3.13"]}'`.
- TextbookImprover in `~/tools/textbookimprover-<release>/`, or `~/tools/textbookimprover/` for a clone of `main` (`ti_source: git`, the `developer` profile's default). `ti_dir` puts it elsewhere, and `ti_version` names the release, or the branch, tag, or commit for `git`.
- TeX: TinyTeX in `~/.TinyTeX/`, as the installation page has it, with the page's packages added (`tex_extra_packages` adds more). Or, with `tex_distribution: texlive` (the `developer` profile's default), TeX Live from its own installer in `~/.local/opt/texlive/2026/`, the full scheme by default (`texlive_scheme`), which has every package but takes several gigabytes; without its documentation and sources, as the role installs it, it took 17 minutes here. Either is brought up to date when first installed, and afterward only with `-e tex_update=true`, so that a run changes nothing unasked. `tex_repository` names the mirror `tlmgr` uses: a network that allows only named hosts needs a fixed one, such as `https://ctan.math.illinois.edu/systems/texlive/tlnet`.
- The validators, each in a folder of its own version under `~/.local/opt/`: epubcheck, the Nu HTML checker from npm's `vnu-jar` (where each version is one file, unlike the GitHub release named `latest`, which is rebuilt in place), and veraPDF from its installer, checked against veraPDF's signature as well as its pin. veraPDF's WCAG modules, for `--wcag`, go in `~/.local/opt/verapdf-wcag-<version>/`: nine jars from Maven Central and two profiles, each pinned for that veraPDF; `-e verapdf_wcag=false` leaves them out. Java 21 comes from `apt`.
- The browser checks, for `--wcag`: Playwright from PyPI in a virtual environment, `~/.local/opt/textbookimprover-venv/`, which sees the system's Python packages too and whose `bin` goes first on `PATH` (`-e browser_checks_venv_on_path=false` leaves it off, and the tools are then run with its Python by name). Its headless Chromium in `~/.local/opt/ms-playwright/`, named by `PLAYWRIGHT_BROWSERS_PATH`: the role fetches and checks the archive itself, since Playwright checks only a download's length, and marks it the way Playwright does, so Playwright takes it for one it installed. Its libraries and fonts come from `apt`, Playwright's own list less Xvfb, so updating needs no `sudo`, where `playwright install --with-deps` asks each time. DAISY's Ace in `~/.local/opt/ace-<version>/`, installed with `npm ci` from a lock file in the collection that gives every package's SHA-512, and linked as `~/.local/bin/ace-puppeteer`, with `PUPPETEER_EXECUTABLE_PATH` naming Playwright's Chromium; and Node for it in `~/.local/opt/node-v<version>-linux-x64/`, linked as `node`, `npm`, and `npx`, from Node's own release, checked against Node's signed checksums as well as its pin, since the distributions' `npm` is older than Ace asks for. `-e browser_checks_ace=false` leaves out Ace and Node.
- For the `developer` playbook: uv in `~/.local/opt/uv-<version>/`, not put on `PATH`, so a uv of your own is left alone, with its Pythons in `~/.local/opt/uv-python/`, its own cache, and none of your uv settings read; and OpenStax's cookbook in `~/tools/openstax-cookbook/`.
- Checked downloads in `~/.cache/textbookimprover-ansible/`, so a second run downloads nothing.

A release the collection has no checksum or commit for stops the play, which names the variable that adds one (`ti_pins`). A pin given that way can add a version, never replace one the collection has.

## Testing

`tests/run-all.sh` runs every check whose needs are met and says which it skipped and why; `--help` lists its options.

```bash
tests/run-all.sh                 # the quick checks
tests/run-all.sh --containers    # and the playbook in fresh containers
tests/run-all.sh --suites        # and TextbookImprover's suites in each
```

The checks, and what each needs:

- **`tests/check-secrets.py`** (Python and git) fails if anything git tracks looks like a key, a vault password, an inventory, or a password or token in plain text, and if `.gitignore` or `galaxy.yml`'s `build_ignore` lets any such name through. It's quick enough to run before each commit.
- **`tests/unit/test_bindep.py`** (bindep importable, or a folder holding it named by `TI_TEST_BINDEP`) holds the lookup plugin to bindep's own answers.
- **`ansible-lint`**, which passes at its `production` profile; `.ansible-lint` says why one rule is skipped.
- **The shell check** (`dash` and `shellcheck`): `bootstrap.sh` is POSIX `sh` throughout, since some will start it as `sh bootstrap.sh`, so `dash` has to parse it and ShellCheck has to find nothing in it as `sh`.
- **`tests/run-scenarios.sh`** (Docker and the network) runs `tests/scenario.sh` in a fresh container of each image in `TI_TEST_IMAGES` (Ubuntu 24.04 and 26.04 if unset; Debian 13 too, given an image of it): it installs `ansible-core` from `apt`, makes an ordinary user with `sudo`, runs the playbook as that user, runs it again to check that nothing changes, and runs the user step with `sudo` taken away. With `--suites` it then runs TextbookImprover's suites as that user, and with `TI_TEST_BINDEP` set it runs the bindep check on each host too. With `TI_TEST_BOOTSTRAP` set, it runs each play through `bootstrap.sh` instead, at a terminal `script` gives it, as a user whose `sudo` asks for a password: `bootstrap.sh` installs `ansible-core` and `git` and fetches the collection from the clone being tested, at the commit checked out there. On a network a container reaches only through a proxy, `TI_TEST_PROXY` names it: the container then shares the host's network, and `apt` and the play's downloads go through the proxy, with `TI_TEST_CA` for the certificates it signs with.

`--no-skip` makes a check that can't run a failure. `notes/PLATFORMS.md` has what's known about each distribution, and how each fact is known.
