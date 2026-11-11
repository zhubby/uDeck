"""Files menus and asynchronous service status using existing shell modals."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtDBus import QDBusConnection

from ..i18n import tr


class NetworkAccessControls:
    def _init_network_access(self):
        self.network_access = {"enabled": False, "state": "stopped", "root": str(Path.home()),
                               "duration": 0, "networks": [], "candidates": [], "urls": [], "errors": []}
        self.network_draft = {"root": str(Path.home()), "duration": 0, "networks": []}
        self._network_dirty = False
        self._network_busy = False
        self._network_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="udeck-network-access")
        self._network_owner = "io.github.zhubby.uDeck.NetworkFiles.Owner.u" + uuid.uuid4().hex
        self._network_bus = QDBusConnection.sessionBus()
        if self._network_bus.isConnected():
            self._network_bus.registerService(self._network_owner)
        self.networkAccessFinished.connect(self._network_result)
        self._network_timer = QTimer(self)
        self._network_timer.setInterval(3000)
        self._network_timer.timeout.connect(self._network_poll)
        self._network_timer.start()

    def _network_poll(self):
        if not self.mock and (self.network_access["enabled"] or self.navigation.page == "files"):
            self._network_request("status")

    def _network_request(self, operation, value=None):
        if self._network_busy:
            return
        self._network_busy = True
        self._network_refresh()
        from . import client
        def work():
            try:
                result = getattr(client, operation)(value) if value is not None else getattr(client, operation)()
                return operation, result, ""
            except Exception as error:
                return operation, None, str(error)
        def finished(future):
            if not self._files_closing:
                self.networkAccessFinished.emit(future.result())
        self._network_executor.submit(work).add_done_callback(finished)

    def _network_result(self, message):
        operation, result, error = message
        self._network_busy = False
        if error:
            self.network_access["errors"] = [error]
            self.notify(error)
        elif result:
            self.network_access = result
            editing = any(modal.get("source", "").startswith("network-access") or modal.get("purpose") == "network-share-root" for modal in self._modals)
            if operation != "status" or not self._network_dirty or not editing:
                self.network_draft = {**{key: result[key] for key in ("root", "duration")}, "networks": list(result["networks"])}
                self._network_dirty = False
        self._network_refresh()
        self._publish()

    def _network_refresh(self):
        if self.modal.get("source") == "network-access":
            self.modal.update(options=self._network_options(), body=self._network_body())
        elif self.modal.get("source") == "network-access-networks":
            previous = self.modal["options"][min(self.modal["index"], len(self.modal["options"]) - 1)].get("value")
            options = self._network_network_options()
            self.modal.update(options=options, index=next((i for i, row in enumerate(options) if row.get("value") == previous), 0),
                              body="" if self.network_access.get("candidates") else tr("No connected networks are available"))

    def _network_network_options(self):
        candidates = self.network_access.get("candidates", [])
        rows = [self._network_option(("✓ " if row["key"] in self.network_draft["networks"] else "") + row["name"],
                    "toggle", "network-wireless", value=row["key"],
                    subtitle=row.get("interface", "") + " · " + ", ".join(row["addresses"])) for row in candidates]
        connected = {row["key"] for row in candidates}
        rows += [self._network_option("✓ " + tr("Unavailable network"), "toggle", "network-disconnect",
                                     value=key, subtitle=key, wrapSubtitle=True)
                 for key in self.network_draft["networks"] if key not in connected]
        return rows + [self._network_option(tr("Done"), "done", "network-connect")]

    @staticmethod
    def _network_option(label, command, icon, **values):
        from ..menu_icons import SETTING_ARTWORK, SETTING_ICON_PREFIX
        artwork = SETTING_ARTWORK.get(icon)
        return {"label": label, "action": "files", "command": "network-" + command,
                "icon": SETTING_ICON_PREFIX + artwork if artwork else icon, **values}

    def _network_options(self):
        option = self._network_option
        duration = self.network_draft["duration"]
        labels = {0: tr("Permanent"), 3600: tr("1 hour"), 21600: tr("6 hours"), 43200: tr("12 hours")}
        rows = [option(tr("Shared folder"), "root", "folder", subtitle=self.network_draft["root"]),
                option(tr("Networks"), "networks", "network-wireless", subtitle=tr("{count} selected", count=len(self.network_draft["networks"]))),
                option(tr("Access duration"), "duration", "preferences-system-time", subtitle=labels[duration])]
        if len(self.network_access["urls"]) > 2:
            rows.append(option(tr("Access addresses"), "addresses", "network-connect"))
        rows.append(option(tr("Apply and enable") if self.network_access["enabled"] else tr("Enable network access"),
                           "start", "network-connect", disabled=self._network_busy or not self.network_draft["networks"]))
        if self.network_access["enabled"]:
            rows.append(option(tr("Turn off network access"), "stop", "network-disconnect", disabled=self._network_busy))
        return rows

    def _network_body(self):
        state = self.network_access
        labels = {"running": tr("Network access is on"), "waiting": tr("Waiting for selected networks"), "stopped": tr("Network access is off")}
        lines = [labels.get(state["state"], tr("Network access is off"))]
        lines.extend(state.get("urls", [])[:2])
        if len(state.get("urls", [])) > 2:
            lines.append(tr("{count} more addresses", count=len(state["urls"]) - 2))
        if state.get("remaining") is not None:
            lines.append(tr("{minutes} minutes remaining", minutes=max(0, state["remaining"] // 60)))
        if state["enabled"] and state["duration"] == 0:
            lines.append(tr("Restores automatically after restart"))
        lines.extend(error[:160] for error in state.get("errors", [])[:1])
        body = lines[0]
        for line in lines[1:]:
            body = body + "\n" + line
        return body

    def _network_menu(self):
        self._menu(tr("Network access"), self._network_options(), body=self._network_body(), source="network-access")
        if not self.mock:
            self._network_request("status")

    def _network_command(self, command, value=""):
        option = self._network_option
        if command == "access":
            self._network_menu()
        elif command == "root":
            self._text_prompt(tr("Shared folder"), tr("Enter the folder to share. The web page can only access this folder and its contents."),
                              "network-share-root", self.network_draft["root"])
        elif command == "networks":
            candidates = self.network_access.get("candidates", [])
            self._menu(tr("Networks"), self._network_network_options(), source="network-access-networks",
                       body="" if candidates else tr("No connected networks are available"))
        elif command == "addresses":
            self._menu(tr("Access addresses"), [option(url, "done", "network-connect") for url in self.network_access["urls"]],
                       source="network-access-addresses")
        elif command == "toggle":
            self._network_dirty = True
            networks = self.network_draft["networks"] = list(self.network_draft["networks"])
            networks.remove(value) if value in networks else networks.append(value)
            self._network_command("networks")
        elif command == "duration":
            values = [(0, tr("Permanent")), (3600, tr("1 hour")), (21600, tr("6 hours")), (43200, tr("12 hours"))]
            self._menu(tr("Access duration"), [option(label, "set-duration", "preferences-system-time", value=duration)
                                               for duration, label in values], source="network-access-duration")
        elif command == "set-duration":
            self._network_dirty = True
            self.network_draft["duration"] = int(value)
            self._network_menu()
        elif command == "done":
            self._network_menu()
        elif command in ("start", "stop"):
            if self.mock:
                self.network_access.update(**self.network_draft, enabled=command == "start", state="running" if command == "start" else "stopped")
                self._network_menu()
            else:
                self._network_request(command, {**self.network_draft, "owner": self._network_owner} if command == "start" else None)

    def _close_network_access(self):
        self._network_timer.stop()
        if self._network_bus.isConnected():
            self._network_bus.unregisterService(self._network_owner)
        self._network_executor.shutdown(wait=False, cancel_futures=True)
