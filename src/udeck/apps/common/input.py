"""Foreground-only native buttons with the existing shell shoulder broker."""

import json

from PySide6.QtCore import QObject, QTimer
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage

from udeck.input import Gamepad
from udeck.pointer import PointerGuard


class AppInput(QObject):
    def __init__(self, controller, app_id, profile):
        super().__init__(controller)
        self.controller, self.app_id = controller, app_id
        self.foreground, self.routed, self.generation = False, False, -1
        self.gamepad = Gamepad(profile, self)
        self.gamepad.action.connect(self.dispatch)
        self.pointer = PointerGuard(self, built_in_only=True)
        self.pointer.shoulder.connect(lambda action: self.dispatch(
            "previous-tab" if action == "previous-page" else "next-tab"))
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.sync)
        self.timer.start()

    def set_foreground(self, active):
        self.foreground, self.routed = active, False
        self.gamepad.set_foreground(active)
        if active:
            self.sync()
        else:
            self.pointer.close()

    def sync(self):
        remote = QDBusInterface("io.github.zhubby.uDeck", "/io/github/zhubby/uDeck",
                                "io.github.zhubby.uDeck.Control", QDBusConnection.sessionBus())
        broker = False
        if remote.isValid():
            reply = remote.call("NativeInputState", self.app_id)
            if reply.type() != QDBusMessage.MessageType.ErrorMessage and reply.arguments():
                try:
                    state = json.loads(reply.arguments()[0])
                    broker = bool(state["available"])
                    if broker:
                        self.route(state["generation"], state["enabled"])
                except (KeyError, TypeError, ValueError):
                    pass
        if broker or not self.foreground:
            self.pointer.close()
        elif not self.pointer.timer.isActive():
            self.pointer.start()

    def route(self, generation, enabled):
        if generation < self.generation:
            return
        self.generation = generation
        self.routed = bool(enabled and self.foreground)
        if enabled:
            self.pointer.close()

    def shoulder(self, generation, action):
        if self.routed and generation == self.generation:
            self.dispatch(action)

    def dispatch(self, action):
        if self.foreground and self.controller.window and self.controller.window.isActive():
            self.controller.dispatch(action)

    def close(self):
        self.timer.stop()
        self.gamepad.close()
        self.pointer.close()
