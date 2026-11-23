#!/usr/bin/env python3
"""Add pins for new releases, check the pins already written, and say which
releases are newer than the collection's defaults. For the collection's
maintainers, run by hand; the playbooks never run it.

    util/update-pins.py check
    util/update-pins.py add pandoc 3.15
    util/update-pins.py add node 26.14.0 --default
    util/update-pins.py verify pandoc 3.14
    util/update-pins.py add tex_snapshot 2026-11-21 --default

"add" downloads a release, checks it against everything its publisher
offers (a signature, a checksum file, the registry's own digest, the digest
GitHub computes for a release asset), and writes its pin into the role's
vars/pins.yml, so each new pin arrives as a change to review. A pin already
written is never replaced: a version already pinned is checked against its
pin instead, and a difference stops the script. "verify" does that for a
pinned version without adding anything. With --default, "add" also makes
the version the role's default (its *_default_version setting).

Downloads go into a temporary folder that's removed afterward. GITHUB_TOKEN,
if set, is sent to GitHub's API, which otherwise allows few requests an hour,
and nowhere else, not even where the API redirects.
Only the standard library is needed, and PyYAML to read the pins back;
"add ace" needs npm 10 or later; signatures need gpg and gpgv; TeX Live's
snapshots need curl.
"""

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROLES = os.path.join(TOP, "roles")
USER_AGENT = "textbookimprover-ansible-update-pins"


class Stop(Exception):
    """A check failed, or something can't be done: the script stops."""


def say(*parts):
    print(*parts, flush=True)


# --- Reading the collection.

def role_file(role, *parts):
    return os.path.join(ROLES, role, *parts)


def defaults(role):
    """The role's defaults that are plain values, by name."""
    found = {}
    with open(role_file(role, "defaults", "main.yml"), encoding="utf-8") as f:
        for line in f:
            m = re.match(r'^([a-z_]+): "?([^"{}\n]*?)"?\s*$', line)
            if m:
                found[m.group(1)] = m.group(2)
    return found


def pins(role):
    import yaml  # only here, so --help works without it
    with open(role_file(role, "vars", "pins.yml"), encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def version_key(text):
    """A version's parts as numbers, so 3.10 sorts after 3.9."""
    return tuple(int(n) for n in re.findall(r"\d+", text))


def stable(text):
    return re.fullmatch(r"v?\d+(\.\d+)*", text) is not None


# --- Downloads.

def fetch(url, headers=None, secret=None):
    """The body and headers. A secret header is never sent on to where a
    redirect points, as urllib sends the others."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    for name, value in (secret or {}).items():
        request.add_unredirected_header(name, value)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read(), response.headers
    except urllib.error.HTTPError as e:
        raise Stop(f"{url}: {e.code} {e.reason}") from e
    except urllib.error.URLError as e:
        raise Stop(f"{url}: {e.reason}") from e


def fetch_json(url, headers=None, secret=None):
    return json.loads(fetch(url, headers, secret)[0])


def download(url, folder):
    """Download into the folder; return the path and the response's headers."""
    path = os.path.join(folder, url.rsplit("/", 1)[-1])
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=600) as response, open(path, "wb") as out:
            shutil.copyfileobj(response, out, 1 << 20)
            return path, response.headers
    except urllib.error.HTTPError as e:
        raise Stop(f"{url}: {e.code} {e.reason}") from e
    except urllib.error.URLError as e:
        raise Stop(f"{url}: {e.reason}") from e


def curl(url, folder):
    """Download into the folder with curl, for texlive.info, which answers
    urllib with a page refusing it, and lets curl through, as tlmgr uses it."""
    path = os.path.join(folder, url.rsplit("/", 1)[-1])
    run = subprocess.run(["curl", "--fail", "--silent", "--show-error", "--location", "--proto", "=https",
                          "--max-time", "600", "--output", path, url], capture_output=True, text=True)
    if run.returncode != 0:
        raise Stop(f"{url}: {run.stderr.strip()}")
    return path


def digest(path, algorithm="sha256"):
    h = hashlib.new(algorithm)
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h


def git_tags(repository):
    """The repository's tags and the commits they name, peeled."""
    out = subprocess.run(["git", "ls-remote", "--tags", repository], check=True,
                         capture_output=True, text=True).stdout
    tags = {}
    for line in out.splitlines():
        commit, ref = line.split("\t")
        name = ref[len("refs/tags/"):]
        if name.endswith("^{}"):
            tags[name[:-3]] = commit           # an annotated tag's commit
        else:
            tags.setdefault(name, commit)
    return tags


def github_digest(owner_repo, tag, name):
    """The SHA-256 GitHub computed for a release asset, or None and why."""
    headers = {"Accept": "application/vnd.github+json"}
    secret = {}
    if os.environ.get("GITHUB_TOKEN"):
        secret["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    try:
        release = fetch_json(f"https://api.github.com/repos/{owner_repo}/releases/tags/{tag}",
                             headers, secret)
    except Stop as e:
        return None, str(e)
    for asset in release.get("assets", []):
        if asset.get("name") == name:
            value = asset.get("digest") or ""
            if value.startswith("sha256:"):
                return value[len("sha256:"):], None
            return None, "GitHub gives no digest for it"
    return None, f"the release has no asset {name}"


def check_github(owner_repo, tag, name, sha, require):
    expected, why = github_digest(owner_repo, tag, name)
    if expected is None:
        message = f"GitHub's digest for {name} not read: {why}"
        if require:
            raise Stop(message)
        say(f"  note: {message}; the pin rests on this download alone")
    elif expected != sha:
        raise Stop(f"{name}: GitHub's digest is {expected}, the download's {sha}")
    else:
        say(f"  GitHub's digest for {name} matches")


# --- Signatures, checked with the keys kept in the collection, in a GNUPGHOME
# of the script's own, so no keyserver is asked and no keyring of the
# maintainer's is read or changed.

def keyring(folder, key_files):
    home = os.path.join(folder, "gnupg")
    os.makedirs(home, mode=0o700, exist_ok=True)
    ring = os.path.join(folder, "keys.gpg")
    with open(ring, "wb") as out:
        for key in key_files:
            out.write(subprocess.run(["gpg", "--homedir", home, "--batch", "--dearmor"],
                                     stdin=open(key, "rb"), capture_output=True,
                                     check=True).stdout)
    return home, ring


def fingerprints(home, key_file):
    out = subprocess.run(["gpg", "--homedir", home, "--batch", "--with-colons", "--show-keys",
                          key_file], capture_output=True, text=True, check=True).stdout
    return [line.split(":")[9] for line in out.splitlines() if line.startswith("fpr:")]


def gpgv(home, ring, signature, data):
    """The fingerprint of the key that made a good signature, or Stop."""
    run = subprocess.run(["gpgv", "--homedir", home, "--keyring", ring, "--status-fd", "1",
                          signature, data], capture_output=True, text=True)
    # VALIDSIG's last field is the primary key's fingerprint, which a
    # subkey's signature names too.
    good = [l.split()[-1] for l in run.stdout.splitlines() if l.startswith("[GNUPG:] VALIDSIG ")]
    if run.returncode == 0 and good:
        return good[0]
    missing = [l.split()[2] for l in run.stdout.splitlines() if l.startswith("[GNUPG:] NO_PUBKEY ")]
    if missing:
        raise Stop(f"{os.path.basename(signature)} is signed by key {missing[0]}, which the "
                   f"collection doesn't keep")
    raise Stop(f"{os.path.basename(signature)}: not a good signature of "
               f"{os.path.basename(data)}\n{run.stderr.strip()}")


# --- Writing pins: a new entry goes first under its map, as text, so the
# file's comments and order stay as they are; the file is read back to check.

def write_pin(role, name, key, value_lines=None, single=None, items=None):
    path = role_file(role, "vars", "pins.yml")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = re.search(rf"^{re.escape(name)}:\n", text, re.M)
    if not m:
        raise Stop(f"{path} has no {name}")
    def scalar(value):  # a hash of digits alone would read back as a number
        return f'"{value}"' if str(value).isdigit() else value
    if single is not None:
        entry = f'  "{key}": {scalar(single)}\n'
    elif items is not None:
        entry = f'  "{key}":\n' + "".join(f"    - {scalar(i)}\n" for i in items)
    else:
        entry = f'  "{key}":\n' + "".join(f"    {l}\n" for l in value_lines)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text[:m.end()] + entry + text[m.end():])
    if key not in pins(role).get(name, {}):
        raise Stop(f"{path}: the new pin didn't read back")
    say(f"  pinned in roles/{role}/vars/pins.yml: {name}[{key}]")


def settle(role, name, key, value, value_lines=None, single=None):
    """Write a pin, or check one already there; never replace it."""
    existing = pins(role).get(name, {}).get(key)
    if existing is None:
        write_pin(role, name, key, value_lines, single)
    elif existing == value:
        say(f"  already pinned, and the pin matches: {name}[{key}]")
    else:
        raise Stop(f"{name}[{key}] is pinned as {existing!r}, but the release gives {value!r}; "
                   f"a pin is never replaced")


def set_default(role, name, version):
    path = role_file(role, "defaults", "main.yml")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    new, n = re.subn(rf'^{re.escape(name)}: .*$', f'{name}: "{version}"', text, count=1, flags=re.M)
    if not n:
        raise Stop(f"{path} has no {name}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)
    say(f"  default: {name} is {version} in roles/{role}/defaults/main.yml")


# --- Each kind of download. Each takes the version, a scratch folder, and
# the options, checks what the publisher offers, and settles the pin.

def tarball(role, name, url, version, folder, opts, github=None, sha256_file=None):
    path, _ = download(url, folder)
    sha = digest(path).hexdigest()
    say(f"  {os.path.basename(path)}: SHA-256 {sha}")
    if sha256_file:
        expected = fetch(sha256_file)[0].decode().split()[0]
        if expected != sha:
            raise Stop(f"the publisher's checksum file gives {expected}")
        say("  the publisher's checksum file matches")
    if github:
        check_github(github[0], github[1], os.path.basename(path), sha, opts.require_github_digest)
    settle(role, name, version, sha, single=sha)


def add_pandoc(v, folder, opts):
    base = defaults("pandoc")["pandoc_release_url"]
    tarball("pandoc", "pandoc_pins", f"{base}/{v}/pandoc-{v}-linux-amd64.tar.gz", v, folder, opts,
            github=("jgm/pandoc", v))
    say("  pandoc_versions is an expression of the profile: change it by hand to make this a default")


def add_tinytex(v, folder, opts):
    base = defaults("tex")["tinytex_release_url"]
    tarball("tex", "tinytex_pins", f"{base}/{v}/TinyTeX-linux-x86_64-{v}.tar.xz", v, folder, opts,
            github=("rstudio/tinytex-releases", v))
    if opts.default:
        set_default("tex", "tinytex_default_version", v)


def add_tex_snapshot(v, folder, opts):
    """A day's snapshot of TeX Live's repository: the SHA-512 of its database,
    as the checksum file signed by TeX Live's key gives it."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        raise Stop(f"{v} isn't a date, as 2026-11-20")
    base = f"{defaults('tex')['tex_snapshot_url']}/{v.replace('-', '/')}/tlnet/tlpkg"
    sums = curl(f"{base}/texlive.tlpdb.sha512", folder)
    signature = curl(f"{base}/texlive.tlpdb.sha512.asc", folder)
    key = role_file("tex", "files", "texlive.asc")
    home, ring = keyring(folder, [key])
    expected = pins("tex")["texlive_key_fingerprint"]
    if expected not in fingerprints(home, key):
        raise Stop(f"files/texlive.asc isn't the key {expected}")
    signer = gpgv(home, ring, signature, sums)
    fields = open(sums, encoding="utf-8").read().split()
    if len(fields) != 2 or fields[1] != "texlive.tlpdb" or not re.fullmatch(r"[0-9a-f]{128}", fields[0]):
        raise Stop(f"texlive.tlpdb.sha512 isn't one SHA-512 of texlive.tlpdb: {fields[:4]}")
    say(f"  texlive.tlpdb of {v}: SHA-512 {fields[0]}; signed by {signer}")
    settle("tex", "tex_snapshot_pins", v, fields[0], single=fields[0])
    if opts.default:
        set_default("tex", "tex_snapshot", v)


def newest_tex_snapshot():
    """The newest of the last week's snapshots."""
    import datetime
    base = defaults("tex")["tex_snapshot_url"]
    today = datetime.datetime.now(datetime.timezone.utc).date()
    with tempfile.TemporaryDirectory(prefix="update-pins-") as folder:
        for back in range(8):
            day = (today - datetime.timedelta(days=back)).isoformat()
            try:
                curl(f"{base}/{day.replace('-', '/')}/tlnet/tlpkg/texlive.tlpdb.sha512", folder)
                return day
            except Stop:
                continue
    raise Stop(f"{base} has no snapshot from the last week")


def add_uv(v, folder, opts):
    base = defaults("developer")["uv_release_url"]
    url = f"{base}/{v}/uv-x86_64-unknown-linux-gnu.tar.gz"
    tarball("developer", "uv_pins", url, v, folder, opts, github=("astral-sh/uv", v),
            sha256_file=url + ".sha256")
    if opts.default:
        set_default("developer", "uv_default_version", v)


def add_epubcheck(v, folder, opts):
    base = defaults("validators")["epubcheck_release_url"]
    tarball("validators", "epubcheck_pins", f"{base}/v{v}/epubcheck-{v}.zip", v, folder, opts,
            github=("w3c/epubcheck", f"v{v}"))
    if opts.default:
        set_default("validators", "epubcheck_default_version", v)


def add_noto_sans_math(v, folder, opts):
    base = defaults("fonts")["noto_sans_math_release_url"]
    tag = f"NotoSansMath-v{v}"
    tarball("fonts", "noto_sans_math_pins", f"{base}/{tag}/{tag}.zip", v, folder, opts,
            github=("notofonts/math", tag))
    if opts.default:
        set_default("fonts", "noto_sans_math_default_version", v)


def add_vnu(v, folder, opts):
    meta = fetch_json(f"https://registry.npmjs.org/vnu-jar/{v}")
    path, _ = download(meta["dist"]["tarball"], folder)
    sha = digest(path).hexdigest()
    integrity = "sha512-" + base64.b64encode(digest(path, "sha512").digest()).decode()
    if integrity != meta["dist"].get("integrity"):
        raise Stop(f"npm's integrity value is {meta['dist'].get('integrity')}, the download's {integrity}")
    say(f"  vnu-jar-{v}.tgz: SHA-256 {sha}; npm's SHA-512 matches")
    settle("validators", "vnu_pins", v, sha, single=sha)
    if opts.default:
        set_default("validators", "vnu_default_version", v)


def add_verapdf(v, folder, opts):
    base = defaults("validators")["verapdf_release_url"]
    zip_name = f"verapdf-greenfield-{v}-installer.zip"
    url = f"{base}/{'.'.join(v.split('.')[:2])}/{zip_name}"
    path, _ = download(url, folder)
    signature, _ = download(url + ".asc", folder)
    key = role_file("validators", "files", "verapdf.asc")
    home, ring = keyring(folder, [key])
    expected = pins("validators")["verapdf_key_fingerprint"]
    if expected not in fingerprints(home, key):
        raise Stop(f"files/verapdf.asc isn't the key {expected}")
    signer = gpgv(home, ring, signature, path)
    sha = digest(path).hexdigest()
    say(f"  {zip_name}: SHA-256 {sha}; signed by {signer}")
    settle("validators", "verapdf_pins", v, sha, single=sha)
    if v not in pins("validators").get("verapdf_wcag_files", {}):
        say(f"  note: verapdf_wcag_files has nothing for {v}: its WCAG modules are pinned by hand, "
            f"as the pins' comment says, before it can be the default")
    elif opts.default:
        set_default("validators", "verapdf_default_version", v)


def add_node(v, folder, opts):
    base = defaults("browser_checks")["node_release_url"]
    name = f"node-v{v}-linux-x64.tar.xz"
    path, _ = download(f"{base}/v{v}/{name}", folder)
    sums, _ = download(f"{base}/v{v}/SHASUMS256.txt", folder)
    signature, _ = download(f"{base}/v{v}/SHASUMS256.txt.sig", folder)
    keys = sorted(os.path.join(role_file("browser_checks", "files", "nodejs"), k)
                  for k in os.listdir(role_file("browser_checks", "files", "nodejs")) if k.endswith(".asc"))
    home, ring = keyring(folder, keys)
    for key in keys:
        fpr = os.path.basename(key)[:-4]
        if fpr not in fingerprints(home, key):
            raise Stop(f"files/nodejs/{os.path.basename(key)} isn't the key {fpr}")
    try:
        signer = gpgv(home, ring, signature, sums)
    except Stop as e:
        if "doesn't keep" in str(e):
            raise Stop(f"{e}. If Node's README lists that key's owner as a releaser, add the key "
                       f"as roles/browser_checks/files/nodejs/<its fingerprint>.asc and run this "
                       f"again") from e
        raise
    sha = digest(path).hexdigest()
    listed = [l.split()[0] for l in open(sums, encoding="utf-8") if l.split()[1:] == [name]]
    if listed != [sha]:
        raise Stop(f"the signed SHASUMS256.txt gives {listed} for {name}, the download {sha}")
    say(f"  {name}: SHA-256 {sha}, as the SHASUMS256.txt signed by {signer} gives it")
    value = {"sha256": sha, "signer": signer}
    settle("browser_checks", "node_pins", v, value, [f"sha256: {sha}", f"signer: {signer}"])
    if opts.default:
        set_default("browser_checks", "node_default_version", v)


def add_playwright(v, folder, opts):
    meta = fetch_json(f"https://pypi.org/pypi/playwright/{v}/json")
    wheel = [u for u in meta["urls"] if u["filename"] == f"playwright-{v}-py3-none-manylinux1_x86_64.whl"]
    if not wheel:
        raise Stop(f"PyPI has no manylinux1 x86_64 wheel of Playwright {v}")
    path, _ = download(wheel[0]["url"], folder)
    sha = digest(path).hexdigest()
    if sha != wheel[0]["digests"]["sha256"]:
        raise Stop(f"PyPI's digest is {wheel[0]['digests']['sha256']}, the download's {sha}")
    say(f"  {wheel[0]['filename']}: SHA-256 {sha}, PyPI's digest")

    # greenlet: the newest release Playwright's requirement takes, with its
    # wheels for the three systems' Pythons.
    requirement = [r for r in meta["info"]["requires_dist"] or [] if r.startswith("greenlet")]
    low = re.search(r">=\s*([\d.]+)", requirement[0]).group(1) if requirement else "0"
    high = re.search(r"<\s*([\d.]+)", requirement[0]).group(1) if requirement and "<" in requirement[0] else None
    greenlet = fetch_json("https://pypi.org/pypi/greenlet/json")
    choices = [r for r in greenlet["releases"] if stable(r) and version_key(r) >= version_key(low)
               and (high is None or version_key(r) < version_key(high))]
    g = max(choices, key=version_key)
    files = fetch_json(f"https://pypi.org/pypi/greenlet/{g}/json")["urls"]
    hashes = []
    for cp in ("cp312", "cp313", "cp314"):
        found = [u["digests"]["sha256"] for u in files
                 if re.fullmatch(rf"greenlet-{re.escape(g)}-{cp}-{cp}-manylinux.*x86_64\.whl", u["filename"])]
        if not found:
            raise Stop(f"greenlet {g} has no manylinux x86_64 wheel for {cp}")
        hashes += found
    say(f"  greenlet {g} ({requirement[0] if requirement else 'any'}): {len(hashes)} wheels, from PyPI's digests")
    existing = pins("browser_checks").get("greenlet_pins", {}).get(g)
    if existing is None:
        write_pin("browser_checks", "greenlet_pins", g, items=hashes)
    elif sorted(existing) != sorted(hashes):
        raise Stop(f"greenlet_pins[{g}] is pinned with other hashes; a pin is never replaced")
    else:
        say(f"  already pinned, and the pin matches: greenlet_pins[{g}]")

    # Its Chromium: the headless shell its browsers.json names, from the
    # address Playwright downloads it from, compared with Google's own MD5.
    with zipfile.ZipFile(path) as z:
        browsers = json.loads(z.read("playwright/driver/package/browsers.json"))
    shell = [b for b in browsers["browsers"] if b["name"] == "chromium-headless-shell"][0]
    cv, revision = shell["browserVersion"], shell["revision"]
    url = f"https://cdn.playwright.dev/builds/cft/{cv}/linux64/chrome-headless-shell-linux64.zip"
    pinned = pins("browser_checks").get("chromium_pins", {}).get(cv)
    if pinned and pinned.get("revision") != revision:
        raise Stop(f"chromium_pins[{cv}] has revision {pinned.get('revision')}, Playwright {revision}")
    # Downloaded even when pinned, so that "verify" checks it again.
    archive, headers = download(pinned["url"] if pinned else url, folder)
    csha = digest(archive).hexdigest()
    # Google sends one x-goog-hash header for each hash, CRC32C's and MD5's.
    md5 = re.search(r"md5=([^,\s]+)", ",".join(headers.get_all("x-goog-hash") or []))
    if not md5:
        raise Stop("Google's bucket gave no MD5 for the Chromium archive")
    if base64.b64decode(md5.group(1)).hex() != digest(archive, "md5").hexdigest():
        raise Stop("the Chromium archive's MD5 isn't the bucket's")
    with zipfile.ZipFile(archive) as z:
        executable = "chrome-headless-shell-linux64/chrome-headless-shell"
        if executable not in z.namelist():
            raise Stop(f"the Chromium archive has no {executable}")
    say(f"  Chromium {cv} (revision {revision}): SHA-256 {csha}; its MD5 the bucket's")
    if not pinned:
        write_pin("browser_checks", "chromium_pins", cv, [f'revision: "{revision}"', f"url: {url}",
                                                         f"sha256: {csha}", f"executable: {executable}"])
    elif pinned.get("sha256") != csha:
        raise Stop(f"chromium_pins[{cv}] is pinned as {pinned.get('sha256')}; a pin is never replaced")
    else:
        say(f"  already pinned, and the pin matches: chromium_pins[{cv}]")
    settle("browser_checks", "playwright_pins", v, {"wheel": sha, "greenlet": g},
           [f"wheel: {sha}", f'greenlet: "{g}"'])
    if opts.default:
        set_default("browser_checks", "playwright_default_version", v)


def add_ace(v, folder, opts):
    """Ace's lock file, made with npm from a package.json naming the release,
    and checked: every package from npm's registry with a SHA-512, and the
    install scripts named, since the role runs none of them."""
    target = role_file("browser_checks", "files", "ace", v)
    work = os.path.join(folder, "ace")
    os.makedirs(work)
    with open(os.path.join(work, "package.json"), "w", encoding="utf-8") as f:
        json.dump({"name": "textbookimprover-ace", "private": True,
                   "dependencies": {"@daisy/ace": v}}, f, indent=2)
        f.write("\n")
    subprocess.run(["npm", "install", "--package-lock-only", "--ignore-scripts", "--no-audit",
                    "--no-fund"], cwd=work, check=True, capture_output=True)
    lock = json.load(open(os.path.join(work, "package-lock.json"), encoding="utf-8"))["packages"]
    hosts = {p.get("resolved", "").split("/")[2] for k, p in lock.items() if k and p.get("resolved")}
    unchecked = [k for k, p in lock.items() if k and not p.get("integrity")]
    scripts = [k.split("node_modules/")[-1] for k, p in lock.items() if p.get("hasInstallScript")]
    if hosts != {"registry.npmjs.org"} or unchecked:
        raise Stop(f"the lock file has packages from {sorted(hosts)}, or without a SHA-512: {unchecked}")
    say(f"  {len(lock) - 1} packages, all from registry.npmjs.org with a SHA-512; "
        f"install scripts, which the role doesn't run: {', '.join(scripts) or 'none'}")
    audit = subprocess.run(["npm", "audit", "--package-lock-only", "--json"], cwd=work,
                           capture_output=True, text=True)
    try:
        counts = json.loads(audit.stdout)["metadata"]["vulnerabilities"]
        say("  npm audit: " + ", ".join(f"{n} {k}" for k, n in counts.items() if n and k != "total")
            if counts.get("total") else "  npm audit: nothing found")
    except (ValueError, KeyError):
        say("  npm audit: couldn't be read")
    if os.path.isdir(target):
        same = all(open(os.path.join(work, n), "rb").read() == open(os.path.join(target, n), "rb").read()
                   for n in ("package.json", "package-lock.json"))
        say(f"  roles/browser_checks/files/ace/{v}/ is there already, "
            + ("and the new lock file is the same" if same
               else "and the new lock file differs (npm resolved some packages anew); the one there is kept"))
    else:
        os.makedirs(target)
        for n in ("package.json", "package-lock.json"):
            shutil.copy(os.path.join(work, n), os.path.join(target, n))
        say(f"  written: roles/browser_checks/files/ace/{v}/")
    if opts.default:
        set_default("browser_checks", "ace_default_version", v)


def add_textbookimprover(v, folder, opts):
    repository = defaults("textbookimprover")["ti_repository"]
    commit = git_tags(repository).get(f"v{v}")
    if not commit:
        raise Stop(f"{repository} has no tag v{v}")
    say(f"  v{v} names {commit}")
    settle("textbookimprover", "textbookimprover_pins", v, commit, single=commit)
    say("  ti_version is an expression of ti_source: change it by hand to make this the default")


ADD = {"pandoc": add_pandoc, "tinytex": add_tinytex, "tex_snapshot": add_tex_snapshot, "uv": add_uv, "epubcheck": add_epubcheck,
       "vnu": add_vnu, "verapdf": add_verapdf, "node": add_node, "playwright": add_playwright,
       "ace": add_ace, "noto_sans_math": add_noto_sans_math, "textbookimprover": add_textbookimprover}


# --- Which releases are newer than the defaults.

def newest_tag(repository, prefix=""):
    tags = [t[len(prefix):] for t in git_tags(repository) if t.startswith(prefix) and stable(t[len(prefix):])]
    return max(tags, key=version_key) if tags else None


def check(opts):
    current = {
        "pandoc": max(pins("pandoc")["pandoc_pins"], key=version_key),
        "tinytex": defaults("tex")["tinytex_default_version"],
        "tex_snapshot": defaults("tex")["tex_snapshot"],
        "uv": defaults("developer")["uv_default_version"],
        "epubcheck": defaults("validators")["epubcheck_default_version"],
        "vnu": defaults("validators")["vnu_default_version"],
        "verapdf": defaults("validators")["verapdf_default_version"],
        "node": defaults("browser_checks")["node_default_version"],
        "playwright": defaults("browser_checks")["playwright_default_version"],
        "ace": defaults("browser_checks")["ace_default_version"],
        "noto_sans_math": defaults("fonts")["noto_sans_math_default_version"],
        "textbookimprover": max(pins("textbookimprover")["textbookimprover_pins"], key=version_key),
    }
    newest = {
        "pandoc": lambda: newest_tag("https://github.com/jgm/pandoc"),
        "tinytex": lambda: "v" + newest_tag("https://github.com/rstudio/tinytex-releases", "v"),
        "tex_snapshot": newest_tex_snapshot,
        "uv": lambda: newest_tag("https://github.com/astral-sh/uv"),
        "epubcheck": lambda: newest_tag("https://github.com/w3c/epubcheck", "v"),
        "vnu": lambda: fetch_json("https://registry.npmjs.org/vnu-jar")["dist-tags"]["latest"],
        "verapdf": newest_verapdf,
        "node": lambda: newest_node(current["node"]),
        "playwright": lambda: fetch_json("https://pypi.org/pypi/playwright/json")["info"]["version"],
        "ace": lambda: fetch_json("https://registry.npmjs.org/@daisy/ace")["dist-tags"]["latest"],
        "noto_sans_math": lambda: newest_tag("https://github.com/notofonts/math", "NotoSansMath-v"),
        "textbookimprover": lambda: newest_tag(defaults("textbookimprover")["ti_repository"], "v"),
    }
    behind = 0
    for name, have in current.items():
        try:
            latest = newest[name]()
        except (Stop, subprocess.CalledProcessError, KeyError, ValueError) as e:
            say(f"{name:17} {have:12} couldn't be read: {e}")
            continue
        newer = latest and version_key(latest) > version_key(have)
        behind += bool(newer)
        say(f"{name:17} {have:12} " + (f"newer: {latest}   (util/update-pins.py add {name} {latest})"
                                       if newer else "the newest"))
    return 1 if behind and opts.strict else 0


def newest_verapdf():
    base = defaults("validators")["verapdf_release_url"]
    folders = re.findall(r'href="(\d+\.\d+)/"', fetch(base + "/")[0].decode())
    latest = max(folders, key=version_key)
    found = re.findall(rf"verapdf-greenfield-({re.escape(latest)}\.\d+)-installer\.zip\"",
                       fetch(f"{base}/{latest}/")[0].decode())
    return max(found, key=version_key)


def newest_node(have):
    """The newest release of the same major line, or a newer long-term line."""
    releases = fetch_json(defaults("browser_checks")["node_release_url"] + "/index.json")
    same = [r["version"][1:] for r in releases if r["version"][1:].split(".")[0] == have.split(".")[0]]
    lts = [r["version"][1:] for r in releases if r.get("lts")]
    return max(same + lts, key=version_key)


# ---

def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog="Kinds: " + ", ".join(ADD))
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("check", help="say which releases are newer than the defaults")
    c.add_argument("--strict", action="store_true", help="exit 1 if any is")
    for name, help_text in (("add", "pin a release"), ("verify", "check a pinned release again")):
        a = sub.add_parser(name, help=help_text)
        a.add_argument("kind", choices=sorted(ADD))
        a.add_argument("version")
        a.add_argument("--require-github-digest", action="store_true",
                       help="stop if GitHub's digest for a release asset can't be read")
        if name == "add":
            a.add_argument("--default", action="store_true",
                           help="also make it the role's default, where that's a plain version")
    opts = parser.parse_args()
    try:
        if opts.command == "check":
            return check(opts)
        if opts.command == "verify":
            opts.default = False
            if not is_pinned(opts.kind, opts.version):
                raise Stop(f"{opts.kind} {opts.version} isn't pinned")
        say(f"{opts.kind} {opts.version}:")
        with tempfile.TemporaryDirectory(prefix="update-pins-") as folder:
            ADD[opts.kind](opts.version, folder, opts)
        return 0
    except Stop as e:
        print(f"update-pins: {e}", file=sys.stderr)
        return 1


def is_pinned(kind, version):
    where = {"pandoc": ("pandoc", "pandoc_pins"), "tinytex": ("tex", "tinytex_pins"),
             "tex_snapshot": ("tex", "tex_snapshot_pins"),
             "uv": ("developer", "uv_pins"), "epubcheck": ("validators", "epubcheck_pins"),
             "vnu": ("validators", "vnu_pins"), "verapdf": ("validators", "verapdf_pins"),
             "node": ("browser_checks", "node_pins"), "playwright": ("browser_checks", "playwright_pins"),
             "noto_sans_math": ("fonts", "noto_sans_math_pins"),
             "textbookimprover": ("textbookimprover", "textbookimprover_pins")}
    if kind == "ace":
        return os.path.isdir(role_file("browser_checks", "files", "ace", version))
    role, name = where[kind]
    return version in pins(role).get(name, {})


if __name__ == "__main__":
    sys.exit(main())
