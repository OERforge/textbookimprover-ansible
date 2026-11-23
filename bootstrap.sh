#!/bin/sh
# Set up this machine to use or develop TextbookImprover, with the playbooks
# in the oerforge.textbookimprover collection. Run it in a terminal as the
# person who'll use TextbookImprover:
#
#   sh bootstrap.sh
#
# It asks which setup and which optional parts, saves the answers as an
# inventory, installs ansible-core and git with apt if they're missing,
# fetches the collection, and runs the playbook on this machine. It asks for
# the sudo password once. Run again later, it updates everything; with
# --user-only it needs no password. --help lists the options.
#
# POSIX sh throughout, since it may be started as "sh bootstrap.sh".
#
# All of it is one group, which the shell reads to its end before it runs
# any of it: a copy cut short, by a download that stopped partway, runs
# nothing, and piped into sh, no command it starts can take the rest of the
# script as its input. Nothing goes after the group's closing brace.
{

set -eu

repository=https://github.com/OERforge/textbookimprover-ansible.git
# The collection's releases this copy of the script knows, oldest first, one
# per line: the tag, then the commit it has to be. Until there's one, the
# script uses main. Each run also reads the list in main's copy of this
# script, which a fresh download would give, and takes the releases it adds;
# a tag it gives another commit than this copy knows stops the run. Then the
# chosen release's own copy of the script runs in its place, so its fixes
# come with the release.
releases=''

data_dir=${XDG_DATA_HOME:-$HOME/.local/share}/textbookimprover-ansible
config_dir=${XDG_CONFIG_HOME:-$HOME/.config}/textbookimprover-ansible
inventory=$config_dir/inventory
answers=$inventory/group_vars/all/bootstrap.yml

say() { printf '%s\n' "$*"; }
die() { printf 'bootstrap.sh: %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'EOF'
Usage: sh bootstrap.sh [option...] [-- ansible-playbook option...]

  --profile user|developer  the setup: for converting books (user) or for
                            working on TextbookImprover (developer)
  --reconfigure             ask the questions again and save the new answers
  --yes                     ask no questions: use the saved answers, or the
                            defaults the first time
  --user-only               only the steps in your home folder, which need
                            no sudo password
  --ref REF                 the collection's branch, tag, or commit to use
  --repository URL          where to fetch the collection from
  --collection DIR          use the collection in DIR as it is
  -h, --help                show this

Options after -- go to ansible-playbook, such as -e tex_update=true.
EOF
}

profile='' reconfigure=false yes=false user_only=false ref='' collection=''
while [ $# -gt 0 ]; do
    case $1 in
        --profile|--ref|--repository|--collection)
            [ $# -ge 2 ] || die "$1 needs a value"
            case $1 in
                --profile) profile=$2 ;;
                --ref) ref=$2 ;;
                --repository) repository=$2 ;;
                --collection) collection=$2 ;;
            esac
            shift 2 ;;
        --reconfigure) reconfigure=true; shift ;;
        --yes) yes=true; shift ;;
        --user-only) user_only=true; shift ;;
        -h|--help) usage; exit 0 ;;
        --) shift; break ;;
        *) die "there's no option $1 (--help lists them)" ;;
    esac
done
case $profile in
    ''|user|developer) ;;
    *) die "--profile is user or developer, not $profile" ;;
esac

# --- Before anything is installed: who, where, and on what.

[ "$(id -u)" -ne 0 ] ||
    die "run this as the person who'll use TextbookImprover, not as root: it installs into that person's home folder, and asks for sudo itself"
[ -r /etc/os-release ] || die "there's no /etc/os-release to say what this system is"
# shellcheck source=/dev/null
platform=$(. /etc/os-release && printf '%s %s|%s' "${ID:-}" "${VERSION_ID:-}" "${PRETTY_NAME:-}")
case ${platform%%|*} in
    'ubuntu 24.04'|'ubuntu 26.04'|'debian 13') ;;
    *) die "this is ${platform#*|}; the playbooks are for Ubuntu 24.04, Ubuntu 26.04, and Debian 13" ;;
esac
[ "$(uname -m)" = x86_64 ] || die "this machine is $(uname -m); the playbooks are for x86_64"

if (: </dev/tty) 2>/dev/null; then
    terminal=true
else
    terminal=false
fi

# --- The questions, first, so the rest can run unattended.

# ask_yes_no QUESTION y|n: sets answer to true or false.
ask_yes_no() {
    if [ "$2" = y ]; then choices=Y/n; else choices=y/N; fi
    while :; do
        printf '%s [%s] ' "$1" "$choices" >/dev/tty
        IFS= read -r reply </dev/tty || reply=''
        [ -n "$reply" ] || reply=$2
        case $reply in
            [Yy]|[Yy][Ee][Ss]) answer=true; return ;;
            [Nn]|[Nn][Oo]) answer=false; return ;;
        esac
        say 'Please answer y or n.' >/dev/tty
    done
}

# saved NAME: the value bootstrap.sh saved for a setting, or nothing.
saved() {
    if [ -f "$answers" ]; then
        sed -n "s/^$1: //p" "$answers" || true
    fi
}

# releases_in: the release list of the copy of this script on standard
# input, one "tag commit" a line, as it's written above: nothing for a copy
# with none. It's read as text, never run.
releases_in() {
    awk '
        !on && /^releases=\047/ { on = 1; sub(/^releases=\047/, "") }
        on {
            end = index($0, "\047")
            line = end ? substr($0, 1, end - 1) : $0
            gsub(/^[ \t]+|[ \t]+$/, "", line)
            if (line != "") print line
            if (end) exit
        }'
}

saved_profile=$(cat "$config_dir/profile" 2>/dev/null || true)
if [ ! -f "$answers" ] || [ -z "$saved_profile" ] || $reconfigure; then
    tex=$(saved ti_tex) validators=$(saved ti_validators) browser=$(saved ti_browser_checks)
    fonts=$(saved ti_fonts)
    : "${tex:=true}" "${validators:=true}" "${browser:=true}" "${fonts:=false}"
    profile_given=false
    [ -z "$profile" ] || profile_given=true
    [ -n "$profile" ] || profile=${saved_profile:-user}
    if $terminal && ! $yes; then
        if ! $profile_given; then
            if [ "$profile" = developer ]; then default=2; else default=1; fi
            cat >/dev/tty <<'EOF'
Which setup is this machine for?
  1  converting books with TextbookImprover (user)
  2  working on TextbookImprover itself (developer): a clone of its main
     branch, the full TeX Live, three Pandocs, LibreOffice, and what its
     test suites need
EOF
            while :; do
                printf 'Choose 1 or 2 [%s] ' "$default" >/dev/tty
                IFS= read -r reply </dev/tty || reply=''
                case ${reply:-$default} in
                    1) profile=user; break ;;
                    2) profile=developer; break ;;
                esac
            done
        fi
        yn() { if [ "$1" = true ]; then echo y; else echo n; fi; }
        ask_yes_no 'Install TeX, for PDF output?' "$(yn "$tex")"; tex=$answer
        ask_yes_no 'Install the validators (epubcheck, the Nu checker, veraPDF)?' "$(yn "$validators")"; validators=$answer
        ask_yes_no 'Install the browser checks (Playwright'\''s Chromium and Ace), for --wcag?' "$(yn "$browser")"; browser=$answer
        ask_yes_no 'Install the fonts for OpenStax'\''s books (Noto Sans Math)?' "$(yn "$fonts")"; fonts=$answer
    fi
    save_answers=true
else
    save_answers=false
    [ -n "$profile" ] || profile=$saved_profile
fi

# --- What apt has to install, and the sudo password, asked for once.

# core_ok COMMAND: whether that ansible-playbook is ansible-core 2.16 or later.
core_ok() {
    "$1" --version 2>/dev/null |
        sed -n '1s/.*core \([0-9]*\)\.\([0-9]*\).*/\1 \2/p' |
        awk '{ ok = ($1 > 2 || ($1 == 2 && $2 >= 16)) } END { exit !ok }'
}

need=''
command -v git >/dev/null 2>&1 || need="$need git"
if command -v ansible-playbook >/dev/null 2>&1 && core_ok ansible-playbook; then
    playbook_command=ansible-playbook
else
    need="$need ansible-core"
    playbook_command=/usr/bin/ansible-playbook
fi
[ -s /etc/ssl/certs/ca-certificates.crt ] || need="$need ca-certificates"

password='' sudo_mode=none
if [ -n "$need" ] || ! $user_only; then
    command -v sudo >/dev/null 2>&1 ||
        die "sudo isn't installed, which the system packages need; with them in place, --user-only needs no sudo"
    if sudo -k -n true 2>/dev/null; then
        sudo_mode=no-password
    else
        if [ -n "${TI_BOOTSTRAP_SUDO_ON_STDIN:-}" ] && [ ! -t 0 ]; then
            # From the copy of this script that handed over to this one,
            # which asked for it, through a pipe: never a file or a command
            # line.
            IFS= read -r password || password=''
            printf '%s\n' "$password" | sudo -S -k -p '' true >/dev/null 2>&1 ||
                die "sudo didn't take the password the other copy of bootstrap.sh gave"
        fi
        if [ -z "$password" ]; then
            $terminal ||
                die "sudo needs a password, and there's no terminal to ask for it in: run this in a terminal"
            tries=0
            while :; do
                printf '[sudo] password for %s, asked once, for apt and the system packages: ' "$(id -un)" >/dev/tty
                tty_settings=$(stty -g </dev/tty)
                trap 'stty "$tty_settings" </dev/tty; exit 130' HUP INT TERM
                stty -echo </dev/tty
                IFS= read -r password </dev/tty || password=''
                stty "$tty_settings" </dev/tty
                trap - HUP INT TERM
                printf '\n' >/dev/tty
                if said=$(printf '%s\n' "$password" | sudo -S -k -p '' true 2>&1 >/dev/null); then
                    break
                fi
                # Given the right password, sudo says when the account isn't
                # allowed to use it; another try wouldn't change that.
                case $said in
                    *sudoers*|*'not allowed'*) die "sudo said: $(printf '%s\n' "$said" | tail -n 1)" ;;
                esac
                tries=$((tries + 1))
                [ "$tries" -lt 3 ] || die "sudo didn't take the password three times"
                say "sudo didn't take that; try again." >/dev/tty
            done
        fi
        sudo_mode=password
    fi
fi

# as_root COMMAND...: run a command with sudo, giving it the password if
# it needs one; -k makes sudo read it every time, so the command's own
# input never holds it.
as_root() {
    if [ "$sudo_mode" = password ]; then
        printf '%s\n' "$password" | sudo -S -k -p '' "$@"
    else
        sudo -n "$@"
    fi
}

if [ -n "$need" ]; then
    say "Installing$need with apt."
    # Its errors still show; the list of what it unpacks doesn't.
    # shellcheck disable=SC2086 # $need is a list of names
    as_root env DEBIAN_FRONTEND=noninteractive sh -c \
        'apt-get -qq update && apt-get -qq -y -o DPkg::Lock::Timeout=300 install --no-install-recommends "$@"' \
        sh $need >/dev/null
fi

# --- The collection.

if [ -n "$collection" ]; then
    [ -f "$collection/galaxy.yml" ] || die "$collection has no galaxy.yml, so it isn't a collection"
    collection=$(cd "$collection" && pwd)
    if ! grep -q '^namespace: *oerforge *$' "$collection/galaxy.yml" ||
        ! grep -q '^name: *textbookimprover *$' "$collection/galaxy.yml"; then
        die "$collection isn't the oerforge.textbookimprover collection"
    fi
    collections_path=$(mktemp -d)
    trap 'rm -rf "$collections_path"' EXIT
    mkdir -p "$collections_path/ansible_collections/oerforge"
    ln -s "$collection" "$collections_path/ansible_collections/oerforge/textbookimprover"
    say "Using the collection in $collection as it is."
else
    collections_path=$data_dir
    clone=$data_dir/ansible_collections/oerforge/textbookimprover
    if [ -d "$clone/.git" ]; then
        [ -z "$(git -C "$clone" status --porcelain)" ] ||
            die "$clone, bootstrap.sh's own copy of the collection, has changes in it, which it won't overwrite; --collection runs a copy of your own"
        git -C "$clone" remote set-url origin "$repository"
        # A tag that's moved since the clone last fetched it is refused here
        # ("would clobber existing tag"), and stops the run.
        fetched=$(git -C "$clone" fetch --prune --tags origin 2>&1) ||
            die "fetching the collection from $repository failed: $(printf '%s\n' "$fetched" | tail -n 2 | sed 's/^ *//' | tr '\n' ' ')"
    elif [ -e "$clone" ]; then
        die "$clone is there but isn't a clone of the collection"
    else
        mkdir -p "$(dirname "$clone")"
        git clone --quiet --no-checkout "$repository" "$clone"
    fi

    # The releases known: this copy's, and those main's copy of this script
    # adds, which is what a fresh download would know. A tag main's list
    # gives another commit than this copy's stops the run, so a release this
    # copy knows can't be moved; a list that isn't one stops it too.
    main_releases=$(git -C "$clone" show refs/remotes/origin/main:bootstrap.sh 2>/dev/null | releases_in) ||
        main_releases=''
    bad=$(printf '%s\n' "$main_releases" | grep -Ev '^$|^v[0-9][0-9A-Za-z._-]* [0-9a-f]{40}$' || true)
    [ -z "$bad" ] ||
        die "main's bootstrap.sh lists a release as \"$(printf '%s\n' "$bad" | head -n 1)\", which isn't a tag and a commit: stopping"
    moved=$(printf '%s\n%s\n' "$releases" "$main_releases" |
        awk 'NF == 2 { if ($1 in c && c[$1] != $2) { print $1; exit } c[$1] = $2 }')
    [ -z "$moved" ] ||
        die "main's bootstrap.sh gives release $moved another commit than this copy does: stopping"
    known=$(printf '%s\n%s\n' "$releases" "$main_releases" | awk 'NF == 2 && !seen[$1]++' | sort -V -k 1,1)

    if [ -z "$ref" ]; then
        ref=$(printf '%s\n' "$known" | awk 'NF { tag = $1 } END { print tag }')
        [ -n "$ref" ] || ref=main
    fi
    commit=$(git -C "$clone" rev-parse --verify --quiet "refs/remotes/origin/$ref^{commit}") ||
        commit=$(git -C "$clone" rev-parse --verify --quiet "refs/tags/$ref^{commit}") ||
        commit=$(git -C "$clone" rev-parse --verify --quiet "$ref^{commit}") ||
        die "the collection has no branch, tag, or commit $ref"
    pinned=$(printf '%s\n' "$known" | awk -v tag="$ref" '$1 == tag { print $2 }')
    if [ -n "$pinned" ] && [ "$commit" != "$pinned" ]; then
        die "the collection's tag $ref is at $commit, not at $pinned as bootstrap.sh's list expects: stopping"
    fi
    git -C "$clone" checkout --quiet --detach "$commit"
    short=$(git -C "$clone" rev-parse --short HEAD)
    if [ -n "$pinned" ]; then
        say "The collection: release $ref, at the commit bootstrap.sh's list expects ($short)."
    elif [ -z "$known" ] && [ "$ref" = main ]; then
        say "The collection: main, at $short; there's no release yet to check it against."
    else
        say "The collection: $ref, at $short, which bootstrap.sh's list has no commit to check against."
    fi
fi

# --- The inventory: bootstrap.sh's answers in group_vars, which it rewrites
# with --reconfigure, and the person's own settings in host_vars, which come
# after them and which it never changes.

mkdir -p "$inventory/group_vars/all" "$inventory/host_vars"
if [ ! -f "$inventory/hosts.yml" ]; then
    cat > "$inventory/hosts.yml" <<'EOF'
# The machine bootstrap.sh sets up: this one.
all:
  hosts:
    localhost:
      ansible_connection: local
EOF
fi
if [ ! -f "$inventory/host_vars/localhost.yml" ]; then
    cat > "$inventory/host_vars/localhost.yml" <<'EOF'
# Settings of your own for the playbooks, such as
#
#   ti_libreoffice: true
#   pandoc_versions: ["3.14", "3.13"]
#
# They come after bootstrap.sh's answers (group_vars/all/bootstrap.yml), so
# they win over them, and bootstrap.sh never changes this file. The README's
# Settings section lists them.
EOF
fi
if $save_answers; then
    cat > "$answers" <<EOF
# bootstrap.sh's answers, which it rewrites when run with --reconfigure.
# Settings of your own go in host_vars/localhost.yml, which wins over these.
ti_tex: $tex
ti_validators: $validators
ti_browser_checks: $browser
ti_fonts: $fonts
EOF
    printf '%s\n' "$profile" > "$config_dir/profile"
fi

# --- The chosen release's own copy of this script, in this one's place,
# once: its fixes come with it, and it knows what the release's playbooks
# ask. It's given the answers (saved above), and the password through a
# pipe. A copy that's the same, or none in that commit, changes nothing.

if [ -z "$collection" ] && [ -z "${TI_BOOTSTRAP_HANDED_OVER:-}" ]; then
    handover=$(mktemp -d)
    if git -C "$clone" show "$commit:bootstrap.sh" >"$handover/bootstrap.sh" 2>/dev/null &&
        ! { [ -f "$0" ] && cmp -s "$0" "$handover/bootstrap.sh"; }; then
        say "Handing over to the bootstrap.sh of $ref ($short)."
        if $user_only; then set -- --user-only -- "$@"; else set -- -- "$@"; fi
        set -- --yes --profile "$profile" --ref "$ref" --repository "$repository" "$@"
        status=0
        if [ "$sudo_mode" = password ]; then
            printf '%s\n' "$password" |
                TI_BOOTSTRAP_HANDED_OVER=1 TI_BOOTSTRAP_SUDO_ON_STDIN=1 sh "$handover/bootstrap.sh" "$@" ||
                status=$?
        else
            TI_BOOTSTRAP_HANDED_OVER=1 sh "$handover/bootstrap.sh" "$@" </dev/null || status=$?
        fi
        password=''
        rm -rf "$handover"
        exit "$status"
    fi
    rm -rf "$handover"
fi

# --- The play.

set -- -i "$inventory" "oerforge.textbookimprover.$profile" "$@"
if $user_only; then
    set -- "$@" --tags user
fi
# The collection is found where bootstrap.sh put it and nowhere else; and
# the folder it runs in is its own, so no ansible.cfg in the folder this
# was started from is read.
ANSIBLE_COLLECTIONS_PATH=$collections_path
export ANSIBLE_COLLECTIONS_PATH
cd "$config_dir"
say "Running the $profile playbook. It can take a while the first time."
if [ "$sudo_mode" = password ]; then
    # "-" is standard input, from which ansible-core trims only the newline.
    printf '%s\n' "$password" | "$playbook_command" --become-password-file - "$@" ||
        die "the play stopped; its last lines say why. Running bootstrap.sh again carries on."
else
    "$playbook_command" "$@" ||
        die "the play stopped; its last lines say why. Running bootstrap.sh again carries on."
fi
password=''

# --- What comes next.

say ''
# The play notes the file its shell settings went in, which ti_shell_rc in
# the person's host_vars can make one of its own.
shell_file=$(cat "$HOME/.config/textbookimprover-ansible/shell-file" 2>/dev/null || true)
case $shell_file in
    '' | "$HOME/.bashrc")
        say 'Done. Open a new terminal: the play added settings to ~/.bashrc that a new one'
        say 'reads, among them T, TextbookImprover'\''s folder, where docs/first-run.md walks'
        say 'through converting a first book.'
        ;;
    *)
        say "Done. The play's settings are in $shell_file, not ~/.bashrc:"
        say "run . $shell_file in a terminal to have them there, among them"
        say 'T, TextbookImprover'\''s folder, where docs/first-run.md walks through'
        say 'converting a first book.'
        ;;
esac
if grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null; then
    say 'Keep your books under your Linux home folder, in ~/projects/ say, rather'
    say 'than under /mnt/c, where a conversion is noticeably slower.'
fi
# shellcheck disable=SC2088 # a ~ to show, not to expand
case $inventory in
    "$HOME"/*) shown="~/${inventory#"$HOME"/}" ;;
    *) shown=$inventory ;;
esac
say ''
say "The settings are in $shown/:"
say 'bootstrap.sh'\''s answers in group_vars/all/bootstrap.yml, and settings of'
say 'your own in host_vars/localhost.yml, which win over them. To update'
say 'everything later, run bootstrap.sh again; with --user-only, it needs no'
say 'password.'

}
