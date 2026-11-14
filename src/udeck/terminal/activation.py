"""Restore the most recently focused terminal through the Wayland compositor.

SPDX-License-Identifier: GPL-2.0-or-later
"""


class RecentWindowActivation:
    def __init__(self, windows, app_id):
        self.windows, self.app_id = windows, app_id
        self.recent = []
        self.candidates = set()
        windows.changed.connect(self.update)
        windows.failed.connect(self.clear)
        self.update(windows.entries())

    def clear(self, *_arguments):
        self.recent.clear()
        self.candidates.clear()

    def update(self, rows):
        terminals = [row for row in rows if row.get("appId") == self.app_id and not row.get("parent")]
        self.candidates = {row["id"] for row in terminals}
        self.recent = [identifier for identifier in self.recent if identifier in self.candidates]
        active = [row["id"] for row in terminals if row.get("active")]
        if len(active) == 1:
            self.recent = [identifier for identifier in self.recent if identifier != active[0]] + active

    def activate(self):
        if not self.windows.available:
            return
        # Titles may be identical or change at any time. Only compositor IDs
        # establish focus history; an unobserved group of windows is ambiguous.
        if self.recent:
            identifier = self.recent[-1]
        elif len(self.candidates) == 1:
            identifier = next(iter(self.candidates))
        else:
            return
        try:
            self.windows.request(identifier, "activate")
        except RuntimeError:
            pass  # A window can close between the launch and this request.
