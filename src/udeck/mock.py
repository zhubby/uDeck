from copy import deepcopy

from PySide6.QtCore import QObject, QTimer, Signal

from .i18n import tr

MOCK_APPS = [
    ("terminal", tr('终端'), "Terminal", "utilities-terminal", "System"),
    ("code", tr('代码编辑器'), "Visual Studio Code", "visual-studio-code", "Development"),
    ("firefox", tr('浏览器'), "Firefox", "firefox", "Network"),
    ("files", tr('文件管理'), tr('个人文件与存储'), "system-file-manager", "Utility"),
    ("retroarch", "RetroArch", tr('模拟器与游戏'), "com.libretro.RetroArch", "Game"),
    ("notes", tr('文本编辑器'), "Mousepad", "accessories-text-editor", "Utility"),
    ("monitor", tr('系统监视器'), tr('运行状态'), "utilities-system-monitor", "System"),
    ("calculator", tr('计算器'), tr('日常计算'), "accessories-calculator", "Utility"),
    ("viewer", tr('图片查看器'), tr('图片与照片'), "image-x-generic", "Graphics"),
    ("geany", "Geany", tr('轻量开发环境'), "geany", "Development"),
]


def mock_apps():
    return [{"id": identifier + ".desktop", "name": name, "subtitle": subtitle,
             "icon": icon, "category": category}
            for identifier, name, subtitle, icon, category in MOCK_APPS]


def initial_state():
    return {
        "wifi": {"available": False, "enabled": False, "devices": []},
        "bluetooth": {"available": False, "powered": False, "discovering": False, "devices": []},
        "audio": {"available": False, "volume": 0, "muted": False, "outputs": [], "inputs": [], "cards": []},
        "brightness": {"available": False, "value": 0},
        "battery": {"available": False, "capacity": 0, "charging": False},
    }


class MockBackend(QObject):
    updated = Signal(object)
    failed = Signal(object)
    operationFailed = Signal(str, object)
    prompt = Signal(object)
    completed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.actions = []
        self.state = initial_state()
        self.state.update({
            "wifi": {"available": True, "enabled": True, "devices": [
                {"id": "builtin", "name": tr('内置无线网卡'), "interface": "wlan0", "kind": "builtin",
                 "available": True, "managed": True, "deviceState": 100, "connected": "Workshop", "strength": 92, "activeProfile": "workshop-profile",
                 "networks": [
                     {"id": "builtin-workshop", "name": "Workshop", "strength": 92, "secured": True, "connected": True, "saved": True, "security": "WPA2"},
                     {"id": "builtin-guest", "name": "Guest", "strength": 54, "secured": False, "connected": False, "security": tr('开放网络')},
                 ],
                 "saved": [{"id": "workshop-profile", "name": "Workshop", "ssid": list(b"Workshop"), "keyManagement": "wpa-psk", "multiConnect": 0}]},
                {"id": "usb", "name": tr('USB 无线网卡'), "interface": "wlx001122334455", "kind": "usb",
                 "available": True, "managed": True, "deviceState": 30, "connected": "", "strength": None,
                 "networks": [
                     {"id": "usb-workshop", "name": "Workshop", "strength": 98, "secured": True, "connected": False, "saved": True, "security": "WPA2"},
                     {"id": "usb-studio", "name": "Studio 5G", "strength": 86, "secured": True, "connected": False, "security": "WPA3"},
                     {"id": "usb-guest", "name": "Guest", "strength": 68, "secured": False, "connected": False, "security": tr('开放网络')},
                 ],
                 "saved": [{"id": "workshop-profile", "name": "Workshop", "ssid": list(b"Workshop"), "keyManagement": "wpa-psk", "multiConnect": 0,
                            "blocked": tr('另一张网卡正在使用 · 可从网络列表另建连接')}]},
            ]},
            "bluetooth": {"available": True, "powered": True, "discovering": False,
                          "devices": [{"id": "headphones", "name": tr('无线耳机'), "paired": True, "connected": True, "trusted": True},
                                      {"id": "keyboard", "name": tr('蓝牙键盘'), "paired": True, "connected": False, "trusted": True}]},
            "audio": {"available": True, "volume": 0.46, "muted": False,
                      "outputs": [{"id": "speaker", "name": tr('内置扬声器'), "active": True, "bluetooth": False, "volume": 0.46, "muted": False},
                                  {"id": "headphones", "name": tr('无线耳机'), "active": False, "bluetooth": True, "cardId": "headphones-card", "volume": 0.5, "muted": False}],
                      "inputs": [{"id": "usb-microphone", "name": tr("USB microphone"), "active": True, "bluetooth": False, "volume": 0.65, "muted": False},
                                 {"id": "headphones-microphone", "name": tr("Wireless headset microphone"), "active": False, "bluetooth": True, "cardId": "headphones-card", "volume": 0.5, "muted": False}],
                      "cards": [{"id": "headphones-card", "name": tr('无线耳机'), "deviceId": "headphones", "profiles": [
                          {"id": "a2dp-sink", "name": "A2DP SBC", "active": False, "microphone": False, "available": True},
                          {"id": "headset-head-unit", "name": "HFP mSBC", "active": True, "microphone": True, "available": True},
                      ]}]},
            "brightness": {"available": True, "value": 0.72},
            "battery": {"available": True, "capacity": 83, "charging": False, "status": "Discharging",
                        "voltage": 3.9, "current": 0.8, "power": 3.12},
        })
        self._mock_audio = deepcopy(self.state["audio"])

    def start(self):
        QTimer.singleShot(0, lambda: self.updated.emit(deepcopy(self.state)))

    def request(self, action, payload=None):
        self.actions.append(action)
        payload = payload or {}
        if action == "volume":
            for output in self.state["audio"]["outputs"]:
                if output["id"] == payload.get("id") or ("id" not in payload and output["active"]):
                    output["volume"] = max(0, min(1, payload["value"]))
        elif action == "mute":
            for output in self.state["audio"]["outputs"]:
                if output["active"]:
                    output["muted"] = not output.get("muted", False)
        elif action == "brightness":
            self.state["brightness"]["value"] = max(0.05, min(1, payload["value"]))
        elif action == "wifi_power":
            self.state["wifi"]["enabled"] = payload["enabled"]
            if not payload["enabled"]:
                for device in self.state["wifi"]["devices"]:
                    device["connected"], device["deviceState"] = "", 30
                    device["strength"] = None
                    device["activeProfile"] = ""
                    for network in device["networks"]:
                        network["connected"] = False
        elif action in ("wifi_scan", "wifi_connect", "wifi_connect_saved", "wifi_disconnect"):
            device = next((entry for entry in self.state["wifi"]["devices"] if entry["id"] == payload.get("deviceId")), None)
            if device is None:
                self.operationFailed.emit(action, tr('目标无线网卡已移除'))
                return
            if action == "wifi_disconnect":
                device["connected"], device["deviceState"] = "", 30
                device["strength"] = None
                device["activeProfile"] = ""
                for network in device["networks"]:
                    network["connected"] = False
            elif action in ("wifi_connect", "wifi_connect_saved"):
                profile = next((entry for entry in device["saved"] if entry["id"] == payload["id"]), None) if action == "wifi_connect_saved" else None
                if profile and profile.get("blocked"):
                    self.operationFailed.emit(action, profile["blocked"])
                    return
                target = profile["name"] if profile else next((entry["name"] for entry in device["networks"] if entry["id"] == payload["id"]), "")
                if target:
                    for network in device["networks"]:
                        network["connected"] = network["name"] == target
                    device["connected"], device["deviceState"] = target, 100
                    device["strength"] = next((network["strength"] for network in device["networks"] if network["connected"]), None)
                    if profile is None:
                        profile = next((entry for entry in device["saved"] if entry["name"] == target and not entry.get("blocked")), None)
                    if profile is None:
                        profile = {"id": "mock:" + device["id"] + ":" + target, "name": target,
                                   "ssid": list(target.encode()), "keyManagement": "wpa-psk", "multiConnect": 0}
                        device["saved"].append(profile)
                    device["activeProfile"] = profile["id"]
        elif action == "bluetooth_power":
            self.state["bluetooth"]["powered"] = payload["enabled"]
            if not payload["enabled"]:
                for device in self.state["bluetooth"]["devices"]:
                    device["connected"] = False
        elif action in ("bluetooth_connect", "bluetooth_disconnect", "bluetooth_pair"):
            for device in self.state["bluetooth"]["devices"]:
                if device["id"] == payload["id"]:
                    device["connected"] = action != "bluetooth_disconnect"
                    device["paired"] = True
        elif action == "bluetooth_remove":
            self.state["bluetooth"]["devices"] = [device for device in self.state["bluetooth"]["devices"] if device["id"] != payload["id"]]
        elif action == "audio_output":
            for output in self.state["audio"]["outputs"]:
                output["active"] = output["id"] == payload["id"]
        elif action in ("audio_input", "audio_input_volume", "audio_input_mute"):
            target = next((source for source in self.state["audio"]["inputs"] if source["id"] == payload["id"]), None)
            if target is None:
                self.operationFailed.emit(action, tr('音频设备已移除'))
                return
            if action == "audio_input":
                for source in self.state["audio"]["inputs"]:
                    source["active"] = source is target
            elif action == "audio_input_volume":
                target["volume"] = max(0, min(1, payload["value"]))
            else:
                target["muted"] = not target.get("muted", False)
        elif action == "audio_profile":
            card = next((card for card in self.state["audio"]["cards"] if card["id"] == payload["id"]), None)
            profile = next((profile for profile in card["profiles"] if profile["id"] == payload["profile"] and profile["available"]), None) if card else None
            if profile is None:
                self.operationFailed.emit(action, tr("Bluetooth audio mode is unavailable"))
                return
            for entry in card["profiles"]:
                entry["active"] = entry is profile
            if not profile["microphone"]:
                self.state["audio"]["inputs"] = [source for source in self.state["audio"]["inputs"] if source.get("cardId") != card["id"]]
            elif not any(source.get("cardId") == card["id"] for source in self.state["audio"]["inputs"]):
                self.state["audio"]["inputs"] += [deepcopy(source) for source in self._mock_audio["inputs"] if source.get("cardId") == card["id"]]
        if action in ("bluetooth_power", "bluetooth_disconnect", "bluetooth_remove"):
            removed = {card["id"] for card in self.state["audio"]["cards"]
                       if (action == "bluetooth_power" and not payload["enabled"]) or card.get("deviceId") == payload.get("id")}
            self.state["audio"]["cards"] = [card for card in self.state["audio"]["cards"] if card["id"] not in removed]
            for kind in ("inputs", "outputs"):
                self.state["audio"][kind] = [entry for entry in self.state["audio"][kind] if entry.get("cardId") not in removed]
        elif action in ("bluetooth_connect", "bluetooth_pair"):
            for card in self._mock_audio["cards"]:
                if card.get("deviceId") == payload["id"] and not any(entry["id"] == card["id"] for entry in self.state["audio"]["cards"]):
                    self.state["audio"]["cards"].append(deepcopy(card))
                    for kind in ("inputs", "outputs"):
                        self.state["audio"][kind] += [deepcopy(entry) for entry in self._mock_audio[kind] if entry.get("cardId") == card["id"]]
        for kind in ("inputs", "outputs"):
            entries = self.state["audio"].get(kind, [])
            if entries and not any(entry["active"] for entry in entries):
                entries[0]["active"] = True
        active = next((output for output in self.state["audio"]["outputs"] if output["active"]), {})
        self.state["audio"].update(volume=active.get("volume") or 0, muted=active.get("muted", False))
        if action.startswith("wifi_"):
            devices = self.state["wifi"]["devices"]
            for device in devices:
                for profile in device["saved"]:
                    busy = profile.get("multiConnect", 0) not in (2, 3) and any(other["id"] != device["id"] and other.get("activeProfile") == profile["id"] for other in devices)
                    profile["blocked"] = tr('另一张网卡正在使用 · 可从网络列表另建连接') if busy else ""
        self.updated.emit(deepcopy(self.state))
        self.completed.emit(action)

    def reply(self, token, value):
        pass

    def close(self):
        pass
