"""
[INPUT]: 依赖会话 D-Bus、窗口元数据、proc 快照和 ConsoleModel。
[OUTPUT]: 提供所有者去重、三种内存口径的实时行数据和身份固定的退出。
[POS]: Console 独立运行服务；后台任务不操作 Qt 或激活游戏。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import os
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import Property, QObject, QTimer, Signal
from PySide6.QtDBus import (
    QDBusConnection,
    QDBusMessage,
    QDBusPendingCallWatcher,
)

from ..app_routing import NATIVE_APPS, object_path, service_name
from ..i18n import Msg, error_text, render, tr
from .model import ConsoleModel
from .processes import force_terminate, measure, read_snapshot, system_metrics


class RuntimeConsole(QObject):
    structureChanged = Signal(object, object)
    identityChanged = Signal(str)
    summaryChanged = Signal()
    failed = Signal(object)
    collected = Signal(object)
    operationFinished = Signal(object)

    def __init__(self, parent=None, *, mock=False):
        super().__init__(parent)
        self.mock = mock
        self.model = ConsoleModel(self)
        self.windows = []
        self.applications = []
        self.language = "en"
        self.owners, self.pids, self.identities, self.infos = {}, {}, {}, {}
        self.metrics, self.aliases, self.exiting = {}, {}, {}
        self.system = {}
        self.details_key = ""
        self.previous = None
        self.visible = False
        self.closed = False
        self.generation = 0
        self._future = None
        self._calls = {}
        self._services = {service_name(app): app for app in sorted(NATIVE_APPS)}
        self.bus = None if mock else QDBusConnection.sessionBus()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="udeck-console")
        self.collected.connect(self._collected)
        self.operationFinished.connect(self._operation_finished)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh)

    @Property("QVariantMap", notify=summaryChanged)
    def summary(self):
        return {"count": len(self.model.rows), **self.system}

    @Property("QVariantMap", notify=summaryChanged)
    def details(self):
        row = self.row(self.details_key)
        if not row:
            return {"applicationKey": self.details_key, "available": False, "canQuit": False, "canForce": False}
        identity = self.identities.get(self.details_key)
        members = self.metrics.get(self.details_key, {}).get("members")
        return {field: row.get(field) for field in self.model.fields} | {
            "available": True, "mainPid": identity.pid if identity else None,
            "processCount": len(members) if members is not None else None,
            "windowCount": len(row["windows"]),
        }

    def set_details(self, key):
        self.details_key = key
        self.summaryChanged.emit()

    @Property(str, notify=summaryChanged)
    def summaryText(self):
        cpu = self.system.get("cpuPercent")
        used, total = self.system.get("memoryUsed"), self.system.get("memoryTotal")
        return render(tr(Msg.CONSOLE_SUMMARY, count=len(self.model.rows),
                         cpu=f"{cpu:.1f}%" if cpu is not None else "—",
                         used=f"{used / 1073741824:.1f} GiB" if used is not None else "—",
                         total=f"{total / 1073741824:.1f} GiB" if total else "—"), self.language)

    def set_catalog(self, applications, language):
        if self.applications is applications and self.language == language:
            return
        self.applications, self.language = applications, language
        self._rebuild()

    def set_windows(self, windows):
        self.windows = list(windows)
        services = {service_name(app): app for app in sorted(NATIVE_APPS)}
        for window in windows:
            app = window.get("appId", "")
            if app.count(".") >= 2 and app not in NATIVE_APPS and app != "io.github.zhubby.uDeck":
                services[app] = app
        for name in set(self._services) - set(services):
            self._owner_changed(name, self.owners.get(self._services[name], ""), "")
        self._services = services
        self._rebuild()
        if self.visible:
            self._discover()

    def set_visible(self, visible):
        visible = bool(visible)
        if visible == self.visible or self.closed:
            return
        self.visible = visible
        self.generation += 1
        self.previous = None
        if visible:
            self.timer.start()
            self.refresh()
        else:
            self.timer.stop()
            self.system = {}
            self.metrics = {}
            self._rebuild()

    def _call(self, app, operation, destination, path, interface, member, arguments, callback):
        key = (app, operation)
        if self.closed or self.mock or not self.bus.isConnected() or key in self._calls:
            return
        message = QDBusMessage.createMethodCall(destination, path, interface, member)
        message.setArguments(arguments)
        pending = QDBusPendingCallWatcher(self.bus.asyncCall(message, 1500), self)
        self._calls[key] = pending

        def finished(*_args):
            if self._calls.get(key) is not pending:
                return
            self._calls.pop(key)
            reply = pending.reply()
            pending.deleteLater()
            if not self.closed:
                callback(reply)

        pending.finished.connect(finished)
        if pending.isFinished():
            QTimer.singleShot(0, finished)

    def _discover(self):
        generation = self.generation
        for name, app in tuple(self._services.items()):
            def received(reply, name=name, app=app):
                if not self.visible or generation != self.generation or self._services.get(name) != app:
                    return
                arguments = reply.arguments()
                if reply.type() != QDBusMessage.MessageType.ErrorMessage and arguments:
                    owner = str(arguments[0])
                    if self.owners.get(app) == owner:
                        self._poll_info(app)
                    else:
                        self._owner_changed(name, self.owners.get(app, ""), owner)
                elif reply.errorName() == "org.freedesktop.DBus.Error.NameHasNoOwner":
                    self._owner_changed(name, self.owners.get(app, ""), "")
            self._call(app, "owner", "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                       "GetNameOwner", [name], received)

    def _owner_changed(self, name, old_owner, owner):
        app = self._services.get(name)
        if not app or self.closed or self.mock:
            return
        if self.owners.get(app, "") == owner:
            return
        self.owners.pop(app, None)
        self.pids.pop(app, None)
        self.identities.pop(app, None)
        self.infos.pop(app, None)
        self.metrics.pop(app, None)
        self.exiting.pop(app, None)
        if owner:
            self.owners[app] = owner
            if self.visible:
                self._resolve_pid(app, owner)
        self._rebuild()

    def _resolve_pid(self, app, owner):
        def received(reply):
            values = reply.arguments()
            if self.owners.get(app) != owner:
                return
            if reply.type() != QDBusMessage.MessageType.ErrorMessage and values and int(values[0]) > 1:
                self.pids[app] = int(values[0])
                self._sample()
                self._poll_info(app)
        self._call(app, "pid", "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                   "GetConnectionUnixProcessID", [owner], received)

    def _poll_info(self, app):
        owner = self.owners.get(app)
        if not owner or not self.visible:
            return
        if app not in self.pids:
            self._resolve_pid(app, owner)
            return
        if app not in NATIVE_APPS:
            return
        generation = self.generation
        def received(reply):
            if not self.visible or generation != self.generation or self.owners.get(app) != owner:
                return
            try:
                info = json.loads(reply.arguments()[0]) if reply.type() != QDBusMessage.MessageType.ErrorMessage else {}
                if not isinstance(info, dict) or not isinstance(info.get("relatedWindows", []), list):
                    return
                if self.infos.get(app) == info:
                    return
                self.infos[app] = info
                self._rebuild()
            except (ValueError, IndexError, TypeError):
                pass
        self._call(app, "info", owner, object_path(app), app + ".Control", "RuntimeInfo", [], received)

    def refresh(self):
        if not self.visible or self.closed:
            return
        for app, (_identity, deadline) in list(self.exiting.items()):
            if time.monotonic() >= deadline:
                self.exiting.pop(app)
                if app in self.owners or any(w.get("appId") == app for w in self.windows):
                    self.failed.emit(tr(Msg.CONSOLE_EXIT_WAITING))
        if self.mock:
            self._rebuild()
            return
        self._discover()
        self._sample()

    def _sample(self):
        if not self.visible or self.closed or self._future is not None or sys.platform != "linux":
            return
        generation, owners, pids = self.generation, dict(self.owners), dict(self.pids)
        previous, identities = self.previous, dict(self.identities)

        def work():
            current = read_snapshot()
            roots = {}
            for app, pid in pids.items():
                process = current.processes.get(pid)
                if process and process.uid == os.getuid() and process.state != "Z" and pid != os.getpid():
                    expected = identities.get(app)
                    if expected is None or expected == process.identity:
                        roots[app] = process.identity
            return current, roots, measure(current, previous, roots), system_metrics(current, previous)

        def done(future):
            try:
                result, error = future.result(), None
            except Exception as failure:
                result, error = None, failure
            if not self.closed:
                self.collected.emit((generation, owners, result, error))

        self._future = self.executor.submit(work)
        self._future.add_done_callback(done)

    def _collected(self, payload):
        generation, owners, result, error = payload
        self._future = None
        if self.closed or not self.visible or generation != self.generation:
            return
        if error:
            self.metrics, self.system = {}, {}
        else:
            self.previous, roots, metrics, self.system = result
            self.identities = {app: identity for app, identity in roots.items() if owners.get(app) == self.owners.get(app)}
            self.metrics = {app: values for app, values in metrics.items() if app in self.identities}
        self._rebuild()

    def _rebuild(self):
        aliases = {}
        for app, info in self.infos.items():
            members = {identity.pid for identity in self.metrics.get(app, {}).get("members", [])}
            for related in info.get("relatedWindows", []):
                if (isinstance(related, dict) and related.get("pid") in members
                        and sum(w.get("appId") == related.get("appId") for w in self.windows) == 1):
                    aliases[related.get("appId")] = app
        self.aliases = aliases
        groups = {}
        for window in self.windows:
            app = window.get("appId") or "window:" + window["id"]
            app = aliases.get(app, app)
            groups.setdefault(app, []).append(window)
        for app in self.owners:
            if app in NATIVE_APPS:
                groups.setdefault(app, [])
        old = [row["applicationKey"] for row in self.model.rows]
        old_identities = {row["applicationKey"]: row.get("identity") for row in self.model.rows}
        order = [key for key in old if key in groups] + [key for key in groups if key not in old]
        catalog = {entry["id"].removesuffix(".desktop").casefold(): entry for entry in self.applications}
        rows = []
        for key in order:
            windows = groups[key]
            entry = catalog.get(key.casefold(), {})
            first = next((w for w in windows if not w.get("parent")), windows[0] if windows else {})
            values = self.metrics.get(key, {})
            identity = self.identities.get(key)
            state = self.infos.get(key, {}).get("state", "running")
            if state not in ("playing", "paused", "exiting"):
                state = "running"
            if key in self.exiting:
                state = "exiting"
            if self.mock:
                values = {"cpuPercent": 3.4 + len(rows), "memoryBytes": (96 + len(rows) * 20) * 1048576,
                          "memoryRssBytes": (206 + len(rows) * 20) * 1048576,
                          "memoryPrivateBytes": (71 + len(rows) * 20) * 1048576,
                          "uptimeSeconds": 1200 + len(rows) * 90}
            rows.append({"applicationKey": key, "applicationName": render(entry.get("name") or first.get("name") or key.rsplit(".", 1)[-1], self.language),
                         "applicationIcon": entry.get("icon") or first.get("icon") or key,
                         "runtimeState": state, "cpuPercent": values.get("cpuPercent"),
                         "memoryBytes": values.get("memoryBytes"), "uptimeSeconds": values.get("uptimeSeconds"),
                         "memoryRssBytes": values.get("memoryRssBytes"), "memoryPrivateBytes": values.get("memoryPrivateBytes"),
                         "canQuit": bool(windows or self.infos.get(key)) and key not in self.exiting
                                    and (self.mock or key not in NATIVE_APPS or bool(self.owners.get(key))),
                         "canForce": bool(self.mock or identity and sum(value == identity for value in self.identities.values()) == 1
                                          and hasattr(os, "pidfd_open") and hasattr(signal, "pidfd_send_signal")) and key not in self.exiting,
                         "windows": windows, "identity": identity, "owner": self.owners.get(key, "")})
        self.model.update(rows)
        for row in rows:
            key = row["applicationKey"]
            if key in old_identities and old_identities[key] != row["identity"]:
                self.identityChanged.emit(key)
        if order != old:
            self.structureChanged.emit(old, order)
        self.summaryChanged.emit()

    def row(self, key):
        return next((row for row in self.model.rows if row["applicationKey"] == key), None)

    def target(self, key):
        row = self.row(key)
        identity = row.get("identity") if row else None
        return {"key": key, "owner": row.get("owner", ""), "pid": identity.pid if identity else 0,
                "start": identity.start if identity else 0,
                "windows": [[w["id"], w.get("appId", "")] for w in row["windows"]]} if row else {}

    def _checked(self, target):
        row = self.row(target.get("key"))
        if not row or self.target(target["key"]) != target:
            raise RuntimeError(tr(Msg.CONSOLE_IDENTITY_CHANGED))
        return row

    def _close_windows(self, row, windows):
        if not windows:
            raise RuntimeError(tr(Msg.CONSOLE_PROCESS_UNAVAILABLE))
        existing = {(w["id"], w.get("appId", "")) for w in windows.entries()}
        targets = [window for window in row["windows"] if not window.get("parent")] or row["windows"]
        for window in targets:
            if (window["id"], window.get("appId", "")) in existing:
                windows.request(window["id"], "close")

    def quit(self, target, windows):
        row = self._checked(target)
        key = target["key"]
        if not row["canQuit"]:
            return
        if self.mock:
            self.set_windows([w for w in self.windows if w not in row["windows"]])
            return
        if key in NATIVE_APPS:
            owner = target["owner"]
            def received(reply):
                if self.owners.get(key) != owner:
                    return
                if reply.type() == QDBusMessage.MessageType.ErrorMessage and reply.errorName() in (
                    "org.freedesktop.DBus.Error.UnknownMethod", "org.freedesktop.DBus.Error.UnknownInterface",
                ):
                    try:
                        self._close_windows(self._checked(target), windows)
                        return
                    except (OSError, RuntimeError) as error:
                        self.exiting.pop(key, None)
                        self.failed.emit(error_text(error))
                        self._rebuild()
                        return
                values = reply.arguments()
                if reply.type() == QDBusMessage.MessageType.ErrorMessage or not values or values[0]:
                    self.exiting.pop(key, None)
                    self.failed.emit(str(values[0]) if values else reply.errorMessage())
                    self._rebuild()
            self._call(key, "quit", owner, object_path(key), key + ".Control", "RequestQuit", [], received)
        else:
            self._close_windows(row, windows)
        self.exiting[key] = (row["identity"], time.monotonic() + 5)
        self._rebuild()

    def force(self, target):
        row = self._checked(target)
        if not row["canForce"]:
            raise RuntimeError(tr(Msg.CONSOLE_PROCESS_UNAVAILABLE))
        if self.mock:
            self.set_windows([w for w in self.windows if w not in row["windows"]])
            return
        key, identity, owner = target["key"], row["identity"], target["owner"]
        name = next((name for name, app in self._services.items() if app == key), "")

        def verified(reply):
            try:
                self._checked(target)
                if reply.type() == QDBusMessage.MessageType.ErrorMessage or reply.arguments() != [owner]:
                    raise RuntimeError(tr(Msg.CONSOLE_IDENTITY_CHANGED))
                protected = [value for app, value in self.identities.items() if app != key]
                future = self.executor.submit(force_terminate, identity, protected)
                def done(result):
                    try:
                        result.result()
                        error = None
                    except Exception as failure:
                        error = failure
                    if not self.closed:
                        self.operationFinished.emit((key, error))
                future.add_done_callback(done)
            except RuntimeError as error:
                self.exiting.pop(key, None)
                self.failed.emit(error_text(error))
                self._rebuild()
        self._call(key, "force-owner", "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                   "GetNameOwner", [name], verified)
        self.exiting[key] = (identity, time.monotonic() + 5)
        self._rebuild()

    def _operation_finished(self, payload):
        key, error = payload
        if self.closed:
            return
        if error:
            self.exiting.pop(key, None)
            self.failed.emit(error_text(error))
        self.refresh()

    def close(self):
        self.closed = True
        self.timer.stop()
        for watcher in self._calls.values():
            watcher.deleteLater()
        self._calls.clear()
        self.executor.shutdown(wait=False, cancel_futures=True)
