"""Wi-Fi menus keep stable device, network and profile identities."""

from .hotspot import HOTSPOT_BUSY
from .hotspot_controller import HotspotControls
from .i18n import Msg, tr
from .wifi import network_key, wifi_label, wifi_status


class WifiControls(HotspotControls):
    def _wifi_options(self):
        information = self.data["wifi"]
        if not information.get("available"):
            return [{"id": "unavailable", "label": information.get("error") or tr(Msg.NO_WI_FI_ADAPTERS_FOUND), "action": "none", "disabled": True}]
        options = [{"id": "power", "label": "Wi-Fi", "checked": bool(information["enabled"]),
                    "pendingAction": "wifi_power", "action": "wifi-power"}]
        return options + [{"id": device["id"], "deviceId": device["id"], "label": wifi_label(device),
                           "subtitle": wifi_status(device, information["enabled"]), "action": "wifi-device", "icon": "network-wireless"}
                          for device in information.get("devices", [])]

    def _wifi_device(self, device_id):
        device = next((device for device in self.data["wifi"].get("devices", []) if device["id"] == device_id), None)
        if device is None:
            raise RuntimeError(tr(Msg.THE_TARGET_WI_FI_ADAPTER_WAS_REMOVED_SELECT_AN_ADAPTER_AGAIN))
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
            return [{"id": "hotspot", "label": tr(Msg.MANAGE_HOTSPOT), "action": "hotspot-device", "deviceId": device["id"]},
                    {"id": "saved", "label": tr(Msg.SAVED_NETWORKS), "action": "wifi-saved", "deviceId": device["id"]}]
        usable, identifier = self._wifi_usable(device), device["id"]
        scan = device.get("scan", {})
        scan_label = tr(Msg.SCANNING) if scan.get("status") == "scanning" else tr(Msg.SCAN_FOR_NETWORKS)
        options = [{"id": "scan", "label": scan_label, "action": "system", "systemAction": "wifi_scan",
                    "payload": {"deviceId": identifier}, "disabled": not usable or scan.get("status") == "scanning"},
                   {"id": "saved", "label": tr(Msg.SAVED_NETWORKS), "subtitle": tr(Msg.COMPATIBLE_PROFILES_VALUE0, value0=len(device.get('saved', []))),
                    "action": "wifi-saved", "deviceId": identifier}]
        if device.get("connected") or 40 <= device.get("deviceState", 0) <= 100:
            options.append({"id": "disconnect", "label": tr(Msg.DISCONNECT_THIS_ADAPTER), "action": "wifi-disconnect", "deviceId": identifier, "disabled": not usable})
        if scan.get("status") == "timeout":
            options.append({"id": "scan-timeout", "label": tr(Msg.SCAN_TIMED_OUT_SEARCH_AGAIN_TO_RETRY), "action": "none", "disabled": True})
        if device.get("error"):
            options.append({"id": "failure", "label": device["error"], "action": "none", "disabled": True})
        for network in device.get("networks", []):
            status = tr(Msg.CONNECTED_PREFIX) if network.get("connected") else tr(Msg.CONNECTING_PREFIX) if network.get("connecting") else tr(Msg.SAVED_PREFIX) if network.get("saved") else ""
            options.append({"id": "network:" + self._network_key(network), "label": network["name"],
                            "subtitle": status + tr(Msg.STRENGTH_SECURITY, strength=network["strength"], security=network["security"]),
                            "action": "wifi-connect", "deviceId": identifier, "network": network})
        if not device.get("networks"):
            options.append({"id": "empty", "label": tr(Msg.NO_NETWORKS_FOUND_YET) if usable else wifi_status(device, self.data["wifi"].get("enabled")), "action": "none", "disabled": True})
        return options

    def _wifi_saved_options(self, device):
        return [{"id": profile.get("uuid") or profile["id"], "label": profile["name"],
                 "subtitle": profile.get("blocked") or (tr(Msg.AUTO_JOIN_ON) if profile.get("autoconnect", True) else tr(Msg.AUTO_JOIN_OFF)),
                 "action": "wifi-saved-connect", "deviceId": device["id"], "profile": profile}
                for profile in device.get("saved", [])] or [{"id": "empty", "label": tr(Msg.NO_COMPATIBLE_SAVED_NETWORKS), "action": "none", "disabled": True}]

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
            options.append({"id": "status", "label": operation["message"], "subtitle": tr(Msg.STILL_WAITING_YOU_CAN_CANCEL_JOINING_OR_KEEP_WAITING) if operation.get("timedOut") else "", "action": "none", "disabled": True})
        if joining:
            options.append({"id": "cancel-join", "label": tr(Msg.CANCEL_JOINING), "action": "system", "systemAction": "wifi_cancel_connect",
                            "payload": {"deviceId": device["id"], "operationId": operation["id"]}})
        label = tr(Msg.REJOIN_NETWORK) if connected else tr(Msg.RETRY_JOINING) if matching_operation and operation.get("status") == "failed" else tr(Msg.JOIN_NETWORK)
        reason = profile.get("blocked") if profile else ""
        options.append({"id": "join", "label": label, "action": "wifi-join", "deviceId": device["id"],
                        "networkKey": modal.get("networkKey"), "profileUuid": profile.get("uuid", "") if profile else "",
                        "reconnect": connected, "disabled": not usable or busy or bool((profile or network or {}).get("unsupported")) or (not network and bool(reason)),
                        "subtitle": tr(Msg.A_SEPARATE_CONFIGURATION_WILL_BE_CREATED_FOR_THIS_ADAPTER) if reason and network else "",
                        "reason": reason or tr(Msg.THIS_ADAPTER_CANNOT_JOIN_THIS_NETWORK_RIGHT_NOW)})
        if connected:
            options.append({"id": "disconnect", "label": tr(Msg.DISCONNECT), "action": "wifi-disconnect", "deviceId": device["id"], "disabled": not usable})
        if profile:
            blocked = profile.get("mutationBlocked") or profile.get("blocked") or (tr(Msg.THIS_SAVED_CONFIGURATION_IS_READ_ONLY) if profile.get("readOnly") else "")
            disabled = bool(blocked) or not profile.get("uuid") or busy
            target = {"deviceId": device["id"], "profileUuid": profile.get("uuid", ""), "revision": profile.get("revision", "")}
            options.append({"id": "auto-join", "label": tr(Msg.AUTO_JOIN), "checked": bool(profile.get("autoconnect", True)),
                            "subtitle": blocked, "pendingAction": "wifi_set_autoconnect",
                            "action": "wifi-autoconnect", "payload": {**target, "enabled": not profile.get("autoconnect", True)}, "disabled": disabled, "reason": blocked})
            if profile.get("keyManagement") in ("wpa-psk", "sae"):
                options.append({"id": "password", "label": tr(Msg.ENTER_PASSWORD_AGAIN) if matching_operation and operation.get("status") == "failed" else tr(Msg.CHANGE_PASSWORD), "action": "wifi-password", "payload": target,
                                "security": "WPA3" if profile["keyManagement"] == "sae" else "WPA2", "disabled": disabled, "reason": blocked})
            options.append({"id": "forget", "label": tr(Msg.FORGET_NETWORK), "action": "wifi-forget", "payload": target,
                            "disabled": disabled, "reason": blocked})
        options.append({"id": "details", "label": tr(Msg.NETWORK_DETAILS), "action": "wifi-details", "deviceId": device["id"],
                        "networkKey": modal.get("networkKey"), "profileUuid": modal.get("profileUuid", "")})
        return options

    def _wifi_profile_options(self, modal, device):
        _, _, profiles = self._wifi_target({**modal, "profileUuid": ""}, device)
        return [{"id": profile.get("uuid") or profile["id"], "label": profile["name"],
                 "subtitle": (tr(Msg.CURRENT_CONFIGURATION) + " · " if profile.get("active") else "") + (profile.get("uuid") or profile["id"]),
                 "action": "wifi-profile", "deviceId": device["id"], "networkKey": modal.get("networkKey"),
                 "profileUuid": profile.get("uuid", ""), "network": modal.get("network"), "profile": profile}
                for profile in profiles] or [{"id": "empty", "label": tr(Msg.NO_COMPATIBLE_SAVED_NETWORKS), "action": "none", "disabled": True}]

    def _wifi_details_options(self, modal, device):
        network, profile, _ = self._wifi_target(modal, device)
        connected = bool(profile and profile.get("active")) or bool(network and network.get("connected"))
        unavailable = tr(Msg.NOT_AVAILABLE)
        pairs = [(tr(Msg.SSID), modal["title"]), (tr(Msg.ADAPTER), wifi_label(device)),
                 (tr(Msg.STATUS), wifi_status(device, self.data["wifi"].get("enabled")) if connected else tr(Msg.NOT_CONNECTED_TO_THIS_NETWORK)),
                 (tr(Msg.SECURITY), network["security"] if network else modal.get("security", unavailable)),
                 (tr(Msg.SIGNAL), f"{network['strength']}%" if network else unavailable)]
        addresses = device.get("addresses", {}) if connected else {}
        pairs += [(tr(key), ", ".join(addresses.get(field, [])) or unavailable)
                  for key, field in ((Msg.IP_ADDRESS, "ip"), (Msg.GATEWAY, "gateway"), (Msg.DNS, "dns"))]
        if profile:
            pairs.append((tr(Msg.SAVED_CONFIGURATION), profile["name"] + " · " + profile.get("uuid", "")))
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
        security = network["security"] if network else "WPA3" if profile.get("keyManagement") == "sae" else "WPA2" if profile.get("keyManagement") else tr(Msg.OPEN_NETWORK)
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
                self._confirm(tr(Msg.TURN_OFF_ALL_WI_FI_PROMPT), tr(Msg.THIS_DISCONNECTS_ALL_WI_FI_ADAPTERS_AND_MAY_INTERRUPT_SSH),
                              {"action": "system", "systemAction": "wifi_power", "payload": {"enabled": False}})
        elif action == "wifi-device":
            device = self._wifi_device(option["deviceId"])
            self._menu(wifi_label(device), self._wifi_device_options(device), source="wifi-device", deviceId=device["id"], body=wifi_status(device, self.data["wifi"].get("enabled")))
        elif action == "wifi-saved":
            device = self._wifi_device(option["deviceId"])
            self._menu(tr(Msg.SAVED_NETWORKS), self._wifi_saved_options(device), source="wifi-saved", deviceId=device["id"], body=wifi_label(device))
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
                raise RuntimeError(tr(Msg.THIS_ADAPTER_CAN_NO_LONGER_SEE_THE_NETWORK_SCAN_AGAIN))
            body = wifi_label(device)
            if device.get("connected") or device.get("deviceState") == 100:
                body += "\n" + tr(Msg.THIS_REPLACES_THIS_ADAPTER_S_CURRENT_CONNECTION_AND_MAY_INTERRUPT_SSH)
            if network and not network.get("secured"):
                body += "\n" + tr(Msg.THIS_IS_AN_OPEN_NETWORK_TRAFFIC_MAY_NOT_BE_PROTECTED)
            if profile or not network or not network.get("secured") or device.get("deviceState") == 100:
                self._confirm(tr(Msg.JOIN_NAME_PROMPT, name=self.modal["title"]), body,
                              {"action": "system", "systemAction": operation, "payload": payload}, deviceId=device["id"])
            else:
                self._system(operation, payload)
        elif action == "wifi-disconnect":
            device = self._wifi_device(option["deviceId"])
            self._confirm(tr(Msg.DISCONNECT_THIS_ADAPTER_PROMPT), wifi_label(device) + tr(Msg.ONLY_THIS_ADAPTER_WILL_DISCONNECT_SSH_THROUGH_IT_MAY_BE_INTERRUPTED_NOTICE),
                          {"action": "system", "systemAction": "wifi_disconnect", "payload": {"deviceId": device["id"]}}, deviceId=device["id"])
        elif action == "wifi-forget":
            self._confirm(tr(Msg.FORGET_THIS_SAVED_NETWORK_PROMPT), self.modal["title"] + "\n" + tr(Msg.FORGET_NETWORK_INSTRUCTIONS),
                          {"action": "system", "systemAction": "wifi_forget", "payload": option["payload"]},
                          deviceId=option["payload"]["deviceId"], profileUuid=option["payload"]["profileUuid"])
        elif action == "wifi-autoconnect":
            self._system("wifi_set_autoconnect", option["payload"])
        elif action == "wifi-password":
            self._text_prompt(tr(Msg.CHANGE_WI_FI_PASSWORD), self.modal["title"] + "\n" + tr(Msg.SAVE_THE_NEW_PASSWORD_THEN_CHOOSE_WHEN_TO_REJOIN), "wifi-password",
                              secret=True, wifiSecurity=option["security"], payload=option["payload"],
                              deviceId=option["payload"]["deviceId"], profileUuid=option["payload"]["profileUuid"])
        elif action == "wifi-details":
            device = self._wifi_device(option["deviceId"])
            modal = {**self.modal, "source": "wifi-details"}
            options = self._wifi_details_options(modal, device)
            for field in ("key", "options", "index", "kind"):
                modal.pop(field, None)
            self._menu(modal.pop("title"), options, **modal)
