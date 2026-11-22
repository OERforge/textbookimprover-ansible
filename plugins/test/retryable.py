# MIT License; see LICENSE at the top of the collection.

DOCUMENTATION = r"""
name: retryable
author: TextbookImprover's contributors
short_description: Whether a download failed in a way that may pass
description:
  - True for a download that got no answer, lost its connection, was cut
    short, or was answered 408, 429, 500, 502, 503, or 504; false for one that
    succeeded or failed any other way, a refused or untrusted certificate among
    them.
  - Takes the result of C(ansible.builtin.get_url), of C(ansible.builtin.git),
    or of C(curl) run with C(--fail) and C(--write-out %{http_code}), as a
    task's C(until) sees it.
  - With ansible-core 2.16 a body cut short is reported only as a checksum
    that doesn't match, so a checksum that doesn't match is tried again too.
    The download is checked again each time, so nothing unchecked is kept,
    and a file that's really wrong fails the same way at the last try.
options:
  _input:
    description: A download task's result.
    type: dict
    required: true
"""

EXAMPLES = r"""
- name: Download Pandoc, refused unless its SHA-256 matches
  ansible.builtin.get_url:
    url: "{{ url }}"
    dest: "{{ dest }}"
    checksum: "sha256:{{ sha256 }}"
  register: pandoc_got
  until: pandoc_got is not oerforge.textbookimprover.retryable
  retries: "{{ ti_download_retries }}"
  delay: "{{ ti_download_delay }}"
"""

RETURN = r"""
_value:
  description: Whether to try the download again.
  type: bool
"""

import os
import re
from collections.abc import Mapping

# The answers that say "not now": a timeout, too many requests, or the
# server's own trouble.
STATUSES = frozenset({408, 429, 500, 502, 503, 504})

# get_url's messages for a request that got no answer, or a body cut short,
# as ansible-core 2.16 and 2.21 word them (fetch_url's and url_get's).
GET_URL_MESSAGES = (
    # no answer in time, or the connection closed before one
    "Connection failure:",
    # a connection refused, or a name not found; a TLS error, an untrusted
    # certificate among them, is this too, and is left out below
    "Request failed: <urlopen error",
    # the connection lost, or timed out, partway through the body
    "failed to create temporary content file:",
    # a body cut short, in the ansible-core releases that check its length
    "Incomplete read",
    # a body cut short, in those that don't, or a file that's wrong
    "The checksum for ",
)

# curl's exit codes for the same: a name not found (6), no connection (7),
# HTTP/2's framing (16), a body cut short (18), a timeout (28), an empty
# answer (52), a send or a receive that failed (55, 56), and an HTTP/2 stream
# reset (92). 22 is an HTTP error, decided by its status.
CURL_CODES = frozenset({6, 7, 16, 18, 28, 52, 55, 56, 92})


# git's reports, as git 2.43 (Ubuntu 24.04's) and 2.47 (Debian 13's), built
# with GnuTLS, word them. A smart-HTTP request that failed names curl's code,
# and its HTTP status where there was one: "RPC failed; curl 56 GnuTLS recv
# error (-110)", "RPC failed; HTTP 503 curl 22 ...". Any other request gives
# curl's own message after "unable to access '<url>': ", or after "Unable to
# get pack file <url>" in the dumb protocol.
GIT_RPC = re.compile(r"RPC failed; (?:HTTP (\d{3}) )?curl (\d+)")
GIT_HTTP = re.compile(r"The requested URL returned error: (\d{3})")
GIT_MESSAGES = (
    # the connection closed before an answer, or partway through one
    "GnuTLS recv error (-110)",
    # the connection reset
    "Recv failure:",
    # a connection refused
    "Failed to connect to",
    # a name not found
    "Could not resolve host:",
    # under git's low-speed limit (GIT_HTTP_LOW_SPEED_LIMIT and _TIME)
    "Operation too slow",
)


def _is_git(result):
    cmd = result.get("cmd")
    if isinstance(cmd, str):
        cmd = cmd.split()
    return bool(cmd) and os.path.basename(str(cmd[0])) == "git"


def _git_retryable(result):
    text = "%s\n%s" % (result.get("msg", ""), result.get("stderr", ""))
    rpc = GIT_RPC.search(text)
    if rpc:
        if rpc.group(1):
            return int(rpc.group(1)) in STATUSES
        return int(rpc.group(2)) in CURL_CODES
    http = GIT_HTTP.search(text)
    if http:
        return int(http.group(1)) in STATUSES
    return any(m in text for m in GIT_MESSAGES)


def _status(value):
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def retryable(result):
    """Whether a download task's result is worth another try."""
    if not isinstance(result, Mapping):
        raise TypeError("retryable takes a task's result, not %s" % type(result).__name__)
    if not result.get("failed"):
        return False

    if _is_git(result):
        return _git_retryable(result)

    if "rc" in result:
        rc = result["rc"]
        if rc in CURL_CODES:
            return True
        if rc == 22:
            return _status(result.get("stdout", "")) in STATUSES
        return False

    status = _status(result.get("status_code", ""))
    if status is not None and status >= 400:
        return status in STATUSES

    msg = str(result.get("msg", ""))
    if msg.startswith("Request failed: <urlopen error [SSL"):
        return False
    return msg.startswith(GET_URL_MESSAGES)


class TestModule:
    def tests(self):
        return {"retryable": retryable}
