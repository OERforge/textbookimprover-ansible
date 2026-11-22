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
  - Takes the result of C(ansible.builtin.get_url), or of C(curl) run with
    C(--fail) and C(--write-out %{http_code}), as a task's C(until) sees it.
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
