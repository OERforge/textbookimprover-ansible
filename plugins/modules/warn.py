# MIT License; see LICENSE at the top of the collection.

DOCUMENTATION = r"""
module: warn
author: TextbookImprover's contributors
short_description: Show a warning, as Ansible shows its own
description:
  - Shows O(msg) as a C([WARNING]) line, and changes nothing. It runs on the
    controller alone (plugins/action/warn.py).
options:
  msg:
    description: The warning.
    type: str
    required: true
"""

EXAMPLES = r"""
- name: Say that the PDF target has no TeX
  oerforge.textbookimprover.warn:
    msg: ti_tex is on, but no TeX is named.
"""

RETURN = r"""
msg:
  description: The warning.
  type: str
  returned: always
"""

if __name__ == "__main__":
    raise SystemExit("warn runs as an action on the controller, not as a module")
