"""Foreground input ownership shared with uDeck, with local stock-device fallback.

SPDX-License-Identifier: GPL-2.0-or-later
"""

import json

from PySide6.QtCore import QObject, QTimer
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage, QDBusServiceWatcher

from ..input import Gamepad
from ..pointer import PointerGuard


class TerminalInput(QObject):
    def __init__(self, coordinator, profile):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.foreground = False
        self.generation = -1
        self.routed = False
        self.broker_present = False
        self.status = {}
        self.gamepad = Gamepad(profile, self)
        self.gamepad.action.connect(self.dispatch)
        self.gamepad.status.connect(self.status.update)
        self.pointer = PointerGuard(self, built_in_only=True)
        self.pointer.shoulder.connect(lambda action: self.dispatch("previous-tab" if action == "previous-page" else "next-tab"))
        self.pointer.status.connect(self.status.update)
        self.watcher = QDBusServiceWatcher("io.github.zhubby.uDeck", QDBusConnection.sessionBus(),
                                         QDBusServiceWatcher.WatchModeFlag.WatchForOwnerChange, self)
        self.watcher.serviceOwnerChanged.connect(self._broker_changed)

    def _broker_changed(self, name, old_owner, new_owner):
        self.generation = -1
        self.routed = False
        self.sync()

    def set_foreground(self, foreground):
        # Invalidate queued broker events immediately on every focus transition.
        if foreground != self.foreground:
            self.routed = False
        self.foreground = foreground
        self.gamepad.set_foreground(foreground)
        if not foreground:
            self.pointer.close()
        else:
            self.sync()

    def sync(self):
        remote = QDBusInterface("io.github.zhubby.uDeck", "/io/github/zhubby/uDeck",
                                "io.github.zhubby.uDeck.Control", QDBusConnection.sessionBus())
        # A broker exists only when the desktop is actually holding the mouse.
        self.broker_present = False
        self.routed = False
        if remote.isValid():
            result = remote.call("TerminalInputState")
            if result.type() != QDBusMessage.MessageType.ErrorMessage and result.arguments():
                try:
                    state = json.loads(result.arguments()[0])
                    self.broker_present = bool(state["available"])
                    if self.broker_present:
                        self.route(state["generation"], state["enabled"])
                except (ValueError, KeyError, TypeError):
                    pass
        if self.broker_present or not self.foreground:
            self.pointer.close()
        elif not self.pointer.timer.isActive():
            self.pointer.start()
        if self.foreground and self.broker_present and not self.routed:
            # Qt focus and foreign-toplevel notifications can arrive in either
            # order. Retry once; further compositor changes arrive through Route.
            QTimer.singleShot(100, self._retry_route)

    def _retry_route(self):
        if self.foreground and self.broker_present and not self.routed:
            self.sync_once()

    def sync_once(self):
        remote = QDBusInterface("io.github.zhubby.uDeck", "/io/github/zhubby/uDeck",
                                "io.github.zhubby.uDeck.Control", QDBusConnection.sessionBus())
        reply = remote.call("TerminalInputState")
        if reply.type() != QDBusMessage.MessageType.ErrorMessage and reply.arguments():
            try:
                data = json.loads(reply.arguments()[0])
                self.route(data["generation"], data["enabled"])
            except (TypeError, ValueError, KeyError):
                pass

    def route(self, generation, enabled):
        if type(generation) is not int or generation < self.generation:
            return
        self.generation = generation
        self.routed = bool(enabled and self.foreground)
        if enabled:
            self.pointer.close()

    def shoulder(self, generation, action):
        if self.routed and self.foreground and generation == self.generation and action in ("previous-tab", "next-tab"):
            self.dispatch(action)

    def dispatch(self, action):
        active = next((entry for entry in self.coordinator.windows if entry["window"].isActive()), None)
        if self.foreground and active:
            active["controller"].dispatch(action)

    def diagnostics(self):
        return {"enabled": True, "foreground": self.foreground, "broker": self.broker_present,
                "generation": self.generation, "routed": self.routed, **self.status}

    def close(self):
        self.gamepad.close()
        self.pointer.close()
