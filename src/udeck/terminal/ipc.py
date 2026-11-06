"""Private, memory-only requests on the caller's graphical session bus.

SPDX-License-Identifier: GPL-2.0-or-later
"""

import json

from PySide6.QtCore import QObject, Slot
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage

from ..terminal_routing import service_name as service_name
from . import INTERFACE, OBJECT_PATH
from .core import LaunchRequest


def interface():
    return QDBusInterface(service_name(), OBJECT_PATH, INTERFACE, QDBusConnection.sessionBus())


def forward(request):
    remote = interface()
    if not remote.isValid():
        return False
    result = remote.call("Open", request.to_json())
    if result.type() == QDBusMessage.MessageType.ErrorMessage:
        raise RuntimeError(f"终端进程未响应：{result.errorMessage()}")
    error = result.arguments()[0] if result.arguments() else "无效的终端响应"
    if error:
        raise RuntimeError(str(error))
    return True


class TerminalControl(QObject):
    def __init__(self, coordinator):
        super().__init__()
        self.coordinator = coordinator

    @Slot(str, result=str)
    def Open(self, payload):
        try:
            if len(payload) > 2 * 1024 * 1024:
                raise ValueError("窗口请求过大")
            request = LaunchRequest.from_json(payload)
            request.executable()
            self.coordinator.open(request)
            return ""
        except (ValueError, OSError, RuntimeError) as error:
            return str(error)

    @Slot(result=str)
    def Diagnose(self):
        return json.dumps(self.coordinator.diagnostics(), ensure_ascii=False)

    @Slot(int, str)
    def Shoulder(self, generation, action):
        self.coordinator.shoulder(generation, action)

    @Slot(int, bool)
    def Route(self, generation, enabled):
        self.coordinator.route(generation, enabled)
