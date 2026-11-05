from copy import deepcopy

from PySide6.QtCore import QObject, QTimer, Signal

MOCK_APPS = [
    ("terminal", "终端", "Terminal", "utilities-terminal", "System"),
    ("code", "代码编辑器", "Visual Studio Code", "visual-studio-code", "Development"),
    ("firefox", "浏览器", "Firefox", "firefox", "Network"),
    ("files", "文件管理", "个人文件与存储", "system-file-manager", "Utility"),
    ("retroarch", "RetroArch", "模拟器与游戏", "com.libretro.RetroArch", "Game"),
    ("notes", "文本编辑器", "Mousepad", "accessories-text-editor", "Utility"),
    ("monitor", "系统监视器", "运行状态", "utilities-system-monitor", "System"),
    ("calculator", "计算器", "日常计算", "accessories-calculator", "Utility"),
    ("viewer", "图片查看器", "图片与照片", "image-x-generic", "Graphics"),
    ("geany", "Geany", "轻量开发环境", "geany", "Development"),
]


def mock_apps():
    return [{"id": identifier + ".desktop", "name": name, "subtitle": subtitle,
             "icon": icon, "category": category}
            for identifier, name, subtitle, icon, category in MOCK_APPS]


def initial_state():
    return {
        "wifi": {"available": False, "enabled": False, "connected": "", "networks": []},
        "bluetooth": {"available": False, "powered": False, "discovering": False, "devices": []},
        "audio": {"available": False, "volume": 0, "muted": False, "outputs": []},
        "brightness": {"available": False, "value": 0},
        "battery": {"available": False, "capacity": 0, "charging": False},
    }


class MockBackend(QObject):
    updated = Signal(dict)
    failed = Signal(str)
    operationFailed = Signal(str, str)
    prompt = Signal(dict)
    completed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.actions = []
        self.state = initial_state()
        self.state.update({
            "wifi": {"available": True, "enabled": True, "connected": "Workshop",
                     "networks": [
                         {"id": "workshop", "name": "Workshop", "strength": 92, "secured": True, "connected": True, "security": "WPA2"},
                         {"id": "studio", "name": "Studio 5G", "strength": 76, "secured": True, "connected": False, "security": "WPA3"},
                         {"id": "guest", "name": "Guest", "strength": 54, "secured": False, "connected": False, "security": "开放网络"},
                     ]},
            "bluetooth": {"available": True, "powered": True, "discovering": False,
                          "devices": [{"id": "headphones", "name": "无线耳机", "paired": True, "connected": True, "trusted": True},
                                      {"id": "keyboard", "name": "蓝牙键盘", "paired": True, "connected": False, "trusted": True}]},
            "audio": {"available": True, "volume": 0.46, "muted": False,
                      "outputs": [{"id": "speaker", "name": "内置扬声器", "active": True},
                                  {"id": "headphones", "name": "无线耳机", "active": False}]},
            "brightness": {"available": True, "value": 0.72},
            "battery": {"available": True, "capacity": 83, "charging": False},
        })

    def start(self):
        QTimer.singleShot(0, lambda: self.updated.emit(deepcopy(self.state)))

    def request(self, action, payload=None):
        self.actions.append(action)
        payload = payload or {}
        if action == "volume":
            self.state["audio"]["volume"] = max(0, min(1, payload["value"]))
        elif action == "mute":
            self.state["audio"]["muted"] = not self.state["audio"]["muted"]
        elif action == "brightness":
            self.state["brightness"]["value"] = max(0.05, min(1, payload["value"]))
        elif action == "wifi_power":
            self.state["wifi"]["enabled"] = payload["enabled"]
        elif action == "wifi_connect":
            for network in self.state["wifi"]["networks"]:
                network["connected"] = network["id"] == payload["id"]
                if network["connected"]:
                    self.state["wifi"]["connected"] = network["name"]
        elif action == "bluetooth_power":
            self.state["bluetooth"]["powered"] = payload["enabled"]
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
        self.updated.emit(deepcopy(self.state))
        self.completed.emit(action)

    def reply(self, token, value):
        pass

    def close(self):
        pass
