import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from .core import PAGE_NAMES, PAGES, ConfigStore, Navigation, move_index
from .desktop import DesktopCatalog, open_terminal
from .files import FileOperations
from .mock import mock_apps
from .wifi import wifi_label, wifi_status, wifi_summary

CATEGORY_NAMES = {"All": "全部应用", "Development": "开发", "Network": "网络", "System": "系统",
                  "Utility": "工具", "Game": "游戏", "Graphics": "图形", "Office": "办公", "AudioVideo": "影音", "Other": "其他"}


class ShellController(QObject):
    changed = Signal()
    present = Signal()
    calibrationRequested = Signal()
    calibrationDirection = Signal(str)
    foregroundChanged = Signal(bool)
    applicationAction = Signal(str)
    inputSuspended = Signal(bool)
    taskFinished = Signal(object)

    def __init__(self, backend, window_service=None, config=None, catalog=None, mock=False):
        super().__init__()
        self.backend = backend
        self.window_service = window_service
        self.config = config or ConfigStore()
        self.mock = mock
        self.navigation = Navigation(self.config.data["focus"])
        self.catalog = catalog or DesktopCatalog()
        self.applications = mock_apps() if mock else self.catalog.entries()
        self.data = dict(backend.state)
        self.data.update({"windows": [], "files": [], "directory": str(Path.home()),
                          "input": {"available": False, "verified": False}})
        self.query = ""
        saved_category = self.config.data["preferences"]["category"]
        self.category = saved_category if saved_category in CATEGORY_NAMES else "All"
        self._modals = []
        self._text = ""
        self.toast = ""
        self.busy = False
        self.busy_label = ""
        self.clipboard = None
        self.show_hidden = self.config.data["preferences"]["showHidden"]
        self.directory_positions = {}
        self.operations = FileOperations()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="udeck-files")
        self.cancelled = threading.Event()
        self.taskFinished.connect(self._finish_task)
        self.backend.updated.connect(self._update)
        self.backend.failed.connect(self._failure)
        self.backend.operationFailed.connect(self._operation_failed)
        self.backend.prompt.connect(self._agent_prompt)
        self.backend.completed.connect(self._system_completed)
        self.pending_system = set()
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self._clear_toast)
        if window_service:
            window_service.changed.connect(self._windows_changed)
            window_service.failed.connect(self._failure)
        if mock:
            self.data["directory"] = "/home/demo"
            self.data["files"] = [{"id": "/home/demo/" + name, "path": "/home/demo/" + name,
                                   "name": name, "directory": directory, "icon": "folder" if directory else "text-x-generic", "subtitle": subtitle}
                                  for name, directory, subtitle in [("Documents", True, "文件夹"), ("Downloads", True, "文件夹"), ("Projects", True, "文件夹"), ("Pictures", True, "文件夹"), ("掌机使用笔记.md", False, "2.4 KiB"), ("README.txt", False, "1.2 KiB")]]
            self.data["windows"] = [{"id": "terminal", "name": "zhubby@uconsole: ~", "appId": "terminal", "subtitle": "终端", "icon": "utilities-terminal", "active": False}, {"id": "editor", "name": "uDeck — 代码编辑器", "appId": "code", "subtitle": "Visual Studio Code", "icon": "visual-studio-code", "active": False}]
        else:
            self._browse(Path.home())

    @property
    def modal(self):
        return self._modals[-1] if self._modals else {}

    def _items(self):
        page = self.navigation.page
        if page == "home":
            identifiers = list(dict.fromkeys(self.config.data["favorites"] + self.config.data["recent"]))
            available = {application["id"]: application for application in self.applications}
            entries = [available[identifier] for identifier in identifiers if identifier in available]
            return entries or self.applications[:10]
        if page == "apps":
            return [application for application in self.applications if (self.category == "All" or application["category"] == self.category) and (not self.query or self.query.casefold() in (application["name"] + " " + application.get("subtitle", "")).casefold())]
        if page == "windows":
            return self.data["windows"]
        if page == "files":
            return self.data["files"]
        return self._settings()

    def _settings(self):
        audio, brightness = self.data["audio"], self.data["brightness"]
        wifi, bluetooth, battery = self.data["wifi"], self.data["bluetooth"], self.data["battery"]
        return [
            {"id": "volume", "name": "音量", "subtitle": "静音" if audio.get("muted") else f"{round(audio.get('volume', 0) * 100)}%", "icon": "audio-volume-high", "value": audio.get("volume", 0), "disabled": not audio.get("available")},
            {"id": "brightness", "name": "屏幕亮度", "subtitle": f"{round(brightness.get('value', 0) * 100)}%", "icon": "display-brightness", "value": brightness.get("value", 0), "disabled": not brightness.get("available")},
            {"id": "output", "name": "音频输出", "subtitle": next((output["name"] for output in audio.get("outputs", []) if output.get("active")), "未检测到音频输出"), "icon": "audio-card", "disabled": not audio.get("available")},
            {"id": "wifi", "name": "Wi-Fi", "subtitle": wifi_summary(wifi), "icon": "network-wireless", "disabled": not wifi.get("available")},
            {"id": "bluetooth", "name": "蓝牙", "subtitle": "已开启" if bluetooth.get("powered") else "已关闭", "icon": "bluetooth", "disabled": not bluetooth.get("available")},
            {"id": "battery", "name": "电池", "subtitle": f"{battery.get('capacity', 0)}% · {'正在充电' if battery.get('charging') else '电池供电'}" if battery.get("available") else "未检测到电池", "icon": "battery"},
            {"id": "input", "name": "按键与控制器", "subtitle": "ABXY 已校准" if self.data["input"].get("verified") else ("ABXY 固件映射 · 可重新校准" if self.data["input"].get("mapped") else "校准物理 ABXY；不占用普通键盘字母"), "icon": "input-gaming"},
            {"id": "lock", "name": "锁定屏幕", "subtitle": "使用登录密码解锁", "icon": "system-lock-screen"},
            {"id": "blank", "name": "熄灭屏幕", "subtitle": "按方向键或键盘恢复；不是系统休眠", "icon": "video-display"},
            {"id": "logout", "name": "注销会话", "subtitle": "返回登录界面；请先保存工作", "icon": "system-log-out"},
            {"id": "reboot", "name": "重新启动", "subtitle": "需要二次确认", "icon": "system-reboot"},
            {"id": "poweroff", "name": "关闭设备", "subtitle": "需要二次确认", "icon": "system-shutdown"},
        ]

    @Property(str, notify=changed)
    def snapshotJson(self):
        items = self._items()
        selected = max(0, min(self.navigation.index, len(items) - 1))
        titles = {"home": "从这里开始", "apps": CATEGORY_NAMES[self.category], "windows": "正在运行", "files": Path(self.data["directory"]).name or "/", "settings": "设备设置"}
        descriptions = {"home": "收藏与最近使用" if self.config.data["favorites"] or self.config.data["recent"] else "选择应用，开始使用你的掌机", "apps": f"{len(items)} 个应用" + (f" · 搜索：{self.query}" if self.query else " · X 筛选与操作"), "windows": "选择一个窗口，继续工作", "files": self.data["directory"], "settings": "常用控制，直接完成"}
        return json.dumps({
            **self.data, "mock": self.mock, "page": self.navigation.page,
            "pageNames": list(PAGE_NAMES), "pages": list(PAGES),
            "title": titles[self.navigation.page], "description": descriptions[self.navigation.page],
            "index": selected, "zone": self.navigation.zone, "items": items,
            "modal": self.modal, "toast": self.toast, "busy": self.busy,
            "busyLabel": self.busy_label, "favorites": self.config.data["favorites"],
            "clipboard": bool(self.clipboard), "pending": list(self.pending_system), "wifiSummary": wifi_summary(self.data["wifi"]),
        }, ensure_ascii=False)

    def _publish(self):
        items = self._items()
        self.navigation.index = max(0, min(self.navigation.index, len(items) - 1))
        self.changed.emit()

    @Slot(dict)
    def _update(self, values):
        self.data.update(values)
        self._refresh_open_menu()
        self._publish()

    def _refresh_open_menu(self):
        devices = {device["id"]: device for device in self.data["wifi"].get("devices", [])}
        removed = False
        for index in range(len(self._modals) - 1, -1, -1):
            device_id = self._modals[index].get("deviceId")
            if device_id and device_id not in devices:
                self._remove_modal(index, reject=True)
                removed = True
        for modal in self._modals:
            if modal.get("kind") != "menu":
                continue
            source = modal.get("source")
            if source == "wifi":
                options = self._wifi_options()
                modal["body"] = wifi_summary(self.data["wifi"])
            elif source in ("wifi-device", "wifi-saved"):
                device = devices[modal["deviceId"]]
                options = self._wifi_device_options(device) if source == "wifi-device" else self._wifi_saved_options(device)
                modal["body"] = wifi_status(device, self.data["wifi"].get("enabled")) if source == "wifi-device" else wifi_label(device)
            elif source == "bluetooth":
                options = self._bluetooth_options()
            else:
                continue
            old_options = modal["options"]
            previous = old_options[min(modal["index"], len(old_options) - 1)] if old_options else {}
            modal["options"] = options
            modal["index"] = next((index for index, option in enumerate(options) if option.get("id") == previous.get("id")), min(modal["index"], max(0, len(options) - 1)))
        if removed:
            self.notify("无线网卡已移除或暂不可用，请重新选择")

    @Slot(list)
    def _windows_changed(self, windows):
        self.data["windows"] = windows
        self._publish()

    @Slot(str)
    def _failure(self, message):
        self.notify(message)

    @Slot(str, str)
    def _operation_failed(self, action, message):
        self.pending_system.discard(action)
        if action == 'lock':
            self.inputSuspended.emit(False)
        self.notify(message)

    @Slot(str)
    def _system_completed(self, action):
        self.pending_system.discard(action)
        if action == 'lock':
            self.inputSuspended.emit(False)
        if action not in ("refresh", "bluetooth_stop"):
            self.notify("预览操作已模拟，未操作真实设备" if self.mock else "请求已处理；连接结果以设备状态为准")
        self._publish()

    def notify(self, message):
        self.toast = str(message)
        self.toast_timer.start(6000)
        self._publish()

    def _clear_toast(self):
        self.toast = ""
        self._publish()

    @Slot(str)
    def setPage(self, page):
        if page not in PAGES:
            return
        self.navigation.set_page(page)
        self.navigation.zone = "content"
        self._publish()

    @Slot(int)
    def select(self, index):
        self.navigation.select(index)
        self._publish()

    @Slot(bool)
    def windowActive(self, active):
        self.foregroundChanged.emit(active)
        if not active and self.data["bluetooth"].get("discovering"):
            self.backend.request("bluetooth_stop")

    @Slot(str)
    def dispatch(self, action):
        if self.modal.get("kind") == "calibration" and action in ("up", "down", "left", "right"):
            self.calibrationDirection.emit(action)
            return
        if action in ("previous-page", "next-page"):
            if not self.modal:
                index = PAGES.index(self.navigation.page)
                offset = -1 if action == "previous-page" else 1
                self.setPage(PAGES[max(0, min(index + offset, len(PAGES) - 1))])
            return
        if action == "home":
            self._cancel_modals()
            self.setPage("home")
            self.present.emit()
            return
        if action == "switcher":
            self._cancel_modals()
            self.setPage("windows")
            self.present.emit()
            return
        if action == "quick-settings":
            if self.modal.get("source") == "quick-settings":
                return
            self._menu("快捷设置", [{"label": entry["name"], "subtitle": entry["subtitle"], "action": "setting", "id": entry["id"], "disabled": entry.get("disabled", False)} for entry in self._settings()[:7]] + [{"label": "电源与会话", "action": "power-menu"}, {"label": "运行中应用", "action": "switcher"}], source="quick-settings")
            self.present.emit()
            return
        if self.modal:
            self._dispatch_modal(action)
            return
        items = self._items()
        if action in ("left", "right", "up", "down"):
            self.navigation.move(action, len(items), 5 if self.navigation.page in ("home", "apps") else 1)
        elif action == "accept":
            if self.navigation.zone == "tabs":
                self.navigation.zone = "content"
            elif items:
                self._activate(items[min(self.navigation.index, len(items) - 1)])
        elif action == "back":
            if self.navigation.page == "files" and Path(self.data["directory"]) not in (Path.home(), Path("/")):
                self._browse(Path(self.data["directory"]).parent)
            else:
                self.setPage("home")
        elif action == "context":
            self._context(items[min(self.navigation.index, len(items) - 1)] if items else None)
        elif action == "search":
            self._text_prompt("搜索应用", "输入应用名称，按 A 或 Enter 搜索", "search", self.query)
        self._publish()

    def _activate(self, item):
        if item.get("disabled"):
            component = self.data.get(item["id"], {})
            self.notify(component.get("error", "此功能当前不可用"))
        elif self.navigation.page in ("home", "apps"):
            self._launch(item)
        elif self.navigation.page == "windows":
            if not self.mock:
                try:
                    self.window_service.request(item["id"], "activate")
                except RuntimeError as error:
                    self.notify(error)
            else:
                self.notify("预览：切换到 " + item["name"])
        elif self.navigation.page == "files":
            if item["directory"]:
                self._browse(item["path"])
            elif self.mock:
                self.notify("预览：打开 " + item["name"])
            else:
                self._run("打开文件", lambda: self.operations.open(item["path"]))
        elif self.navigation.page == "settings":
            self.activateSetting(item["id"])

    def _launch(self, item):
        if self.mock:
            self.config.remember(item["id"])
            self.notify("预览：启动 " + item["name"])
        else:
            self._run("启动 " + item["name"], lambda: self.catalog.launch(item["id"]), lambda result: self.config.remember(item["id"]))

    def _context(self, item):
        page = self.navigation.page
        if page in ("home", "apps"):
            options = []
            if item:
                options.extend([{"label": "打开应用", "action": "launch", "item": item}, {"label": "取消收藏" if item["id"] in self.config.data["favorites"] else "加入收藏", "action": "favorite", "id": item["id"]}])
            options.extend([{"label": "搜索应用", "action": "search"}, {"label": "应用分类", "action": "categories"}, {"label": "清除搜索与筛选", "action": "clear-search"}])
            self._menu(item["name"] if item else "应用操作", options)
        elif page == "files":
            options = []
            if item:
                options = [{"label": "打开", "action": "open-file", "item": item},
                           {"label": "重命名", "action": "rename", "item": item},
                           {"label": "复制", "action": "copy", "item": item},
                           {"label": "剪切", "action": "cut", "item": item},
                           {"label": "移入回收站", "action": "trash", "item": item}]
            options.append({"label": "新建文件夹", "action": "mkdir"})
            options.append({"label": "在此打开终端", "action": "open-terminal", "directory": item["path"] if item and item.get("directory") else self.data["directory"]})
            if self.clipboard:
                options.append({"label": "粘贴到当前目录", "action": "paste"})
            options.extend([{"label": "隐藏点文件" if self.show_hidden else "显示点文件", "action": "hidden"}, {"label": "上级目录", "action": "parent"}, {"label": "刷新", "action": "refresh-files"}])
            self._menu("文件操作", options)
        elif page == "windows" and item:
            self._menu(item["name"], [{"label": "切换到窗口", "action": "activate-window", "item": item}, {"label": "请求关闭窗口", "action": "close-window", "item": item}])
        else:
            self._menu("设备操作", [{"label": "刷新设备状态", "action": "system", "systemAction": "refresh"}, {"label": "校准 ABXY", "action": "setting", "id": "input"}])

    @Slot(str)
    def activateSetting(self, identifier):
        if identifier == "volume":
            self._menu("音量", [{"label": "调整音量", "action": "setting", "id": "volume-level"}, {"label": "取消静音" if self.data["audio"].get("muted") else "静音", "action": "system", "systemAction": "mute"}])
        elif identifier in ("volume-level", "brightness"):
            component = "audio" if identifier == "volume-level" else "brightness"
            if not self.data[component].get("available"):
                self.notify(self.data[component].get("error", "设备不可用"))
                return
            value = self.data[component].get("volume" if identifier == "volume-level" else "value", 0)
            self._push({"kind": "slider", "title": "音量" if identifier == "volume-level" else "屏幕亮度", "action": "volume" if identifier == "volume-level" else identifier, "value": value, "body": "左右调节 · A 应用 · B 取消"})
        elif identifier == "output":
            self._menu("音频输出", [{"label": output["name"], "subtitle": "当前输出" if output["active"] else "", "action": "system", "systemAction": "audio_output", "payload": {"id": output["id"]}} for output in self.data["audio"].get("outputs", [])])
        elif identifier == "wifi":
            self._menu("Wi-Fi 网卡", self._wifi_options(), source="wifi", body=wifi_summary(self.data["wifi"]),
                       index=1 if self.data["wifi"].get("devices") else 0)
        elif identifier == "bluetooth":
            self._menu("蓝牙", self._bluetooth_options(), source="bluetooth")
        elif identifier in ("poweroff", "reboot", "logout"):
            title = {"poweroff": "关闭设备？", "reboot": "重新启动？", "logout": "注销当前会话？"}[identifier]
            self._confirm(title, "这会关闭当前工作会话并可能中断 SSH。请确认工作已保存。", {"action": "system", "systemAction": identifier})
        elif identifier in ("lock", "blank"):
            self._system(identifier)
        elif identifier == "battery":
            self._push({"kind": "information", "title": "电池与电源", "body": self._settings()[5]["subtitle"] + "\n熄屏仅关闭显示，不等于系统休眠。"})
        elif identifier == "input":
            if self.mock:
                self._push({"kind": "information", "title": "物理按键校准", "body": "请在 uConsole 实机上逐个按下 A、B、X、Y。预览不会将键盘字母当作手柄。"})
            elif self.data["input"].get("available"):
                self.calibrationRequested.emit()
            else:
                self._push({"kind": "information", "title": "未检测到独立手柄", "body": self.data["input"].get("message", "请检查手柄模式。若 ABXY 上报 j/k/u/i 字母，请切换设备原有手柄模式；不需要刷写固件。")})
        self._publish()

    def _wifi_options(self):
        information = self.data["wifi"]
        if not information.get("available"):
            return [{"id": "unavailable", "label": information.get("error") or "未检测到无线网卡", "action": "none", "disabled": True}]
        options = [{"id": "power", "label": "关闭全部 Wi-Fi" if information["enabled"] else "开启全部 Wi-Fi",
                    "subtitle": "影响所有无线网卡", "action": "wifi-power"}]
        options += [{"id": device["id"], "deviceId": device["id"], "label": wifi_label(device),
                     "subtitle": wifi_status(device, information["enabled"]), "action": "wifi-device", "icon": "network-wireless"}
                    for device in information.get("devices", [])]
        return options

    def _wifi_device(self, device_id):
        device = next((device for device in self.data["wifi"].get("devices", []) if device["id"] == device_id), None)
        if device is None:
            raise RuntimeError("目标无线网卡已移除，请重新选择")
        return device

    def _wifi_usable(self, device):
        return self.data["wifi"].get("enabled") and device.get("available") and device.get("managed", True) and device.get("deviceState") not in (10, 20)

    def _wifi_device_options(self, device):
        usable = self._wifi_usable(device)
        device_id = device["id"]
        options = [
            {"id": "scan", "label": "搜索网络", "action": "system", "systemAction": "wifi_scan", "payload": {"deviceId": device_id}, "disabled": not usable},
            {"id": "saved", "label": "已保存的网络", "subtitle": f"{len(device.get('saved', []))} 个兼容配置", "action": "wifi-saved", "deviceId": device_id, "disabled": not usable},
        ]
        if device.get("connected") or 40 <= device.get("deviceState", 0) <= 100:
            options.append({"id": "disconnect", "label": "断开此网卡", "action": "wifi-disconnect", "deviceId": device_id, "disabled": not usable})
        if device.get("error"):
            options.append({"id": "failure", "label": device["error"], "action": "none", "disabled": True})
        for network in device.get("networks", []):
            ssid = bytes(network.get("ssid", network["name"].encode()))
            status = "已连接 · " if network.get("connected") else "正在连接 · " if network.get("connecting") else "已保存 · " if network.get("saved") else ""
            options.append({"id": "network:" + ssid.hex() + ":" + network["security"], "label": network["name"],
                            "subtitle": status + f"{network['strength']}% · {network['security']}",
                            "action": "wifi-connect", "deviceId": device_id, "network": network,
                            "disabled": not usable or network.get("unsupported", False)})
        if not device.get("networks"):
            options.append({"id": "empty", "label": "尚未发现网络" if usable else wifi_status(device, self.data["wifi"].get("enabled")), "action": "none", "disabled": True})
        return options

    def _wifi_saved_options(self, device):
        return [{"id": profile["id"], "label": profile["name"], "subtitle": profile.get("blocked") or ("暂不支持此认证方式" if profile.get("unsupported") else "已保存"),
                 "action": "wifi-saved-connect", "deviceId": device["id"], "profile": profile,
                 "reason": profile.get("blocked"), "disabled": not self._wifi_usable(device) or profile.get("unsupported", False) or bool(profile.get("blocked"))}
                for profile in device.get("saved", [])] or [{"id": "empty", "label": "没有兼容的已保存网络", "action": "none", "disabled": True}]

    def _bluetooth_options(self):
        information = self.data["bluetooth"]
        if not information.get("available"):
            return [{"label": information.get("error", "蓝牙适配器不可用"), "action": "none", "disabled": True}]
        options = [{"id": "power", "label": "关闭蓝牙" if information["powered"] else "开启蓝牙", "action": "system", "systemAction": "bluetooth_power", "payload": {"enabled": not information["powered"]}}, {"id": "scan", "label": "停止发现" if information.get("discovering") else "发现附近设备（30 秒）", "action": "system", "systemAction": "bluetooth_stop" if information.get("discovering") else "bluetooth_scan", "disabled": not information["powered"]}]
        options += [{"id": device["id"], "label": device["name"], "subtitle": "已连接" if device["connected"] else "已配对 · 未连接" if device["paired"] else "未配对", "action": "device", "device": device} for device in information.get("devices", [])]
        return options

    def _push(self, modal):
        self.navigation.open_modal()
        self._modals.append({"key": uuid.uuid4().hex, "index": 0, **modal})
        self._text = modal.get("text", "")
        self._publish()

    def _pop(self, reject=False):
        if self.modal:
            self._remove_modal(len(self._modals) - 1, reject=reject)
        self._publish()

    def _remove_modal(self, index, reject=False):
        modal = self._modals.pop(index)
        if index < len(self.navigation.modal_owners):
            owner = self.navigation.modal_owners.pop(index)
            if index == len(self._modals):
                self.navigation.page, self.navigation.zone, self.navigation.index = owner
        if reject and modal.get("token"):
            self.backend.reply(modal["token"], None)
        self._text = self.modal.get("text", "")

    def _cancel_modals(self):
        self.cancelled.set()
        while self._modals:
            self._pop(reject=True)

    def _menu(self, title, options, **values):
        self._push({"kind": "menu", "title": title, "options": options, **values})

    def _confirm(self, title, body, option, **values):
        self._push({"kind": "confirm", "title": title, "body": body, "option": option, **values})

    def _text_prompt(self, title, body, purpose, text="", **values):
        self._push({"kind": "text", "title": title, "body": body, "purpose": purpose, "text": text, **values})

    def _dispatch_modal(self, action):
        modal = self.modal
        kind = modal["kind"]
        if action == "back":
            if kind == "progress":
                self.cancelled.set()
            self._pop(reject=True)
            if modal.get('source') == 'application' and not self.modal:
                self.applicationAction.emit('return')
            return
        if kind == "menu":
            options = modal["options"]
            if action in ("up", "down") and options:
                modal["index"] = move_index(modal["index"], action, len(options))
            elif action == "accept" and options:
                option = options[min(modal["index"], len(options) - 1)]
                if option.get("disabled"):
                    self.notify(option.get("reason") or "此项目当前不可用")
                    return
                if modal.get("source") not in ("wifi", "wifi-device", "wifi-saved"):
                    self._pop()
                self._execute_option(option)
        elif kind == "confirm":
            if action in ("left", "up"):
                modal["index"] = 0
            elif action in ("right", "down"):
                modal["index"] = 1
            elif action == "accept":
                accepted = modal["index"] == 1
                self._pop()
                if modal.get("token"):
                    self.backend.reply(modal["token"], accepted)
                elif accepted:
                    self._execute_option(modal["option"])
        elif kind == "text" and action == "accept":
            text = self._text
            self._pop()
            self._submit_text(modal, text)
        elif kind == "slider":
            if action in ("left", "right"):
                minimum = 0.05 if modal["action"] == "brightness" else 0
                modal["value"] = max(minimum, min(1, modal["value"] + (0.05 if action == "right" else -0.05)))
            elif action == "accept":
                self._pop()
                self._system(modal["action"], {"value": modal["value"]})
        elif kind == "information" and action == "accept":
            self._pop()
        self._publish()

    @Slot(str)
    def editText(self, value):
        self._text = value
        if self.modal.get("kind") == "text":
            self.modal["text"] = value

    @Slot(int)
    def chooseModal(self, index):
        if not self.modal:
            return
        self.modal["index"] = index
        self._dispatch_modal("accept")

    def _execute_option(self, option):
        try:
            self._apply_option(option)
        except (OSError, ValueError, KeyError, RuntimeError) as error:
            self.notify(f"操作失败：{error}")

    def _apply_option(self, option):
        action = option["action"]
        item = option.get("item", {})
        if action == "application-control":
            self.applicationAction.emit(option['command'])
        elif action == "setting":
            self.activateSetting(option["id"])
        elif action == "power-menu":
            self._menu("电源与会话", [{"label": entry["name"], "subtitle": entry["subtitle"], "action": "setting", "id": entry["id"]} for entry in self._settings() if entry["id"] in ("lock", "blank", "logout", "reboot", "poweroff")])
        elif action == "system":
            self._system(option["systemAction"], option.get("payload", {}))
        elif action == "launch":
            self._launch(item)
        elif action == "favorite":
            self.config.favorite(option["id"], option["id"] not in self.config.data["favorites"])
        elif action == "search":
            self.dispatch("search")
        elif action == "categories":
            categories = {application["category"] for application in self.applications}
            self._menu("应用分类", [{"label": label, "action": "category", "id": identifier} for identifier, label in CATEGORY_NAMES.items() if identifier == "All" or identifier in categories])
        elif action == "category":
            self.category = option["id"]
            self.config.data["preferences"]["category"] = self.category
            self.config.save()
            self.navigation.select(0)
            self.setPage("apps")
        elif action == "clear-search":
            self.category, self.query = "All", ""
            self.config.data["preferences"]["category"] = "All"
            self.config.save()
            self.navigation.select(0)
        elif action == "open-file":
            self._activate(item)
        elif action == "open-terminal":
            if self.mock:
                self.notify("预览：在此打开终端")
            else:
                self._run("打开终端", lambda: open_terminal(option["directory"]))
        elif action in ("mkdir", "rename"):
            self._text_prompt("新建文件夹" if action == "mkdir" else "重命名", "输入名称，按 A 或 Enter 确认", action, "" if action == "mkdir" else item["name"], item=item, directory=self.data["directory"])
        elif action in ("copy", "cut"):
            self.clipboard = {"path": item["path"], "move": action == "cut"}
            self.notify("已剪切，选择目标目录后粘贴" if action == "cut" else "已复制，选择目标目录后粘贴")
        elif action in ("paste", "overwrite"):
            self._paste(replace=action == "overwrite")
        elif action == "hidden":
            self.show_hidden = not self.show_hidden
            self.config.data["preferences"]["showHidden"] = self.show_hidden
            self.config.save()
            self._browse(self.data["directory"])
        elif action in ("parent", "refresh-files"):
            self._browse(Path(self.data["directory"]).parent if action == "parent" else self.data["directory"])
        elif action == "trash":
            self._confirm("移入回收站？", item["name"] + "\n不会执行永久删除。", {"action": "trash-confirm", "item": item})
        elif action == "trash-confirm":
            if self.mock:
                self.data["files"] = [entry for entry in self.data["files"] if entry["id"] != item["id"]]
            else:
                self._run("移入回收站", lambda: self.operations.trash(item["path"]), lambda result: self._browse(self.data["directory"]))
        elif action == "wifi-power":
            enabled = not self.data["wifi"].get("enabled")
            if enabled:
                self._system("wifi_power", {"enabled": True})
            else:
                self._confirm("关闭全部 Wi-Fi？", "这会断开所有无线网卡的连接，并可能中断 SSH。",
                              {"action": "system", "systemAction": "wifi_power", "payload": {"enabled": False}})
        elif action == "wifi-device":
            device = self._wifi_device(option["deviceId"])
            self._menu(wifi_label(device), self._wifi_device_options(device), source="wifi-device", deviceId=device["id"],
                       body=wifi_status(device, self.data["wifi"].get("enabled")))
        elif action == "wifi-disconnect":
            device = self._wifi_device(option["deviceId"])
            self._confirm("断开此网卡？", wifi_label(device) + "\n只断开这张网卡，可能中断经由它的 SSH 连接。",
                          {"action": "system", "systemAction": "wifi_disconnect", "payload": {"deviceId": device["id"]}}, deviceId=device["id"])
        elif action == "wifi-connect":
            device = self._wifi_device(option["deviceId"])
            network = option["network"]
            if network.get("connected"):
                self.notify("此网络当前已连接")
            else:
                self._confirm("连接 " + network["name"] + "？", wifi_label(device) + "\n切换这张网卡的网络可能中断 SSH。",
                              {"action": "system", "systemAction": "wifi_connect", "payload": {"id": network["id"], "deviceId": device["id"]}}, deviceId=device["id"])
        elif action == "wifi-saved":
            device = self._wifi_device(option["deviceId"])
            self._menu("已保存的网络", self._wifi_saved_options(device), source="wifi-saved", deviceId=device["id"], body=wifi_label(device))
        elif action == "wifi-saved-connect":
            device = self._wifi_device(option["deviceId"])
            profile = option["profile"]
            self._confirm("连接 " + profile["name"] + "？", wifi_label(device) + "\n切换这张网卡的网络可能中断 SSH。",
                          {"action": "system", "systemAction": "wifi_connect_saved", "payload": {"id": profile["id"], "deviceId": device["id"]}}, deviceId=device["id"])
        elif action == "device":
            device = option["device"]
            options = []
            if not device["paired"]:
                options.append({"label": "配对并信任此设备", "action": "device-pair", "device": device})
            else:
                options.append({"label": "断开连接" if device["connected"] else "连接设备", "action": "system", "systemAction": "bluetooth_disconnect" if device["connected"] else "bluetooth_connect", "payload": {"id": device["id"]}})
                options.append({"label": "移除配对", "action": "device-remove", "device": device})
            self._menu(device["name"], options)
        elif action in ("device-pair", "device-remove"):
            device = option["device"]
            self._confirm("配对并信任？" if action == "device-pair" else "移除蓝牙设备？", device["name"], {"action": "system", "systemAction": "bluetooth_pair" if action == "device-pair" else "bluetooth_remove", "payload": {"id": device["id"]}})
        elif action == "activate-window":
            self._activate(item)
        elif action == "close-window":
            self._confirm("请求关闭窗口？", item["name"] + "\n应用可能要求保存工作；不会强制结束进程。", {"action": "window-close-confirm", "item": item})
        elif action == "window-close-confirm":
            if self.mock:
                self.data["windows"] = [entry for entry in self.data["windows"] if entry["id"] != item["id"]]
            else:
                try:
                    self.window_service.request(item["id"], "close")
                except RuntimeError as error:
                    self.notify(error)
        elif action == "switcher":
            self.dispatch("switcher")
        self._publish()

    def _submit_text(self, modal, text):
        if modal.get("token"):
            self.backend.reply(modal["token"], text)
        elif modal["purpose"] == "search":
            self.query = text.strip()
            self.navigation.select(0)
            self.setPage("apps")
        elif self.mock:
            if modal["purpose"] == "mkdir" and text.strip():
                identifier = self.data["directory"] + "/" + text
                self.data["files"].append({"id": identifier, "path": identifier, "name": text, "directory": True, "subtitle": "预览文件夹", "icon": "folder"})
            elif modal["purpose"] == "rename":
                for entry in self.data["files"]:
                    if entry["id"] == modal["item"]["id"]:
                        entry["name"] = text
            self._publish()
        elif modal["purpose"] == "mkdir":
            self._run("创建文件夹", lambda: self.operations.mkdir(modal["directory"], text), lambda result: self._browse(self.data["directory"]))
        elif modal["purpose"] == "rename":
            self._run("重命名", lambda: self.operations.rename(modal["item"]["path"], text), lambda result: self._browse(self.data["directory"]))

    def _browse(self, directory):
        if self.mock:
            self.data["directory"] = str(directory)
            self.navigation.select(0)
            self._publish()
            return
        directory = Path(directory).absolute()
        if self.navigation.page == "files":
            entries = self.data["files"]
            selected = entries[min(self.navigation.index, len(entries) - 1)]["id"] if entries else None
            self.directory_positions[self.data["directory"]] = {"id": selected, "index": self.navigation.index}

        def loaded(entries):
            self.data["directory"] = str(directory)
            self.data["files"] = entries
            if self.navigation.page == "files":
                saved = self.directory_positions.get(str(directory), {})
                position = next((index for index, entry in enumerate(entries) if entry["id"] == saved.get("id")), saved.get("index", 0))
                self.navigation.select(position)

        self._run("读取文件夹", lambda: self.operations.list_directory(directory, self.show_hidden), loaded)

    def _paste(self, replace=False):
        if not self.clipboard:
            return
        if self.busy:
            self.notify("请等待当前文件操作完成")
            return
        if self.mock:
            self.notify("预览：粘贴操作已模拟，未访问真实文件")
            return
        clipboard = dict(self.clipboard)
        directory = self.data["directory"]
        target = Path(directory) / Path(clipboard["path"]).name
        if not replace and os.path.lexists(target):
            self._confirm("覆盖同名文件？", target.name + "\n文件夹不会被合并或覆盖。", {"action": "overwrite"})
            return
        self.cancelled = threading.Event()
        cancellation = self.cancelled
        self._push({"kind": "progress", "title": "正在移动" if clipboard["move"] else "正在复制", "body": Path(clipboard["path"]).name + "\nB 取消；取消不会删除源文件"})
        modal_key = self.modal["key"]

        def finished(result):
            if self.modal.get("key") == modal_key:
                self._pop()
            if clipboard["move"]:
                self.clipboard = None
            self._browse(directory)

        self._run("移动文件" if clipboard["move"] else "复制文件", lambda: self.operations.transfer(clipboard["path"], directory, move=clipboard["move"], replace=replace, cancelled=cancellation), finished)

    def _run(self, label, work, success=None):
        if self.busy:
            self.notify("请等待当前文件操作完成")
            return
        self.busy, self.busy_label = True, label

        def complete(future):
            try:
                self.taskFinished.emit((future.result(), success, None))
            except Exception as error:
                self.taskFinished.emit((None, success, error))

        self.executor.submit(work).add_done_callback(complete)
        self._publish()

    @Slot(object)
    def _finish_task(self, result):
        value, success, error = result
        self.busy, self.busy_label = False, ""
        if error:
            if self.modal.get("kind") == "progress":
                self._pop()
            self.notify("操作已取消" if isinstance(error, InterruptedError) else f"操作失败：{error}")
        elif success:
            try:
                success(value)
            except (OSError, ValueError, RuntimeError) as error:
                self.notify(f"操作已执行，但更新状态失败：{error}")
        self._publish()

    def _system(self, action, payload=None):
        if action in self.pending_system or (action.startswith("wifi_") and any(pending.startswith("wifi_") for pending in self.pending_system)):
            self.notify("此请求正在处理中，请稍候")
            return
        self.pending_system.add(action)
        if action == 'lock':
            self.inputSuspended.emit(True)
        self.backend.request(action, payload or {})
        self._publish()

    @Slot(dict)
    def _agent_prompt(self, modal):
        if modal.get("dismiss"):
            token = modal["dismiss"]
            for index, existing in enumerate(self._modals):
                if existing.get("token") == token:
                    self._remove_modal(index)
                    break
            self._publish()
        else:
            if modal.get("deviceId") and not any(device["id"] == modal["deviceId"] for device in self.data["wifi"].get("devices", [])):
                if modal.get("token"):
                    self.backend.reply(modal["token"], None)
                self.notify("目标无线网卡已移除，请重新选择")
                return
            existing = next((entry for entry in self._modals if modal.get("token") and entry.get("token") == modal["token"]), None)
            if existing is not None:
                existing.update(modal)
                self._publish()
            else:
                self._push(modal)
                self.present.emit()

    def input_status(self, values):
        self.data["input"].update(values)
        self._publish()

    def close(self):
        self._cancel_modals()
        self.config.data["focus"] = self.navigation.positions
        try:
            self.config.save()
        except OSError:
            pass
        self.executor.shutdown(wait=True, cancel_futures=True)
