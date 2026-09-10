"""Small Tk resize coalescer used by heavyweight canvas views."""

from __future__ import annotations


class TkResizeScheduler:
    def __init__(self, widget):
        self.widget = widget
        self._pending = {}

    def request(self, key, delay_ms, callback):
        previous = self._pending.pop(key, None)
        if previous is not None:
            try:
                self.widget.after_cancel(previous)
            except Exception:
                pass

        def run():
            self._pending.pop(key, None)
            callback()

        self._pending[key] = self.widget.after(max(1, int(delay_ms)), run)
