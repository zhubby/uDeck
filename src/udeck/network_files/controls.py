"""Files menus and asynchronous service status using existing shell modals."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtDBus import QDBusConnection

from ..i18n import Msg, tr


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
                              body="" if self.network_access.get("candidates") else tr(Msg.NO_CONNECTED_NETWORKS_ARE_AVAILABLE))

    def _network_network_options(self):
        candidates = self.network_access.get("candidates", [])
        rows = [self._network_option(("✓ " if row["key"] in self.network_draft["networks"] else "") + row["name"],
                    "toggle", "network-wireless", value=row["key"],
                    subtitle=row.get("interface", "") + " · " + ", ".join(row["addresses"])) for row in candidates]
        connected = {row["key"] for row in candidates}
        rows += [self._network_option("✓ " + tr(Msg.UNAVAILABLE_NETWORK), "toggle", "network-disconnect",
                                     value=key, subtitle=key, wrapSubtitle=True)
                 for key in self.network_draft["networks"] if key not in connected]
        return rows + [self._network_option(tr(Msg.DONE), "done", "network-connect")]

    @staticmethod
    def _network_option(label, command, icon, **values):
        from ..menu_icons import SETTING_ARTWORK, SETTING_ICON_PREFIX
        artwork = SETTING_ARTWORK.get(icon)
        return {"label": label, "action": "files", "command": "network-" + command,
                "icon": SETTING_ICON_PREFIX + artwork if artwork else icon, **values}

    def _network_options(self):
        option = self._network_option
        duration = self.network_draft["duration"]
        labels = {0: tr(Msg.PERMANENT), 3600: tr(Msg.N_1_HOUR), 21600: tr(Msg.N_6_HOURS), 43200: tr(Msg.N_12_HOURS)}
        rows = [option(tr(Msg.SHARED_FOLDER), "root", "folder", subtitle=self.network_draft["root"]),
                option(tr(Msg.NETWORKS), "networks", "network-wireless", subtitle=tr(Msg.COUNT_SELECTED, count=len(self.network_draft["networks"]))),
                option(tr(Msg.ACCESS_DURATION), "duration", "preferences-system-time", subtitle=labels[duration])]
        if len(self.network_access["urls"]) > 2:
            rows.append(option(tr(Msg.ACCESS_ADDRESSES), "addresses", "network-connect"))
        rows.append(option(tr(Msg.APPLY_AND_ENABLE) if self.network_access["enabled"] else tr(Msg.ENABLE_NETWORK_ACCESS),
                           "start", "network-connect", disabled=self._network_busy or not self.network_draft["networks"]))
        if self.network_access["enabled"]:
            rows.append(option(tr(Msg.TURN_OFF_NETWORK_ACCESS), "stop", "network-disconnect", disabled=self._network_busy))
        return rows

    def _network_body(self):
        state = self.network_access
        labels = {"running": tr(Msg.NETWORK_ACCESS_IS_ON), "waiting": tr(Msg.WAITING_FOR_SELECTED_NETWORKS), "stopped": tr(Msg.NETWORK_ACCESS_IS_OFF)}
        lines = [labels.get(state["state"], tr(Msg.NETWORK_ACCESS_IS_OFF))]
        lines.extend(state.get("urls", [])[:2])
        if len(state.get("urls", [])) > 2:
            lines.append(tr(Msg.COUNT_MORE_ADDRESSES, count=len(state["urls"]) - 2))
        if state.get("remaining") is not None:
            lines.append(tr(Msg.MINUTES_MINUTES_REMAINING, minutes=max(0, state["remaining"] // 60)))
        if state["enabled"] and state["duration"] == 0:
            lines.append(tr(Msg.RESTORES_AUTOMATICALLY_AFTER_RESTART))
        lines.extend(error[:160] for error in state.get("errors", [])[:1])
        body = lines[0]
        for line in lines[1:]:
            body = body + "\n" + line
        return body

    def _network_menu(self):
        self._menu(tr(Msg.NETWORK_ACCESS), self._network_options(), body=self._network_body(), source="network-access")
        if not self.mock:
            self._network_request("status")

    def _network_command(self, command, value=""):
        option = self._network_option
        if command == "access":
            self._network_menu()
        elif command == "root":
            self._text_prompt(tr(Msg.SHARED_FOLDER), tr(Msg.ENTER_THE_FOLDER_TO_SHARE_THE_WEB_PAGE_CAN_ONLY_ACCESS_THIS_FOLDER_AND_ITS_CONTENTS),
                              "network-share-root", self.network_draft["root"])
        elif command == "networks":
            candidates = self.network_access.get("candidates", [])
            self._menu(tr(Msg.NETWORKS), self._network_network_options(), source="network-access-networks",
                       body="" if candidates else tr(Msg.NO_CONNECTED_NETWORKS_ARE_AVAILABLE))
        elif command == "addresses":
            self._menu(tr(Msg.ACCESS_ADDRESSES), [option(url, "done", "network-connect") for url in self.network_access["urls"]],
                       source="network-access-addresses")
        elif command == "toggle":
            self._network_dirty = True
            networks = self.network_draft["networks"] = list(self.network_draft["networks"])
            networks.remove(value) if value in networks else networks.append(value)
            self._network_command("networks")
        elif command == "duration":
            values = [(0, tr(Msg.PERMANENT)), (3600, tr(Msg.N_1_HOUR)), (21600, tr(Msg.N_6_HOURS)), (43200, tr(Msg.N_12_HOURS))]
            self._menu(tr(Msg.ACCESS_DURATION), [option(label, "set-duration", "preferences-system-time", value=duration)
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
