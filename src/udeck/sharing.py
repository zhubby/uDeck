"""Independent sharing controls, owned by the shell rather than the Files page."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtDBus import QDBusConnection

from .i18n import Msg, error_text, tr
from .menu_icons import system_menu_icons
from .sharing_messages import sharing_message


class SharingControls:
    def _init_sharing(self):
        self._shares = {}
        for protocol, root in (("web", str(Path.home())), ("smb", "")):
            state = {"enabled": False, "state": "stopped", "root": root, "duration": 0,
                     "networks": [], "candidates": [], "urls": [], "errors": []}
            self._shares[protocol] = {"state": state, "draft": {"root": root, "duration": 0, "networks": []},
                                      "dirty": False, "busy": False, "pending": False, "loaded": False, "error": ""}
        self._sharing_closing = False
        self._network_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="udeck-sharing")
        self._network_owner = "io.github.zhubby.uDeck.NetworkFiles.Owner.u" + uuid.uuid4().hex
        self._network_bus = QDBusConnection.sessionBus()
        if self._network_bus.isConnected():
            self._network_bus.registerService(self._network_owner)
        self.sharingFinished.connect(self._sharing_result)
        self.networkAccessFinished.connect(self._network_result)
        self._network_timer = QTimer(self)
        self._network_timer.setInterval(3000)
        self._network_timer.timeout.connect(self._network_poll)
        self._network_timer.start()
        QTimer.singleShot(0, self._network_poll)

    @property
    def network_access(self):
        return self._shares["web"]["state"]

    @network_access.setter
    def network_access(self, value):
        self._shares["web"]["state"] = value

    @property
    def network_draft(self):
        return self._shares["web"]["draft"]

    @property
    def smb_access(self):
        return self._shares["smb"]["state"]

    @property
    def smb_draft(self):
        return self._shares["smb"]["draft"]

    @property
    def _network_dirty(self):
        return self._shares["web"]["dirty"]

    @_network_dirty.setter
    def _network_dirty(self, value):
        self._shares["web"]["dirty"] = value

    def _network_poll(self):
        if not self.mock and not self._sharing_closing:
            for protocol in self._shares:
                self._sharing_request(protocol, "status")

    def _sharing_request(self, protocol, operation, value=None):
        share = self._shares[protocol]
        if share["busy"]:
            if operation != "status":
                share["queued"] = (operation, value)
                share.update(pending=True, error="")
                self._sharing_refresh()
                self._publish()
            return
        share.update(busy=True, pending=operation != "status")
        if operation != "status":
            share["error"] = ""
        self._sharing_refresh()
        self._publish()

        def work():
            client = None
            try:
                if protocol == "web":
                    from .network_files import client
                else:
                    from .smb_files import client
                result = getattr(client, operation)(value) if value is not None else getattr(client, operation)()
                return protocol, operation, result, ""
            except Exception as error:
                result = None
                if operation != "status" and client is not None:
                    try:
                        result = client.status()
                    except Exception:
                        pass
                return protocol, operation, result, sharing_message(error_text(error))

        def finished(future):
            if not self._sharing_closing:
                self.sharingFinished.emit(future.result())
        self._network_executor.submit(work).add_done_callback(finished)

    def _sharing_result(self, message):
        protocol, operation, result, error = message
        share = self._shares[protocol]
        share.update(busy=False, pending=False)
        if result:
            share.update(state=result, loaded=True)
            if not share["dirty"] or operation != "status" and not error:
                share["draft"] = {key: list(result[key]) if key == "networks" else result[key]
                                  for key in ("root", "duration", "networks")}
                share["dirty"] = False
        if error:
            share["error"] = error
            share["error_operation"] = operation
            if operation != "status":
                self.notify(error)
        elif operation != "status" or share.get("error_operation") == "status":
            share["error"] = ""
        self._sharing_refresh()
        self._publish()
        queued = share.pop("queued", None)
        if queued:
            self._sharing_request(protocol, *queued)

    @staticmethod
    def _sharing_title(protocol):
        return tr(Msg.WEB_FILE_ACCESS if protocol == "web" else Msg.SMB_FILE_SHARING)

    @staticmethod
    def _sharing_option(protocol, label, command, icon, **values):
        return {"id": command, "label": label, "action": "sharing", "protocol": protocol,
                "command": command, "icon": icon, "navigate": command in ("open", "root", "networks", "duration", "addresses"), **values}

    def _sharing_options(self, protocol):
        share = self._shares[protocol]
        state, draft = share["state"], share["draft"]
        def row(label, command, icon, **values):
            return self._sharing_option(protocol, label, command, icon, disabled=share["pending"], **values)
        return [row(tr(Msg.ENABLE_SHARING), "enabled", "network-connect", checked=state["enabled"],
                    subtitle=tr(Msg.APPLYING) if share["pending"] else self._sharing_status(protocol)),
                row(tr(Msg.SHARED_FOLDER), "root", "folder", subtitle=draft["root"] or tr(Msg.NOT_SELECTED)),
                row(tr(Msg.ALLOWED_NETWORKS), "networks", "network-wireless", subtitle=tr(Msg.COUNT_SELECTED, count=len(draft["networks"]))),
                row(tr(Msg.ACCESS_DURATION), "duration", "preferences-system-time", subtitle=self._sharing_duration(draft["duration"])),
                row(tr(Msg.ACCESS_ADDRESSES), "addresses", "network-connect", subtitle=state.get("urls", [""])[0] if state.get("urls") else tr(Msg.NONE))]

    def _sharing_status(self, protocol):
        state = self._shares[protocol]["state"]
        return tr(Msg.ON) if state["state"] == "running" else tr(Msg.WAITING_FOR_SELECTED_NETWORKS) if state["enabled"] else tr(Msg.OFF)

    @staticmethod
    def _sharing_duration(duration):
        return tr({0: Msg.PERMANENT, 3600: Msg.N_1_HOUR, 21600: Msg.N_6_HOURS, 43200: Msg.N_12_HOURS}[duration])

    def _sharing_body(self, protocol):
        share = self._shares[protocol]
        state = share["state"]
        lines = []
        if protocol == "smb":
            lines.append(tr(Msg.SMB_GUEST_DESCRIPTION))
        if state.get("remaining") is not None:
            lines.append(tr(Msg.MINUTES_MINUTES_REMAINING, minutes=max(0, state["remaining"] // 60)))
        elif state["enabled"] and state["duration"] == 0:
            lines.append(tr(Msg.RESTORES_AUTOMATICALLY_AFTER_RESTART))
        lines.extend(([share["error"]] if share["error"] else state.get("errors", []))[:1])
        # Preserve marked messages until serialization, including when language changes.
        body = ""
        for line in lines:
            body = body + ("\n" if body else "") + sharing_message(line)
        return body

    def _sharing_root_options(self):
        return [self._sharing_option(protocol, self._sharing_title(protocol), "open", "network-connect",
                                     id=protocol, value=protocol, subtitle=self._sharing_status(protocol))
                for protocol in self._shares]

    def _sharing_menu(self):
        self._menu(tr(Msg.SHARING), self._sharing_root_options(), source="sharing")
        self._network_poll()

    def _sharing_open(self, protocol):
        source = "sharing-" + protocol
        if self.modal.get("source") != source:
            self._menu(self._sharing_title(protocol), self._sharing_options(protocol), source=source, body=self._sharing_body(protocol))
        self._sharing_refresh()
        if not self.mock:
            self._sharing_request(protocol, "status")

    def _sharing_network_options(self, protocol):
        share = self._shares[protocol]
        candidates = share["state"].get("candidates", [])
        rows = [self._sharing_option(protocol, row["name"], "toggle-network", "network-wireless", id=row["key"], value=row["key"],
                    checked=row["key"] in share["draft"]["networks"], subtitle=", ".join(row["addresses"])) for row in candidates]
        connected = {row["key"] for row in candidates}
        rows += [self._sharing_option(protocol, tr(Msg.UNAVAILABLE_NETWORK), "toggle-network", "network-disconnect",
                                     id=key, value=key, checked=True, subtitle=key)
                 for key in share["draft"]["networks"] if key not in connected]
        return rows + [self._sharing_option(protocol, tr(Msg.DONE), "done", "network-connect")]

    def _sharing_refresh(self):
        for modal in self._modals:
            source = modal.get("source", "")
            if source == "sharing":
                options = self._sharing_root_options()
            elif source in ("sharing-web", "sharing-smb"):
                protocol = source.split("-")[1]
                options = self._sharing_options(protocol)
                modal["body"] = self._sharing_body(protocol)
            elif source in ("sharing-web-networks", "sharing-smb-networks"):
                protocol = source.split("-")[1]
                options = self._sharing_network_options(protocol)
                modal["body"] = "" if self._shares[protocol]["state"].get("candidates") else tr(Msg.NO_CONNECTED_NETWORKS_ARE_AVAILABLE)
            else:
                continue
            old = modal["options"]
            previous = old[min(modal["index"], len(old) - 1)].get("id") if old else None
            modal["options"] = system_menu_icons(options, source)
            modal["index"] = next((i for i, row in enumerate(options) if row["id"] == previous), min(modal["index"], len(options) - 1))

    def _sharing_apply(self, protocol):
        share = self._shares[protocol]
        if not share["draft"]["root"] or not share["draft"]["networks"]:
            share["error"] = tr(Msg.SELECT_SHARED_FOLDER_AND_NETWORK)
            self._sharing_refresh()
            self._publish()
            return
        value = {**share["draft"], "owner": self._network_owner}
        if self.mock:
            state = {**share["state"], **value, "enabled": True, "state": "running"}
            self._sharing_result((protocol, "start", state, ""))
        else:
            self._sharing_request(protocol, "start", value)

    def _sharing_command(self, protocol, command, value=""):
        share = self._shares[protocol]
        if command == "open":
            self._sharing_open(protocol)
        elif command == "enabled":
            if share["state"]["enabled"]:
                if self.mock:
                    self._sharing_result((protocol, "stop", {**share["state"], "enabled": False, "state": "stopped", "urls": []}, ""))
                else:
                    self._sharing_request(protocol, "stop")
            else:
                self._sharing_apply(protocol)
        elif command == "root":
            self._text_prompt(tr(Msg.SHARED_FOLDER), tr(Msg.ENTER_SHARED_FOLDER), "sharing-" + protocol + "-root", share["draft"]["root"])
        elif command == "networks":
            self._menu(tr(Msg.ALLOWED_NETWORKS), self._sharing_network_options(protocol), source="sharing-" + protocol + "-networks")
        elif command == "toggle-network":
            share["dirty"] = True
            networks = share["draft"]["networks"]
            networks.remove(value) if value in networks else networks.append(value)
        elif command == "duration":
            self._menu(tr(Msg.ACCESS_DURATION), [self._sharing_option(protocol, self._sharing_duration(duration), "set-duration", "preferences-system-time",
                       id=str(duration), value=duration, checked=duration == share["draft"]["duration"]) for duration in (0, 3600, 21600, 43200)],
                       source="sharing-" + protocol + "-duration")
        elif command in ("set-duration", "done"):
            if command == "set-duration":
                share["draft"]["duration"] = int(value)
                share["dirty"] = True
            if self.modal.get("source") in ("sharing-" + protocol + "-networks", "sharing-" + protocol + "-duration", "sharing-" + protocol + "-addresses"):
                self._pop()
            if share["state"]["enabled"] and share["dirty"]:
                self._sharing_apply(protocol)
        elif command == "addresses":
            self._menu(tr(Msg.ACCESS_ADDRESSES), [self._sharing_option(protocol, url, "done", "network-connect", id=url) for url in share["state"].get("urls", [])]
                       or [self._sharing_option(protocol, tr(Msg.NONE), "done", "network-disconnect")], source="sharing-" + protocol + "-addresses")
        self._sharing_refresh()
        self._publish()

    def _sharing_submit(self, protocol, text):
        path = Path(text).expanduser()
        share = self._shares[protocol]
        if not path.is_absolute() or not path.is_dir():
            share["error"] = tr(Msg.CHOOSE_AN_EXISTING_FOLDER)
        else:
            share["draft"]["root"] = str(path.resolve())
            share.update(dirty=True, error="")
            if share["state"]["enabled"]:
                self._sharing_apply(protocol)
        self._sharing_refresh()

    # Old Files actions and service consumers keep working after the entry moves.
    def _network_menu(self):
        self._sharing_open("web")

    def _network_command(self, command, value=""):
        if command == "access":
            self._network_menu()
        elif command == "start":
            self._sharing_apply("web")
        elif command == "stop":
            self._sharing_request("web", "stop")
        else:
            self._sharing_command("web", "toggle-network" if command == "toggle" else command, value)

    def _network_result(self, message):
        self._sharing_result(("web", *message))

    def _network_request(self, operation, value=None):
        self._sharing_request("web", operation, value)

    def _close_sharing(self):
        self._sharing_closing = True
        self._network_timer.stop()
        if self._network_bus.isConnected():
            self._network_bus.unregisterService(self._network_owner)
        self._network_executor.shutdown(wait=False, cancel_futures=True)
