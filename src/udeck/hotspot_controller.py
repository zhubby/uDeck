"""Hotspot menus share the shell's button navigation and device ownership."""

from .hotspot import (
    HOTSPOT_BUSY,
    default_hotspot_name,
    hotspot_status,
    hotspot_summary,
    validate_hotspot_name,
)
from .i18n import Msg, tr
from .wifi import wifi_label


class HotspotControls:
    def _hotspot_options(self):
        information = self.data["wifi"]
        devices = information.get("devices", [])
        if not devices:
            return [{"id": "empty", "label": hotspot_summary(information), "action": "none", "disabled": True}]
        options = []
        if not information.get("enabled"):
            options.append({"id": "power", "label": "Wi-Fi", "checked": False,
                            "pendingAction": "wifi_power", "action": "wifi-power"})
        return options + [{"id": device["id"], "label": wifi_label(device), "deviceId": device["id"],
                           "subtitle": hotspot_status(device.get("hotspot", {})) if device.get("apSupported") else tr(Msg.HOTSPOT_NOT_SUPPORTED),
                           "action": "hotspot-device"} for device in devices]

    def _hotspot_device_options(self, device):
        hotspot = device.get("hotspot", {})
        busy = hotspot.get("status") in HOTSPOT_BUSY
        ap = device.get("mode") == "ap"
        supported = device.get("apSupported", False) and device.get("available") and device.get("managed", True)
        target = {"deviceId": device["id"], "revision": hotspot.get("revision", "")}
        options = []
        if ap:
            options.append({"id": "stop", "label": tr(Msg.HOTSPOT), "icon": "network-wireless", "checked": True,
                            "subtitle": hotspot_status(hotspot), "pendingAction": "wifi_hotspot_stop",
                            "action": "hotspot-stop", "deviceId": device["id"],
                            "disabled": busy or not hotspot.get("owned"),
                            "reason": tr(Msg.THIS_HOTSPOT_IS_MANAGED_OUTSIDE_UDECK) if not hotspot.get("owned") else tr(Msg.THIS_ADAPTER_IS_CHANGING_HOTSPOT_STATE)})
        else:
            options.append({"id": "start", "label": tr(Msg.HOTSPOT), "icon": "network-wireless", "checked": False,
                            "subtitle": hotspot_status(hotspot), "pendingAction": "wifi_hotspot_start",
                            "action": "hotspot-start", "deviceId": device["id"],
                            "disabled": not supported or not self.data["wifi"].get("enabled") or busy,
                            "reason": tr(Msg.ENABLE_WI_FI_AND_USE_AN_ADAPTER_THAT_SUPPORTS_WPA2_CCMP_HOTSPOTS)})
        if hotspot.get("message"):
            options.append({"id": "status", "label": hotspot["message"], "action": "none"})
        for field, label in (("name", tr(Msg.HOTSPOT_NAME)), ("password", tr(Msg.HOTSPOT_PASSWORD))):
            options.append({"id": field, "label": label,
                            "subtitle": (hotspot.get("ssid") or default_hotspot_name(device["interface"])) if field == "name" else (
                                tr(Msg.SAVED_IN_NETWORKMANAGER) if hotspot.get("configured") else tr(Msg.SET_A_PASSWORD_BEFORE_STARTING)),
                            "action": "hotspot-" + field, "payload": target, "deviceId": device["id"],
                            "disabled": not supported or ap or busy,
                            "reason": tr(Msg.TURN_OFF_THIS_HOTSPOT_BEFORE_EDITING_ITS_CONFIGURATION)})
        if ap:
            options.append({"id": "ip", "label": tr(Msg.IP_ADDRESS), "subtitle": ", ".join(device.get("addresses", {}).get("ip", [])) or tr(Msg.NOT_AVAILABLE), "action": "none", "wrapSubtitle": True})
        if not supported:
            options.append({"id": "unsupported", "label": tr(Msg.HOTSPOT_NOT_SUPPORTED), "subtitle": device.get("error", ""), "action": "none", "disabled": True})
        if ap and not hotspot.get("owned"):
            options.append({"id": "external", "label": tr(Msg.THIS_HOTSPOT_IS_MANAGED_OUTSIDE_UDECK), "action": "none", "disabled": True})
        return options

    def _apply_hotspot_option(self, option):
        action = option["action"]
        device = self._wifi_device(option["deviceId"])
        hotspot = device.get("hotspot", {})
        target = {"deviceId": device["id"], "revision": hotspot.get("revision", "")}
        if action == "hotspot-device":
            self._menu(wifi_label(device), self._hotspot_device_options(device), source="hotspot-device", deviceId=device["id"],
                       body=tr(Msg.HOTSPOT_UPLINK_INSTRUCTIONS))
        elif action == "hotspot-name":
            self._text_prompt(tr(Msg.HOTSPOT_NAME), tr(Msg.USE_1_32_UTF_8_BYTES), "hotspot-name",
                              text=hotspot.get("ssid") or default_hotspot_name(device["interface"]), payload=target,
                              deviceId=device["id"], hotspotRevision=target["revision"])
        elif action == "hotspot-password":
            self._hotspot_password_prompt(device, {**target, "ssid": hotspot.get("ssid") or default_hotspot_name(device["interface"])})
        elif action == "hotspot-start":
            if not hotspot.get("configured"):
                self._hotspot_password_prompt(device, {**target, "ssid": hotspot.get("ssid") or default_hotspot_name(device["interface"])})
                return
            payload = {**target, "expectedActive": device.get("activeConnection", "/")}
            if device.get("connected") or 40 <= device.get("deviceState", 0) <= 100:
                self._confirm(tr(Msg.SWITCH_THIS_ADAPTER_TO_A_HOTSPOT_PROMPT), wifi_label(device) + "\n" + tr(Msg.HOTSPOT_REPLACES_WIFI_INSTRUCTIONS),
                              {"action": "system", "systemAction": "wifi_hotspot_start", "payload": payload}, deviceId=device["id"])
            else:
                self._system("wifi_hotspot_start", payload)
        elif action == "hotspot-stop":
            self._system("wifi_hotspot_stop", {"deviceId": device["id"], "operationId": hotspot.get("operationId"), "activePath": hotspot.get("activePath")})

    def _hotspot_password_prompt(self, device, payload):
        self._text_prompt(tr(Msg.HOTSPOT_PASSWORD), tr(Msg.USE_8_63_BYTES_OR_A_64_DIGIT_HEXADECIMAL_PSK_CREDENTIALS_ARE_SAVED_BY_NETWORKMANAGER),
                          "hotspot-password", secret=True, wifiSecurity="WPA2", payload=payload,
                          deviceId=device["id"], hotspotRevision=payload["revision"])

    def _submit_hotspot_text(self, modal, text):
        payload = modal["payload"]
        device = self._wifi_device(payload["deviceId"])
        if modal["purpose"] == "hotspot-name":
            payload = {**payload, "ssid": validate_hotspot_name(text)}
            if not device.get("hotspot", {}).get("configured"):
                self._hotspot_password_prompt(device, payload)
            else:
                self._system("wifi_hotspot_configure", payload)
        else:
            self._system("wifi_hotspot_configure", {**payload, "password": text})
