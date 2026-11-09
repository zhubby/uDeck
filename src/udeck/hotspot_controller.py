"""Hotspot menus share the shell's button navigation and device ownership."""

from .hotspot import (
    HOTSPOT_BUSY,
    default_hotspot_name,
    hotspot_status,
    hotspot_summary,
    validate_hotspot_name,
)
from .i18n import tr
from .wifi import wifi_label


class HotspotControls:
    def _hotspot_options(self):
        information = self.data["wifi"]
        devices = information.get("devices", [])
        if not devices:
            return [{"id": "empty", "label": hotspot_summary(information), "action": "none", "disabled": True}]
        options = []
        if not information.get("enabled"):
            options.append({"id": "power", "label": tr("Enable Wi-Fi to start a hotspot"), "action": "wifi-power"})
        return options + [{"id": device["id"], "label": wifi_label(device), "deviceId": device["id"],
                           "subtitle": hotspot_status(device.get("hotspot", {})) if device.get("apSupported") else tr("Hotspot not supported"),
                           "action": "hotspot-device"} for device in devices]

    def _hotspot_device_options(self, device):
        hotspot = device.get("hotspot", {})
        busy = hotspot.get("status") in HOTSPOT_BUSY
        ap = device.get("mode") == "ap"
        supported = device.get("apSupported", False) and device.get("available") and device.get("managed", True)
        target = {"deviceId": device["id"], "revision": hotspot.get("revision", "")}
        options = [{"id": "status", "label": hotspot_status(hotspot), "subtitle": hotspot.get("message", ""),
                    "action": "none", "wrapSubtitle": True}]
        if ap:
            options.append({"id": "stop", "label": tr("Turn off hotspot"), "action": "hotspot-stop", "deviceId": device["id"],
                            "disabled": busy or not hotspot.get("owned"),
                            "reason": tr("This hotspot is managed outside uDeck") if not hotspot.get("owned") else tr("This adapter is changing hotspot state")})
        else:
            options.append({"id": "start", "label": tr("Turn on hotspot"), "action": "hotspot-start", "deviceId": device["id"],
                            "disabled": not supported or not self.data["wifi"].get("enabled") or busy,
                            "reason": tr("Enable Wi-Fi and use an adapter that supports WPA2/CCMP hotspots")})
        for field, label in (("name", tr("Hotspot name")), ("password", tr("Hotspot password"))):
            options.append({"id": field, "label": label,
                            "subtitle": (hotspot.get("ssid") or default_hotspot_name(device["interface"])) if field == "name" else (
                                tr("Saved in NetworkManager") if hotspot.get("configured") else tr("Set a password before starting")),
                            "action": "hotspot-" + field, "payload": target, "deviceId": device["id"],
                            "disabled": not supported or ap or busy,
                            "reason": tr("Turn off this hotspot before editing its configuration")})
        if ap:
            options.append({"id": "ip", "label": tr("IP address"), "subtitle": ", ".join(device.get("addresses", {}).get("ip", [])) or tr("Not available"), "action": "none", "wrapSubtitle": True})
        if not supported:
            options.append({"id": "unsupported", "label": tr("Hotspot not supported"), "subtitle": device.get("error", ""), "action": "none", "disabled": True})
        if ap and not hotspot.get("owned"):
            options.append({"id": "external", "label": tr("This hotspot is managed outside uDeck"), "action": "none", "disabled": True})
        return options

    def _apply_hotspot_option(self, option):
        action = option["action"]
        device = self._wifi_device(option["deviceId"])
        hotspot = device.get("hotspot", {})
        target = {"deviceId": device["id"], "revision": hotspot.get("revision", "")}
        if action == "hotspot-device":
            self._menu(wifi_label(device), self._hotspot_device_options(device), source="hotspot-device", deviceId=device["id"],
                       body=tr("Share the current internet connection. Without an uplink, devices can still communicate locally."))
        elif action == "hotspot-name":
            self._text_prompt(tr("Hotspot name"), tr("Use 1–32 UTF-8 bytes"), "hotspot-name",
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
                self._confirm(tr("Switch this adapter to a hotspot?"), wifi_label(device) + "\n" + tr("This replaces this adapter's Wi-Fi connection and may interrupt SSH. Turning off the hotspot will try to restore it."),
                              {"action": "system", "systemAction": "wifi_hotspot_start", "payload": payload}, deviceId=device["id"])
            else:
                self._system("wifi_hotspot_start", payload)
        elif action == "hotspot-stop":
            self._system("wifi_hotspot_stop", {"deviceId": device["id"], "operationId": hotspot.get("operationId"), "activePath": hotspot.get("activePath")})

    def _hotspot_password_prompt(self, device, payload):
        self._text_prompt(tr("Hotspot password"), tr("Use 8–63 bytes or a 64-digit hexadecimal PSK. Credentials are saved by NetworkManager."),
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
