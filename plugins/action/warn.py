# MIT License; see LICENSE at the top of the collection.
# The action for oerforge.textbookimprover.warn; its documentation is in
# plugins/modules/warn.py, where Ansible looks for it.

from ansible.plugins.action import ActionBase


class ActionModule(ActionBase):
    TRANSFERS_FILES = False
    _VALID_ARGS = frozenset(("msg",))

    def run(self, tmp=None, task_vars=None):
        result = super().run(tmp, task_vars)
        msg = self._task.args.get("msg")
        if not isinstance(msg, str) or not msg.strip():
            result.update(failed=True, msg="warn needs msg, a line of text")
            return result
        result.update(changed=False, msg=msg, warnings=[msg])
        return result
