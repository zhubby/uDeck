"""Desktop-side routing, authorized only by compositor-reported active windows.

SPDX-License-Identifier: GPL-2.0-or-later
"""

import hashlib
import os

from PySide6.QtCore import QObject
from PySide6.QtDBus import QDBusConnection, QDBusMessage

from .app_routing import APP_IDS, object_path
from .app_routing import service_name as native_service_name

APP_ID = "io.github.zhubby.uDeck.Terminal"
INTERFACE = APP_ID + ".Control"
OBJECT_PATH = "/io/github/zhubby/uDeck/Terminal"


def service_name():
    if os.environ.get("WAYLAND_DISPLAY"):
        identity = "wayland:" + os.environ["WAYLAND_DISPLAY"]
    elif os.environ.get("DISPLAY"):
        identity = "x11:" + os.environ["DISPLAY"]
    else:
        identity = "session:" + os.environ.get("XDG_SESSION_ID", "headless")
    return APP_ID + ".Session_" + hashlib.sha256(identity.encode()).hexdigest()[:16]


class TerminalInputBroker(QObject):
    def __init__(self, windows, pointer, sender=None, app_id=APP_ID):
        super().__init__()
        self.generation = 0
        self.active_id = ""
        self.enabled = False
        self.available = bool(windows and pointer)
        self.pointer = pointer
        self.sender = sender or self._send
        self.app_id = app_id
        if self.available:
            windows.changed.connect(self.update)
            windows.failed.connect(lambda error: self.update([]))
            pointer.shoulder.connect(self.shoulder)

    def update(self, windows):
        active = next((entry for entry in windows if entry.get("active") and entry.get("appId") == self.app_id), None)
        identifier = active["id"] if active else ""
        if identifier == self.active_id:
            return
        self.active_id = identifier
        self.generation += 1
        self.enabled = bool(identifier)
        self.sender("Route", [self.generation, self.enabled])

    def state(self):
        return {"available": self.available, "generation": self.generation, "enabled": self.enabled}

    def shoulder(self, action):
        if self.enabled and self.active_id and action in ("previous-page", "next-page"):
            self.sender("Shoulder", [self.generation, "previous-tab" if action == "previous-page" else "next-tab"])

    def _send(self, method, arguments):
        message = QDBusMessage.createMethodCall(native_service_name(self.app_id), object_path(self.app_id), self.app_id + ".Control", method)
        message.setArguments(arguments)
        QDBusConnection.sessionBus().asyncCall(message)


class SuiteInputBroker:
    def __init__(self, windows, pointer):
        self.brokers = {app_id: TerminalInputBroker(windows, pointer, app_id=app_id)
                        for app_id in APP_IDS.values()}

    def state(self, app_id):
        broker = self.brokers.get(app_id)
        return broker.state() if broker else {"available": False}
