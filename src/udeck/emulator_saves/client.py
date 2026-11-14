"""Asynchronous Qt bridge to the persistent user save service."""

import asyncio
import json
import subprocess
import sys
import uuid

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from . import OBJECT_PATH, SERVICE, data_directory
from .sync import Rclone, clean_error


class TaskSignals(QObject):
    done = Signal(str, object, object)


class SaveTask(QRunnable):
    def __init__(self, identifier, operation):
        super().__init__()
        self.identifier, self.operation = identifier, operation
        self.signals = TaskSignals()

    def run(self):
        try:
            value = self.operation()
        except Exception as error:
            self.signals.done.emit(self.identifier, None, error)
        else:
            self.signals.done.emit(self.identifier, value, None)


async def service_call(member, payload=None):
    from dbus_next import Message
    from dbus_next.aio import MessageBus

    bus = await MessageBus().connect()
    try:
        message = Message(destination=SERVICE, path=OBJECT_PATH, interface=SERVICE,
                          member=member, signature="s" if payload is not None else "",
                          body=[json.dumps(payload)] if payload is not None else [])
        reply = await asyncio.wait_for(bus.call(message), 110 if member == "Configure" else 15)
        if reply.error_name:
            raise OSError(reply.error_name + ": " + clean_error(str(reply.body)))
        return json.loads(reply.body[0])
    finally:
        bus.disconnect()


async def configure_service(payload):
    previous = await service_call("Status")
    enabled = payload.get("enabled", previous["enabled"])

    def autostart(value):
        command = ["systemctl", "--user", "enable" if value else "disable", "udeck-emulator-saves.service"]
        configured = subprocess.run(command, capture_output=True, text=True, timeout=10)
        if configured.returncode:
            raise OSError(clean_error(configured.stderr) or "Could not configure the background save service")

    changed = enabled != previous["enabled"]
    if changed:
        autostart(enabled)
    try:
        result = await service_call("Configure", payload)
        if result.get("error"):
            raise OSError(result["error"])
        return result
    except Exception:
        if changed:
            autostart(previous["enabled"])
        raise


class SaveCloudClient(QObject):
    changed = Signal(object)

    def __init__(self, directory=None, parent=None):
        super().__init__(parent)
        self.root = data_directory(directory)
        self.state = {"enabled": False, "remote": "", "directory": "", "phase": "disabled",
                      "error": "", "lastSync": 0, "progress": {}, "conflicts": []}
        try:
            self.state.update(json.loads((self.root / "emulator-cloud.json").read_text()))
            if self.state["enabled"]:
                self.state["phase"] = "idle"
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError):
            self.state.update(phase="error", error="The cloud configuration is damaged")
        self.tasks = {}
        self.closed = False
        self.polling = False
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)

    def request(self, member, payload=None, callback=None):
        if self.closed:
            return

        def operation():
            if member == "Remotes":
                return {"remotes": asyncio.run(Rclone().remotes())}
            if member == "TestConnection":
                async def check():
                    transport = Rclone()
                    if payload["remote"] not in await transport.remotes():
                        raise ValueError("Choose an existing rclone remote")
                    await transport.run("lsf", payload["remote"] + ":" + payload["directory"], "--max-depth=1")
                    return {"connected": True}
                return asyncio.run(check())
            if sys.platform != "linux":
                raise OSError("The background save service requires a Linux user session")
            return asyncio.run(configure_service(payload) if member == "Configure" else service_call(member, payload))

        identifier = uuid.uuid4().hex
        task = SaveTask(identifier, operation)
        self.tasks[identifier] = (task, member, callback)
        task.signals.done.connect(self.completed)
        self.pool.start(task)

    def completed(self, identifier, result, error):
        task = self.tasks.pop(identifier, None)
        if not task or self.closed:
            return
        _, member, callback = task
        if member == "Status":
            self.polling = False
        if error:
            result = {"phase": "error", "error": clean_error(str(error))}
        if member in ("Configure", "SyncNow", "Status"):
            self.state.update(result)
            self.changed.emit(dict(self.state))
        if callback:
            callback(result)

    def refresh(self):
        if self.state["enabled"] and not self.polling and not self.closed:
            self.polling = True
            self.request("Status")

    def close(self):
        self.closed = True
