"""Print bounded wall-clock timing per Ansible task for appliance deployments.

This callback does not inspect task arguments, results, or secrets.
"""
from time import monotonic
from ansible.plugins.callback import CallbackBase


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = "aggregate"
    CALLBACK_NAME = "rfid_task_timing"
    CALLBACK_NEEDS_WHITELIST = True

    def __init__(self):
        super().__init__()
        self._started = None
        self._task = None

    def _finish(self):
        if self._started is not None:
            seconds = monotonic() - self._started
            self._display.display(f"RFID TASK TIMING {seconds:.2f}s {self._task}")
            self._started = None

    def v2_playbook_on_task_start(self, task, is_conditional):
        self._finish()
        self._task = task.get_name().replace("\n", " ")[:120]
        self._started = monotonic()

    def v2_playbook_on_stats(self, stats):
        self._finish()
