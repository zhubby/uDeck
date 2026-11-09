"""Wi-Fi menus keep stable device, network and profile identities."""

from .hotspot import HOTSPOT_BUSY
from .hotspot_controller import HotspotControls
from .i18n import tr
from .wifi import network_key, wifi_label, wifi_status


class WifiControls(HotspotControls):
    def _wifi_options(self):
        information = self.data["wifi"]
        if not information.get("available"):
            return [{"id": "unavailable", "label": information.get("error") or tr('未检测到无线网卡'), "action": "none", "disabled": True}]
        options = [{"id": "power", "label": tr('关闭全部 Wi-Fi') if information["enabled"] else tr('开启全部 Wi-Fi'),
                    "subtitle": tr('影响所有无线网卡'), "action": "wifi-power"}]
        return options + [{"id": device["id"], "deviceId": device["id"], "label": wifi_label(device),
                           "subtitle": wifi_status(device, information["enabled"]), "action": "wifi-device", "icon": "network-wireless"}
                          for device in information.get("devices", [])]

    def _wifi_device(self, device_id):
        device = next((device for device in self.data["wifi"].get("devices", []) if device["id"] == device_id), None)
        if device is None:
            raise RuntimeError(tr('目标无线网卡已移除，请重新选择'))
        return device

    def _wifi_usable(self, device):
        return (self.data["wifi"].get("enabled") and device.get("available") and device.get("managed", True)
                and device.get("deviceState") not in (10, 20) and device.get("mode") != "ap"
                and device.get("hotspot", {}).get("status") not in HOTSPOT_BUSY)

    @staticmethod
    def _network_key(network):
        return network.get("key") or network_key(network.get("ssid", network["name"].encode()), network.get("securityId", "open" if not network.get("secured") else "wpa3" if network["security"] == "WPA3" else "wpa2"))

    def _wifi_device_options(self, device):
        if device.get("mode") == "ap" or device.get("hotspot", {}).get("status") in HOTSPOT_BUSY:
            return [{"id": "hotspot", "label": tr("Manage hotspot"), "action": "hotspot-device", "deviceId": device["id"]},
                    {"id": "saved", "label": tr('已保存的网络'), "action": "wifi-saved", "deviceId": device["id"]}]
        usable, identifier = self._wifi_usable(device), device["id"]
        scan = device.get("scan", {})
        scan_label = tr("Scanning…") if scan.get("status") == "scanning" else tr('搜索网络')
        options = [{"id": "scan", "label": scan_label, "action": "system", "systemAction": "wifi_scan",
                    "payload": {"deviceId": identifier}, "disabled": not usable or scan.get("status") == "scanning"},
                   {"id": "saved", "label": tr('已保存的网络'), "subtitle": tr('{value0} 个兼容配置', value0=len(device.get('saved', []))),
                    "action": "wifi-saved", "deviceId": identifier}]
        if device.get("connected") or 40 <= device.get("deviceState", 0) <= 100:
            options.append({"id": "disconnect", "label": tr('断开此网卡'), "action": "wifi-disconnect", "deviceId": identifier, "disabled": not usable})
        if scan.get("status") == "timeout":
            options.append({"id": "scan-timeout", "label": tr("Scan timed out. Search again to retry."), "action": "none", "disabled": True})
        if device.get("error"):
            options.append({"id": "failure", "label": device["error"], "action": "none", "disabled": True})
        for network in device.get("networks", []):
            status = tr('已连接 · ') if network.get("connected") else tr('正在连接 · ') if network.get("connecting") else tr('已保存 · ') if network.get("saved") else ""
            options.append({"id": "network:" + self._network_key(network), "label": network["name"],
                            "subtitle": status + tr('{strength}% · {security}', strength=network["strength"], security=network["security"]),
                            "action": "wifi-connect", "deviceId": identifier, "network": network})
        if not device.get("networks"):
            options.append({"id": "empty", "label": tr('尚未发现网络') if usable else wifi_status(device, self.data["wifi"].get("enabled")), "action": "none", "disabled": True})
        return options

    def _wifi_saved_options(self, device):
        return [{"id": profile.get("uuid") or profile["id"], "label": profile["name"],
                 "subtitle": profile.get("blocked") or (tr("Auto-join on") if profile.get("autoconnect", True) else tr("Auto-join off")),
                 "action": "wifi-saved-connect", "deviceId": device["id"], "profile": profile}
                for profile in device.get("saved", [])] or [{"id": "empty", "label": tr('没有兼容的已保存网络'), "action": "none", "disabled": True}]

    def _wifi_target(self, modal, device):
        network = next((entry for entry in device.get("networks", []) if self._network_key(entry) == modal.get("networkKey")), None)
        profiles = [entry for entry in device.get("saved", []) if
                    entry.get("ssid") == modal.get("ssid") and entry.get("keyManagement", "") in modal.get("keyManagement", [""])]
        profile = next((entry for entry in profiles if entry.get("uuid") == modal.get("profileUuid")), None)
        if profile is None and not modal.get("profileUuid") and len(profiles) == 1:
            profile = profiles[0]
        operation = device.get("operation", {})
        if not modal.get("profileExplicit") and modal.get("networkKey") and operation.get("networkKey") == modal["networkKey"]:
            profile = next((entry for entry in profiles if entry.get("uuid") == operation.get("profileUuid")), profile)
        if profile:
            modal["profileUuid"] = profile.get("uuid", "")
        return network, profile, profiles

    def _wifi_network_options(self, modal, device):
        network, profile, _ = self._wifi_target(modal, device)
        usable, operation = self._wifi_usable(device), device.get("operation", {})
        matching_operation = (operation.get("networkKey") == modal.get("networkKey") or
                              (profile and operation.get("profileUuid") == profile.get("uuid")))
        joining = matching_operation and operation.get("status") in ("preparing", "connecting")
        busy = operation.get("status") in ("preparing", "connecting")
        connected = profile.get("active", False) if profile else bool(network and network.get("connected"))
        options = []
        if matching_operation and operation.get("message"):
            options.append({"id": "status", "label": operation["message"], "subtitle": tr("Still waiting. You can cancel joining or keep waiting.") if operation.get("timedOut") else "", "action": "none", "disabled": True})
        if joining:
            options.append({"id": "cancel-join", "label": tr("Cancel joining"), "action": "system", "systemAction": "wifi_cancel_connect",
                            "payload": {"deviceId": device["id"], "operationId": operation["id"]}})
        label = tr("Rejoin network") if connected else tr("Retry joining") if matching_operation and operation.get("status") == "failed" else tr("Join network")
        reason = profile.get("blocked") if profile else ""
        options.append({"id": "join", "label": label, "action": "wifi-join", "deviceId": device["id"],
                        "networkKey": modal.get("networkKey"), "profileUuid": profile.get("uuid", "") if profile else "",
                        "reconnect": connected, "disabled": not usable or busy or bool((profile or network or {}).get("unsupported")) or (not network and bool(reason)),
                        "subtitle": tr("A separate configuration will be created for this adapter") if reason and network else "",
                        "reason": reason or tr("This adapter cannot join this network right now")})
        if connected:
            options.append({"id": "disconnect", "label": tr("Disconnect"), "action": "wifi-disconnect", "deviceId": device["id"], "disabled": not usable})
        if profile:
            blocked = profile.get("mutationBlocked") or profile.get("blocked") or (tr("This saved configuration is read-only") if profile.get("readOnly") else "")
            disabled = bool(blocked) or not profile.get("uuid") or busy
            target = {"deviceId": device["id"], "profileUuid": profile.get("uuid", ""), "revision": profile.get("revision", "")}
            options.append({"id": "auto-join", "label": tr("Disable auto-join") if profile.get("autoconnect", True) else tr("Enable auto-join"),
                            "subtitle": blocked or (tr("Auto-join on") if profile.get("autoconnect", True) else tr("Auto-join off")),
                            "action": "wifi-autoconnect", "payload": {**target, "enabled": not profile.get("autoconnect", True)}, "disabled": disabled, "reason": blocked})
            if profile.get("keyManagement") in ("wpa-psk", "sae"):
                options.append({"id": "password", "label": tr("Enter password again") if matching_operation and operation.get("status") == "failed" else tr("Change password"), "action": "wifi-password", "payload": target,
                                "security": "WPA3" if profile["keyManagement"] == "sae" else "WPA2", "disabled": disabled, "reason": blocked})
            options.append({"id": "forget", "label": tr("Forget network"), "action": "wifi-forget", "payload": target,
                            "disabled": disabled, "reason": blocked})
        options.append({"id": "details", "label": tr("Network details"), "action": "wifi-details", "deviceId": device["id"],
                        "networkKey": modal.get("networkKey"), "profileUuid": modal.get("profileUuid", "")})
        return options

    def _wifi_profile_options(self, modal, device):
        _, _, profiles = self._wifi_target({**modal, "profileUuid": ""}, device)
        return [{"id": profile.get("uuid") or profile["id"], "label": profile["name"],
                 "subtitle": (tr("Current configuration") + " · " if profile.get("active") else "") + (profile.get("uuid") or profile["id"]),
                 "action": "wifi-profile", "deviceId": device["id"], "networkKey": modal.get("networkKey"),
                 "profileUuid": profile.get("uuid", ""), "network": modal.get("network"), "profile": profile}
                for profile in profiles] or [{"id": "empty", "label": tr('没有兼容的已保存网络'), "action": "none", "disabled": True}]

    def _wifi_details_options(self, modal, device):
        network, profile, _ = self._wifi_target(modal, device)
        connected = bool(profile and profile.get("active")) or bool(network and network.get("connected"))
        unavailable = tr("Not available")
        pairs = [(tr("SSID"), modal["title"]), (tr("Adapter"), wifi_label(device)),
                 (tr("Status"), wifi_status(device, self.data["wifi"].get("enabled")) if connected else tr("Not connected to this network")),
                 (tr("Security"), network["security"] if network else modal.get("security", unavailable)),
                 (tr("Signal"), f"{network['strength']}%" if network else unavailable)]
        addresses = device.get("addresses", {}) if connected else {}
        pairs += [(tr(label), ", ".join(addresses.get(field, [])) or unavailable) for label, field in (("IP address", "ip"), ("Gateway", "gateway"), ("DNS", "dns"))]
        if profile:
            pairs.append((tr("Saved configuration"), profile["name"] + " · " + profile.get("uuid", "")))
        return [{"id": str(index), "label": label, "subtitle": value, "action": "none", "wrapSubtitle": True} for index, (label, value) in enumerate(pairs)]

    def _refresh_wifi_network(self, modal, device):
        modal["body"] = wifi_label(device) + "\n" + wifi_status(device, self.data["wifi"].get("enabled"))
        if modal["source"] == "wifi-profiles":
            return self._wifi_profile_options(modal, device)
        if modal["source"] == "wifi-details":
            return self._wifi_details_options(modal, device)
        return self._wifi_network_options(modal, device)

    def _open_wifi_network(self, device, network=None, profile=None, choose_profile=True):
        if network is None and profile:
            network = next((entry for entry in device.get("networks", []) if entry["ssid"] == profile["ssid"] and
                            profile.get("keyManagement", "") in (entry.get("keyManagement") or [""])), None)
        ssid = network["ssid"] if network else profile["ssid"]
        keys = network.get("keyManagement") or [""] if network else [profile.get("keyManagement", "")]
        security = network["security"] if network else "WPA3" if profile.get("keyManagement") == "sae" else "WPA2" if profile.get("keyManagement") else tr('开放网络')
        modal = {"deviceId": device["id"], "networkKey": self._network_key(network) if network else network_key(ssid, "wpa3" if profile.get("keyManagement") == "sae" else "wpa2" if profile.get("keyManagement") else "open"),
                 "profileExplicit": bool(profile), "profileUuid": profile.get("uuid", "") if profile else "", "ssid": ssid, "keyManagement": keys,
                 "network": network, "security": security, "title": bytes(ssid).decode("utf-8", errors="replace")}
        matches = self._wifi_target(modal, device)[2]
        source = "wifi-profiles" if choose_profile and not profile and len(matches) > 1 else "wifi-network"
        modal["source"] = source
        options = self._refresh_wifi_network(modal, device)
        self._menu(modal.pop("title"), options, **modal)

    def _apply_wifi_option(self, option):
        action = option["action"]
        if action == "wifi-power":
            enabled = not self.data["wifi"].get("enabled")
            if enabled:
                self._system("wifi_power", {"enabled": True})
            else:
                self._confirm(tr('关闭全部 Wi-Fi？'), tr('这会断开所有无线网卡的连接，并可能中断 SSH。'),
                              {"action": "system", "systemAction": "wifi_power", "payload": {"enabled": False}})
        elif action == "wifi-device":
            device = self._wifi_device(option["deviceId"])
            self._menu(wifi_label(device), self._wifi_device_options(device), source="wifi-device", deviceId=device["id"], body=wifi_status(device, self.data["wifi"].get("enabled")))
        elif action == "wifi-saved":
            device = self._wifi_device(option["deviceId"])
            self._menu(tr('已保存的网络'), self._wifi_saved_options(device), source="wifi-saved", deviceId=device["id"], body=wifi_label(device))
        elif action in ("wifi-connect", "wifi-saved-connect", "wifi-profile"):
            device = self._wifi_device(option["deviceId"])
            self._open_wifi_network(device, option.get("network"), option.get("profile"), choose_profile=action != "wifi-profile")
        elif action == "wifi-join":
            device = self._wifi_device(option["deviceId"])
            network = next((entry for entry in device.get("networks", []) if self._network_key(entry) == option.get("networkKey")), None)
            profile = next((entry for entry in device.get("saved", []) if entry.get("uuid") == option.get("profileUuid")), None)
            if profile and not profile.get("blocked"):
                operation = "wifi_reconnect" if option.get("reconnect") else "wifi_connect_saved"
                payload = {"deviceId": device["id"], "profileUuid": profile["uuid"]}
            elif network:
                operation, payload = "wifi_connect", {"deviceId": device["id"], "networkKey": self._network_key(network)}
            else:
                raise RuntimeError(tr('此网卡已搜索不到该网络，请重新搜索'))
            body = wifi_label(device)
            if device.get("connected") or device.get("deviceState") == 100:
                body += "\n" + tr("This replaces this adapter's current connection and may interrupt SSH.")
            if network and not network.get("secured"):
                body += "\n" + tr("This is an open network. Traffic may not be protected.")
            if profile or not network or not network.get("secured") or device.get("deviceState") == 100:
                self._confirm(tr("Join {name}?", name=self.modal["title"]), body,
                              {"action": "system", "systemAction": operation, "payload": payload}, deviceId=device["id"])
            else:
                self._system(operation, payload)
        elif action == "wifi-disconnect":
            device = self._wifi_device(option["deviceId"])
            self._confirm(tr('断开此网卡？'), wifi_label(device) + tr('\n只断开这张网卡，可能中断经由它的 SSH 连接。'),
                          {"action": "system", "systemAction": "wifi_disconnect", "payload": {"deviceId": device["id"]}}, deviceId=device["id"])
        elif action == "wifi-forget":
            self._confirm(tr("Forget this saved network?"), self.modal["title"] + "\n" + tr("The selected configuration and password will be removed. If connected, this adapter will disconnect. Other saved configurations are kept."),
                          {"action": "system", "systemAction": "wifi_forget", "payload": option["payload"]},
                          deviceId=option["payload"]["deviceId"], profileUuid=option["payload"]["profileUuid"])
        elif action == "wifi-autoconnect":
            self._system("wifi_set_autoconnect", option["payload"])
        elif action == "wifi-password":
            self._text_prompt(tr("Change Wi-Fi password"), self.modal["title"] + "\n" + tr("Save the new password, then choose when to rejoin."), "wifi-password",
                              secret=True, wifiSecurity=option["security"], payload=option["payload"],
                              deviceId=option["payload"]["deviceId"], profileUuid=option["payload"]["profileUuid"])
        elif action == "wifi-details":
            device = self._wifi_device(option["deviceId"])
            modal = {**self.modal, "source": "wifi-details"}
            options = self._wifi_details_options(modal, device)
            for field in ("key", "options", "index", "kind"):
                modal.pop(field, None)
            self._menu(modal.pop("title"), options, **modal)
