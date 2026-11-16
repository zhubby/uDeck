"""
[INPUT]: 依赖 RuntimeConsole、网格导航与现有应用启动路由。
[OUTPUT]: 提供 Console 模型、稳定选择、实时详情与退出确认。
[POS]: ShellController 的运行面板桥接；进程采样不进入桌面主控制器。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

from PySide6.QtCore import Property, QObject

from ..app_routing import NATIVE_APPS
from ..core import move_index
from ..i18n import Msg, error_text, tr
from .service import RuntimeConsole


class ConsoleControls:
    def _init_console(self):
        self.console_exit_focused = False
        self.runtime_console = RuntimeConsole(self, mock=self.mock)
        self.runtime_console.set_catalog(self.applications, self.language)
        self.runtime_console.set_windows(self.data["windows"])
        self.runtime_console.structureChanged.connect(self._console_structure)
        self.runtime_console.identityChanged.connect(self._console_identity)
        self.runtime_console.failed.connect(self.notify)

    @Property(QObject, constant=True)
    def consoleModel(self):
        return self.runtime_console.model

    @Property(QObject, constant=True)
    def runtimeConsole(self):
        return self.runtime_console

    def _console_items(self):
        return [{"id": row["applicationKey"], "appId": row["applicationKey"], "name": row["applicationName"],
                 "icon": row["applicationIcon"]} for row in self.runtime_console.model.rows]

    def _console_snapshot(self):
        return {"summary": self.runtime_console.summary, "visible": self.runtime_console.visible,
                "samplePending": self.runtime_console._future is not None,
                "applications": [{field: row.get(field) for field in self.runtime_console.model.fields}
                                 | {"process": self.runtime_console.target(row["applicationKey"])}
                                 for row in self.runtime_console.model.rows]}

    def _console_identity(self, key):
        items = self._console_items()
        if (self.navigation.page == "windows" and self.console_exit_focused
                and items and items[min(self.navigation.index, len(items) - 1)]["id"] == key):
            self.console_exit_focused = False
            self._publish()

    def _console_structure(self, old, new):
        def selected_index(index):
            key = old[index] if 0 <= index < len(old) else None
            return new.index(key) if key in new else max(0, min(index, len(new) - 1))

        index = self.navigation.index if self.navigation.page == "windows" else self.navigation.positions.get("windows", 0)
        key = old[index] if 0 <= index < len(old) else None
        selected = selected_index(index)
        self.navigation.positions["windows"] = selected
        self.navigation.modal_owners = [(page, zone, selected_index(position) if page == "windows" else position)
                                        for page, zone, position in self.navigation.modal_owners]
        if self.navigation.page == "windows":
            self.navigation.index = selected
        if key not in new:
            self.console_exit_focused = False
        self._publish()

    def _console_sync(self):
        if not hasattr(self, "runtime_console"):
            return
        self.runtime_console.set_catalog(self.applications, self.language)
        self.runtime_console.set_visible(self.navigation.page == "windows" and (self.mock or getattr(self, "_test_active", False)))
        if self.navigation.page != "windows":
            self.console_exit_focused = False

    def _console_dispatch(self, action):
        if self.navigation.page != "windows" or self.navigation.zone != "content":
            return False
        items = self._console_items()
        if action in ("left", "right") and items:
            value = action == "right"
            if value != self.console_exit_focused:
                self.console_exit_focused = value
                self.feedback("navigate")
            self._publish()
            return True
        if action == "accept" and self.console_exit_focused and items:
            self._console_quit(items[min(self.navigation.index, len(items) - 1)]["id"])
            self._publish()
            return True
        if action in ("up", "down", "back"):
            self.console_exit_focused = False
        return False

    def _console_activate(self, item):
        row = self.runtime_console.row(item["id"])
        if not row:
            self.notify(tr(Msg.CONSOLE_IDENTITY_CHANGED))
            return
        if self.mock:
            self.notify(tr(Msg.PREVIEW_SWITCH_TO_PREFIX) + item["name"])
        elif item["id"] in NATIVE_APPS:
            entry = next((app for app in self.applications if app["id"].removesuffix(".desktop") == item["id"]),
                         {"id": item["id"] + ".desktop", "name": item["name"], "icon": item["icon"]})
            self._start_application(entry)
        else:
            windows = row["windows"]
            window = next((w for w in windows if w.get("active")), next((w for w in windows if not w.get("parent")), None))
            if window:
                self._console_window(window)

    def _console_action(self, key, action):
        if (self.modal or self.navigation.page != "windows" or self.startup["active"]
                or self.app_launch["pending"] or action not in ("details", "quit")):
            return
        items = self._console_items()
        index = next((i for i, item in enumerate(items) if item["id"] == key), None)
        if index is None:
            return
        self.select(index)
        if action == "details":
            self._console_show(items[index])
        else:
            self._console_quit(key)
            self._publish()

    def _console_show(self, item):
        if not self.runtime_console.row(item["id"]):
            return
        self.runtime_console.set_details(item["id"])
        self._push({"kind": "console-details", "title": item["name"], "applicationKey": item["id"]})

    def _console_details_modal(self, action):
        modal = self.modal
        if action in ("up", "down", "left", "right"):
            previous = modal["index"]
            modal["index"] = move_index(previous, action, 4, 2)
            if previous != modal["index"]:
                self.feedback("navigate")
        elif action == "accept":
            index = modal["index"]
            if index == 3:
                self.feedback("back")
                self._pop()
                return
            row = self.runtime_console.row(modal["applicationKey"])
            if not row or (index == 1 and not row["canQuit"]) or (index == 2 and not row["canForce"]):
                self.feedback("error")
                self.notify(tr(Msg.CONSOLE_IDENTITY_CHANGED if not row else Msg.CONSOLE_PROCESS_UNAVAILABLE))
                return
            target = self.runtime_console.target(modal["applicationKey"])
            self.feedback("accept")
            if index == 0:
                self._pop()
            self._console_option({"action": ("console-activate", "console-quit", "console-force")[index], "target": target})

    def _console_window(self, item):
        if self.mock:
            return
        existing = self.window_service.entries() if self.window_service else []
        if not any((w["id"], w.get("appId")) == (item["id"], item.get("appId")) for w in existing):
            raise RuntimeError(tr(Msg.CONSOLE_IDENTITY_CHANGED))
        self.window_service.request(item["id"], "activate")

    def _console_quit(self, key, target=None):
        try:
            row = self.runtime_console.row(key)
            if self.mock and row:
                self.data["windows"] = [w for w in self.data["windows"] if w not in row["windows"]]
            self.runtime_console.quit(target or self.runtime_console.target(key), self.window_service)
        except (OSError, RuntimeError) as error:
            self.notify(error_text(error))

    def _console_context(self, item):
        if not item:
            return
        row = self.runtime_console.row(item["id"])
        if not row:
            return
        target = self.runtime_console.target(item["id"])
        options = [{"label": tr(Msg.OPEN_APP), "action": "console-activate", "target": target},
                   {"label": tr(Msg.CONSOLE_EXIT), "action": "console-quit", "target": target,
                    "disabled": not row["canQuit"]}]
        if len(row["windows"]) > 1:
            options.append({"label": tr(Msg.CONSOLE_WINDOWS), "action": "console-windows", "target": target})
        options.append({"label": tr(Msg.CONSOLE_FORCE_QUIT), "action": "console-force", "target": target,
                        "disabled": not row["canForce"], "reason": tr(Msg.CONSOLE_PROCESS_UNAVAILABLE)})
        self._menu(item["name"], options, source="console-app")

    def _console_option(self, option):
        action = option.get("action", "")
        if not action.startswith("console-") or action == "console-control":
            return False
        target = option.get("target", {})
        try:
            if action == "console-window":
                self._console_window(option["item"])
            else:
                row = self.runtime_console._checked(target)
                if action == "console-activate":
                    self._console_activate({"id": target["key"], "name": row["applicationName"], "icon": row["applicationIcon"]})
                elif action == "console-quit":
                    self._console_quit(target["key"], target)
                elif action == "console-windows":
                    self._menu(tr(Msg.CONSOLE_WINDOWS), [{"label": w["name"], "action": "console-window", "item": w}
                                                       for w in row["windows"] if not w.get("parent")])
                elif action == "console-force":
                    self._confirm(tr(Msg.CONSOLE_FORCE_PROMPT), tr(Msg.CONSOLE_FORCE_BODY, name=row["applicationName"]),
                                  {"action": "console-force-confirm", "target": target})
                elif action == "console-force-confirm":
                    if self.mock:
                        self.data["windows"] = [w for w in self.data["windows"] if w not in row["windows"]]
                    self.runtime_console.force(target)
        except (OSError, RuntimeError) as error:
            self.notify(error_text(error))
        return True
