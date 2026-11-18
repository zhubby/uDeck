"""
[INPUT]: 依赖窗口焦点、桌面输入授权、物理手柄和指针服务。
[OUTPUT]: 提供前台输入授权、服务变更监听和独立启动回退。
[POS]: 共享应用输入边界；后台停止查询，已授权路由接收桌面推送。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json

from PySide6.QtCore import QObject, QTimer
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage, QDBusServiceWatcher

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
        self.watcher = QDBusServiceWatcher('io.github.zhubby.uDeck', QDBusConnection.sessionBus(),
                                         QDBusServiceWatcher.WatchModeFlag.WatchForOwnerChange, self)
        self.watcher.serviceOwnerChanged.connect(self._broker_changed)

    def _broker_changed(self, name, old_owner, new_owner):
        self.generation, self.routed = -1, False
        self.sync()

    def set_foreground(self, active):
        self.foreground, self.routed = active, False
        self.gamepad.set_foreground(active)
        if active:
            self.sync()
        else:
            self.timer.stop()
            self.pointer.close()

    def sync(self):
        if not self.foreground:
            return
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
        if not broker or not self.routed:
            self.timer.start()
        else:
            self.timer.stop()

    def route(self, generation, enabled):
        if generation < self.generation:
            return
        self.generation = generation
        self.routed = bool(enabled and self.foreground)
        if self.routed:
            self.timer.stop()
        elif self.foreground:
            self.timer.start()
        if enabled:
            self.pointer.close()

    def shoulder(self, generation, action):
        if self.routed and generation == self.generation:
            self.dispatch(action)

    def dispatch(self, action):
        if self.foreground and self.controller.window and self.controller.window.isActive():
            self.controller.dispatch(action)

    def close(self):
        self.foreground, self.routed = False, False
        self.timer.stop()
        self.gamepad.close()
        self.pointer.close()
