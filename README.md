# textbookimprover-ansible

Ansible playbooks that set up a machine to use or develop [TextbookImprover](https://github.com/OERforge/textbookimprover): Pandoc, TextbookImprover itself, LuaLaTeX for tagged PDFs, the validators, and the rest of what its [installation page](https://github.com/OERforge/textbookimprover/blob/main/docs/installation.md) asks for.

**Nothing here works yet.** This is the start of the collection; the roles come next.

Licensed MIT. See `LICENSE`.

## What it will do

- **Follow TextbookImprover's installation page**, which stays the one description of what TextbookImprover needs. Where the playbooks find the page wrong or incomplete, the fix goes into the page.
- **Run on Ubuntu 24.04 LTS, Ubuntu 26.04 LTS, and Debian 13**, on a machine of their own or under WSL 2, x86_64 first. Other distributions come later, so nothing particular to one distribution goes in a task.
- **Install into one user's home folder**, so that updating needs no `sudo`. System packages come from `apt`, and that step alone asks for a password.
- **Check every download before it's used**: each is a release by default, checked against a SHA-256 written into the collection in advance, and against the publisher's signature where there is one.
- **Offer two profiles**: `user`, for converting books, and `developer`, for working on TextbookImprover. Either way, TextbookImprover's own test suites are the check that the machine is set up right.
- **Start from one script**, `bootstrap.sh`, for a person who has never used Ansible.

It's an Ansible collection, `oerforge.textbookimprover`, using only the modules that come with ansible-core.
