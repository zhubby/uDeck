import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from .appearance import THEMES
from .audio import AUDIO_ACTIONS
from .battery import battery_details, battery_summary
from .core import ALL_PAGES, PAGE_NAMES, PAGES, ConfigStore, Navigation, move_index
from .desktop import DesktopCatalog, open_terminal
from .file_controller import FileControls
from .files import FileOperations, file_kind, validate_name
from .home import home_shortcuts
from .hotspot import hotspot_summary, validate_hotspot_name
from .i18n import LANGUAGES, error_text, render, tr
from .key_test import KeyTestControls
from .launch_controller import LaunchControls
from .menu_icons import system_menu_icons
from .mock import mock_apps
from .shortcut_controller import ShortcutControls
from .shortcuts import binding_label
from .sounds import SoundFeedback, interaction
from .timezone import REGIONS, local_clock, region, zone_label, zone_summary
from .wifi import wifi_indicators, wifi_label, wifi_status, wifi_summary
from .wifi_controller import WifiControls

CATEGORY_NAMES = {"All": tr('全部应用'), "Development": tr('开发'), "Network": tr('网络'), "System": tr('系统'),
                  "Utility": tr('工具'), "Game": tr('游戏'), "Graphics": tr('图形'), "Office": tr('办公'), "AudioVideo": tr('影音'), "Other": tr('其他')}


class ShellController(LaunchControls, KeyTestControls, WifiControls, FileControls, ShortcutControls, SoundFeedback):
    changed = Signal()
    present = Signal()
    calibrationRequested = Signal()
    calibrationDirection = Signal(str)
    foregroundChanged = Signal(bool)
    applicationAction = Signal(str)
    consoleAction = Signal(str)
    inputSuspended = Signal(bool)
    taskFinished = Signal(object)
    launchFinished = Signal(object)
    startupLoaded = Signal(object)
    fileJobProgress = Signal(object)
    fileJobFinished = Signal(object)
    filePreviewScroll = Signal(int)
    screenshotFinished = Signal(object)

    def __init__(self, backend, window_service=None, config=None, catalog=None, mock=False, *, defer_startup=False):
        super().__init__()
        self.backend = backend
        self.window_service = window_service
        self.config = config or ConfigStore()
        self.language = self.config.data["preferences"]["language"]
        self.theme = self.config.data["preferences"]["theme"]
        self.mock = mock
        self.navigation = Navigation(self.config.data["focus"])
        self.catalog = catalog or DesktopCatalog(locale=self.language)
        self.applications = [] if defer_startup else mock_apps() if mock else self.catalog.entries()
        self.data = dict(backend.state)
        self.data.update({"windows": [], "files": [], "directory": str(Path.home()),
                          "input": {"available": False, "verified": False}})
        self.query = ""
        saved_category = self.config.data["preferences"]["category"]
        self.category = saved_category if saved_category in CATEGORY_NAMES else "All"
        self._modals = []
        self._text = ""
        self._init_key_test()
        self._init_shortcuts()
        self.toast = ""
        self.busy = False
        self.busy_label = ""
        self.clipboard = None
        self.show_hidden = self.config.data["preferences"]["showHidden"]
        self.directory_positions = {}
        self.operations = FileOperations()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="udeck-files")
        self.cancelled = threading.Event()
        self._init_file_controls()
        self.taskFinished.connect(self._finish_task)
        self.backend.updated.connect(self._update)
        self.backend.failed.connect(self._failure)
        self.backend.operationFailed.connect(self._operation_failed)
        self.backend.prompt.connect(self._agent_prompt)
        self.backend.completed.connect(self._system_completed)
        self.pending_system = set()
        self._wifi_sound_requests = {}
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self._clear_toast)
        self._init_loading(defer_startup)
        if window_service:
            window_service.changed.connect(self._windows_changed)
            window_service.failed.connect(self._failure)
        if mock:
            self.data["directory"] = "/home/demo"
            self._file_places_base = [{"id": name.lower(), "path": "/home/demo" + ("/" + name if name != "Home folder" else ""),
                                      "name": tr(name), "icon": "folder"}
                                     for name in ("Home folder", "Downloads", "Documents", "Music", "Videos", "Pictures")]
            self._file_places_base.append({"id": "trash", "path": "trash:///", "name": tr("Trash"), "icon": "user-trash"})
            self.data["files"] = [{"id": "/home/demo/" + name, "path": "/home/demo/" + name,
                                   "name": name, "directory": directory, "icon": "folder" if directory else "text-x-generic", "subtitle": subtitle}
                                  for name, directory, subtitle in [("Documents", True, tr('文件夹')), ("Downloads", True, tr('文件夹')), ("Projects", True, tr('文件夹')), ("Pictures", True, tr('文件夹')), ("掌机使用笔记.md", False, "2.4 KiB"), ("README.txt", False, "1.2 KiB")]]
            for entry in self.data["files"]:
                entry["kind"], entry["mime"], entry["icon"] = file_kind(entry["name"], entry["directory"])
            self.data["windows"] = [{"id": "terminal", "name": "zhubby@uconsole: ~", "appId": "terminal", "subtitle": tr('终端'), "icon": "utilities-terminal", "active": False}, {"id": "editor", "name": "uDeck — 代码编辑器", "appId": "code", "subtitle": "Visual Studio Code", "icon": "visual-studio-code", "active": False}]
        elif not defer_startup:
            self._browse(Path.home())

    @property
    def modal(self):
        return self._modals[-1] if self._modals else {}

    def _items(self):
        page = self.navigation.page
        if page == "home":
            return home_shortcuts(self.applications)
        if page == "apps":
            return [application for application in self.applications if (self.category == "All" or application["category"] == self.category) and (not self.query or self.query.casefold() in render(application["name"] + " " + application.get("subtitle", ""), self.language).casefold())]
        if page == "windows":
            return self.data["windows"]
        if page == "files":
            return self.data["files"]
        return self._settings()

    def _settings(self):
        audio, brightness = self.data["audio"], self.data["brightness"]
        wifi, bluetooth, battery = self.data["wifi"], self.data["bluetooth"], self.data["battery"]
        microphone = next((source for source in audio.get("inputs", []) if source["active"]), {})
        return [
            {"id": "volume", "name": tr('音量'), "subtitle": tr('静音') if audio.get("muted") else f"{round(audio.get('volume', 0) * 100)}%", "icon": "audio-volume-high", "value": audio.get("volume", 0), "disabled": not audio.get("available") or not audio.get("outputs")},
            {"id": "brightness", "name": tr('屏幕亮度'), "subtitle": f"{round(brightness.get('value', 0) * 100)}%", "icon": "display-brightness", "value": brightness.get("value", 0), "disabled": not brightness.get("available")},
            {"id": "output", "name": tr('音频输出'), "subtitle": next((output["name"] for output in audio.get("outputs", []) if output.get("active")), tr('未检测到音频输出')), "icon": "audio-card", "disabled": not audio.get("available")},
            {"id": "microphone", "name": tr("Microphone input"), "subtitle": microphone.get("name", tr("No microphone detected")), "icon": "audio-input-microphone", "disabled": not audio.get("available")},
            {"id": "wifi", "name": "Wi-Fi", "subtitle": wifi_summary(wifi), "icon": "network-wireless", "disabled": not wifi.get("available")},
            {"id": "hotspot", "name": tr("Hotspot"), "subtitle": hotspot_summary(wifi), "icon": "network-wireless", "disabled": not wifi.get("available")},
            {"id": "bluetooth", "name": tr('蓝牙'), "subtitle": tr('已开启') if bluetooth.get("powered") else tr('已关闭'), "icon": "bluetooth", "disabled": not bluetooth.get("available")},
            {"id": "battery", "name": tr('电池'), "subtitle": battery_summary(battery), "icon": "battery"},
            {"id": "input", "name": tr('按键与控制器'), "subtitle": tr('ABXY 已校准') if self.data["input"].get("verified") else (tr('ABXY 固件映射 · 可重新校准') if self.data["input"].get("mapped") else tr('校准物理 ABXY；不占用普通键盘字母')), "icon": "input-gaming"},
            {"id": "key-test", "name": tr('Key test'), "subtitle": tr('Full keyboard, controls and trackball'), "icon": "input-keyboard"},
            {"id": "shortcuts", "name": tr('Shortcut bindings'), "subtitle": tr('System actions and keyboard combinations'), "icon": "input-keyboard"},
            {"id": "language", "name": tr('语言'), "subtitle": LANGUAGES[self.language], "icon": "preferences-desktop-locale"},
            {"id": "theme", "name": tr('Theme'), "subtitle": THEMES[self.theme], "icon": "preferences-desktop-theme"},
            {"id": "ui-sounds", "name": tr("Interface sounds"), "subtitle": tr("On") if self.config.data["preferences"]["uiSounds"] else tr("Off"), "icon": "audio-volume-high"},
            {"id": "timezone", "name": tr('Time zone'), "subtitle": zone_summary(self.data["timezone"]), "icon": "preferences-system-time"},
            {"id": "lock", "name": tr('锁定屏幕'), "subtitle": tr('使用登录密码解锁'), "icon": "system-lock-screen"},
            {"id": "blank", "name": tr('熄灭屏幕'), "subtitle": tr('按方向键或键盘恢复；不是系统休眠'), "icon": "video-display"},
            {"id": "logout", "name": tr('注销会话'), "subtitle": tr('返回登录界面；请先保存工作'), "icon": "system-log-out"},
            {"id": "reboot", "name": tr('重新启动'), "subtitle": tr('需要二次确认'), "icon": "system-reboot"},
            {"id": "poweroff", "name": tr('关闭设备'), "subtitle": tr('需要二次确认'), "icon": "system-shutdown"},
        ]

    @Property(str, notify=changed)
    def snapshotJson(self):
        return self._snapshot()

    @Property(str, notify=changed)
    def viewSnapshotJson(self):
        return self._snapshot(compact=True)

    @Property(QObject, constant=True)
    def fileModel(self):
        return self._file_model

    @Slot(str, str)
    @interaction
    def fileAction(self, action, value):
        self._execute_option({"action": "files", "command": action, "value": value})

    @Slot(int)
    def setFileGridColumns(self, columns):
        self.file_columns = max(1, min(12, columns))

    def _snapshot(self, compact=False):
        items = self._items()
        selected = max(0, min(self.navigation.index, len(items) - 1))
        modal = {key: value for key, value in self.modal.items() if not compact or key not in ("items", "option")}
        if not compact and modal.get("secret"):
            modal["text"] = ""
        titles = {"home": tr('从这里开始'), "apps": CATEGORY_NAMES[self.category], "windows": tr('正在运行'), "files": tr("Trash") if self.data["directory"] == "trash:///" else Path(self.data["directory"]).name or "/", "settings": tr('设备设置')}
        descriptions = {"home": tr('Choose a destination with Left / Right'), "apps": tr('{value0} 个应用', value0=len(items)) + (tr(' · 搜索：{value0}', value0=self.query) if self.query else tr(' · X 筛选与操作')), "windows": tr('选择一个窗口，继续工作'), "files": self.data["directory"], "settings": tr('常用控制，直接完成')}
        return json.dumps(render({
            **{key: value for key, value in self.data.items() if not compact or key != "files"},
            "mock": self.mock, "page": self.navigation.page,
            "language": self.language, "theme": self.theme,
            "startup": self.startup, "appLaunch": self.app_launch,
            "reducedMotion": os.environ.get("UDECK_REDUCED_MOTION") == "1",
            "categoryNames": CATEGORY_NAMES,
            "pageNames": list(PAGE_NAMES), "pages": list(PAGES), "activeTab": self.navigation.tab_page,
            "title": titles[self.navigation.page], "description": descriptions[self.navigation.page],
            "index": selected, "zone": self.navigation.zone, "items": [] if compact and self.navigation.page == "files" else items,
            "fileState": self._file_state(),
            "modal": modal,
            "toast": self.toast, "busy": self.busy,
            "busyLabel": self.busy_label, "favorites": self.config.data["favorites"],
            "clipboard": bool(self.clipboard), "pending": list(self.pending_system), "wifiSummary": wifi_summary(self.data["wifi"]),
            "wifiIndicators": wifi_indicators(self.data["wifi"]),
            "homeShortcutHints": self._shortcut_hints('home', tr('主页')),
        }, self.language), ensure_ascii=False)

    @Slot(str, str, result=str)
    def translate(self, source, language):
        return render(tr(source), self.language)

    def _language_options(self):
        return [{"id": code, "label": name, "subtitle": tr('当前语言') if code == self.language else "",
                 "action": "language", "language": code} for code, name in LANGUAGES.items()]

    def _theme_options(self):
        return [{"id": code, "label": name, "subtitle": tr("Current theme") if code == self.theme else "",
                 "action": "theme", "theme": code} for code, name in THEMES.items()]

    @Slot(str, result=bool)
    def setTheme(self, theme):
        if not isinstance(theme, str) or theme not in THEMES:
            return False
        if theme == self.theme:
            return True
        previous = self.theme
        self.config.data["preferences"]["theme"] = theme
        try:
            self.config.save()
        except OSError as error:
            self.config.data["preferences"]["theme"] = previous
            self.notify(tr("Could not save theme settings: {error}", error=error_text(error)))
            return False
        self.theme = theme
        self._refresh_open_menu()
        self._publish()
        return True

    def _quick_options(self):
        controls = {"volume", "brightness", "output", "microphone", "wifi", "hotspot", "bluetooth", "battery", "input", "key-test", "language", "theme", "timezone", "ui-sounds"}
        return [{"label": entry["name"], "subtitle": entry["subtitle"], "action": "setting", "id": entry["id"],
                 "icon": entry["icon"], "disabled": entry.get("disabled", False)} for entry in self._settings() if entry["id"] in controls] + [
            {"label": tr('电源与会话'), "action": "power-menu"}, {"label": tr('运行中应用'), "action": "switcher"}]

    @Slot(str, result=bool)
    def setLanguage(self, language):
        if not isinstance(language, str) or language not in LANGUAGES:
            return False
        if language == self.language:
            return True
        previous = self.language
        # Desktop entry translations may change ordering. Keep application IDs
        # for both pages, including the owners beneath an open settings menu.
        old_page = self.navigation.page
        positions = dict(self.navigation.positions)
        positions[old_page] = self.navigation.index
        selected_apps = {}
        for page in ("home", "apps"):
            self.navigation.page = page
            items = self._items()
            position = positions.get(page, 0)
            if items:
                selected_apps[page] = items[min(position, len(items) - 1)]["id"]
        self.navigation.page = old_page
        self.config.data["preferences"]["language"] = language
        try:
            self.config.save()
        except OSError as error:
            self.config.data["preferences"]["language"] = previous
            self.notify(tr('语言设置保存失败：{error}', error=error_text(error)))
            return False
        self.language = language
        if not self.mock:
            self.catalog.locale = language
            self.applications = self.catalog.entries()
        for page, identifier in selected_apps.items():
            self.navigation.page = page
            items = self._items()
            self.navigation.positions[page] = next((index for index, item in enumerate(items) if item["id"] == identifier), 0)
        self.navigation.page = old_page
        if old_page in selected_apps:
            self.navigation.index = self.navigation.positions[old_page]
        self.navigation.modal_owners = [(page, zone, self.navigation.positions.get(page, index) if page in selected_apps else index)
                                        for page, zone, index in self.navigation.modal_owners]
        for modal in self._modals:
            if modal.get("source") == "language":
                modal["options"] = self._language_options()
        self._publish()
        return True

    def _publish(self):
        items = self._items()
        if self.startup["phase"] not in ("preparing", "scanning"):
            self.navigation.index = max(0, min(self.navigation.index, len(items) - 1))
        self._file_sync()
        self.changed.emit()

    @Slot(object)
    def _update(self, values):
        self.data.update(values)
        wifi = self.data["wifi"]
        devices = {device["id"]: device for device in wifi.get("devices", [])}
        for identifier, request in list(self._wifi_sound_requests.items()):
            device = devices.get(identifier)
            if device is None or request["epoch"] != wifi.get("epoch", ""):
                self._wifi_sound_requests.pop(identifier)
                continue
            operation = device.get("operation", {})
            operation_id = operation.get("id")
            if not operation_id or operation_id == request["baseline"]:
                continue
            request.setdefault("operation", operation_id)
            status = operation.get("status")
            if operation_id != request["operation"] or status in ("connected", "failed", "cancelled", "superseded"):
                self._wifi_sound_requests.pop(identifier)
                if operation_id == request["operation"]:
                    if status == "connected" and device.get("deviceState") == 100:
                        self.soundRequested.emit("success")
                    elif status == "failed":
                        self.soundRequested.emit("error")
        self._refresh_open_menu()
        self._publish()

    def _refresh_open_menu(self):
        devices = {device["id"]: device for device in self.data["wifi"].get("devices", [])}
        cards = {card["id"]: card for card in self.data["audio"].get("cards", [])}
        inputs = {source["id"] for source in self.data["audio"].get("inputs", [])}
        removed = False
        removed_audio = False
        for index in range(len(self._modals) - 1, -1, -1):
            device_id = self._modals[index].get("deviceId")
            if device_id and (device_id not in devices or self._modals[index].get("wifiEpoch", "") != self.data["wifi"].get("epoch", "")):
                self._remove_modal(index, reject=True)
                removed = True
            elif (device_id and self._modals[index].get("profileUuid") and self._modals[index].get("kind") != "menu"
                  and not any(profile.get("uuid") == self._modals[index]["profileUuid"] for profile in devices[device_id].get("saved", []))):
                self._remove_modal(index, reject=True)
                removed = True
            elif (device_id and "hotspotRevision" in self._modals[index] and
                  (self._modals[index]["hotspotRevision"] != devices[device_id].get("hotspot", {}).get("revision", "")
                   or devices[device_id].get("mode") == "ap")):
                self._remove_modal(index, reject=True)
                removed = True
            elif ((self._modals[index].get("cardId") and self._modals[index]["cardId"] not in cards)
                  or (self._modals[index].get("audioInputId") and self._modals[index]["audioInputId"] not in inputs)):
                self._remove_modal(index, reject=True)
                removed_audio = True
        for modal in self._modals:
            if modal.get("source") == "battery":
                modal.update(battery_details(self.data["battery"]))
                continue
            if modal.get("kind") != "menu":
                continue
            source = modal.get("source")
            if source == "wifi":
                options = self._wifi_options()
                modal["body"] = wifi_summary(self.data["wifi"])
            elif source == "hotspot":
                options = self._hotspot_options()
                modal["body"] = hotspot_summary(self.data["wifi"])
            elif source == "hotspot-device":
                options = self._hotspot_device_options(devices[modal["deviceId"]])
            elif source in ("wifi-device", "wifi-saved"):
                device = devices[modal["deviceId"]]
                options = self._wifi_device_options(device) if source == "wifi-device" else self._wifi_saved_options(device)
                modal["body"] = wifi_status(device, self.data["wifi"].get("enabled")) if source == "wifi-device" else wifi_label(device)
            elif source in ("wifi-network", "wifi-profiles", "wifi-details"):
                device = devices[modal["deviceId"]]
                options = self._refresh_wifi_network(modal, device)
            elif source == "bluetooth":
                options = self._bluetooth_options()
            elif source in ("audio-input", "audio-output"):
                options = self._audio_endpoint_options(source == "audio-input")
            elif source == "audio-cards":
                options = self._audio_card_options()
            elif source == "audio-profiles":
                options = self._audio_profile_options(cards[modal["cardId"]])
            elif source == "theme":
                options = self._theme_options()
            elif source in ("timezone-areas", "timezone-cities"):
                options = self._timezone_options(modal.get("region"))
                modal["body"] = self._timezone_body()
            elif source == "quick-settings":
                options = self._quick_options()
            elif source in ('shortcuts', 'shortcuts-group', 'shortcut-action'):
                options = self._shortcut_menu_options(modal)
            else:
                continue
            old_options = modal["options"]
            previous = old_options[min(modal["index"], len(old_options) - 1)] if old_options else {}
            modal["options"] = system_menu_icons(options, source)
            modal["index"] = next((index for index, option in enumerate(options) if option.get("id") == previous.get("id")), min(modal["index"], max(0, len(options) - 1)))
        if removed:
            self.notify(tr('无线网卡已移除或暂不可用，请重新选择'))
        if removed_audio:
            self.notify(tr('音频设备已移除'))

    @Slot(object)
    def _windows_changed(self, windows):
        self.data["windows"] = windows
        self.launches.windows_changed(windows)
        self._refresh_launch()
        self._publish()

    @Slot()
    def startupFrameSwapped(self):
        self._startup_frame()

    @Slot(object)
    def _startup_loaded(self, result):
        self._complete_startup(result)

    @Slot(object)
    def _launch_finished(self, result):
        self._complete_launch(result)

    @Slot(object)
    def _failure(self, message):
        self.notify(message)

    @Slot(str, object)
    def _operation_failed(self, action, message):
        if action in ("wifi_connect", "wifi_connect_saved", "wifi_reconnect"):
            self._wifi_sound_requests.clear()
        if action in self.pending_system and action != "refresh":
            self.soundRequested.emit("error")
        self.pending_system.discard(action)
        if action == "timezone_set":
            self._refresh_open_menu()
        if action == 'lock':
            self.inputSuspended.emit(False)
        self.notify(message)

    @Slot(str)
    def _system_completed(self, action):
        if action in self.pending_system and action in {
                "timezone_set", "wifi_update_password", "wifi_set_autoconnect", "wifi_forget",
                "audio_output", "audio_input", "audio_profile"}:
            self.soundRequested.emit("success")
        self.pending_system.discard(action)
        if action == "timezone_set":
            self._refresh_open_menu()
        if action == 'lock':
            self.inputSuspended.emit(False)
        if action == "wifi_update_password":
            self.notify(tr("Password saved. It will be used the next time you join."))
        elif action == "wifi_set_autoconnect":
            self.notify(tr("Auto-join preference saved"))
        elif action == "wifi_forget":
            self.notify(tr("Saved configuration forgotten"))
        elif action == "wifi_hotspot_configure":
            self.notify(tr("Hotspot configuration saved. Turn it on when ready."))
        elif action == "timezone_set":
            self.notify(tr("Time zone updated") if not self.mock else tr("Preview time zone updated"))
        elif action not in ("refresh", "bluetooth_stop", "wifi_connect", "wifi_connect_saved", "wifi_reconnect", "wifi_scan", "wifi_cancel_connect", "wifi_hotspot_start", "wifi_hotspot_stop"):
            self.notify(tr('预览操作已模拟，未操作真实设备') if self.mock else tr('请求已处理；连接结果以设备状态为准'))
        self._publish()

    def notify(self, message):
        if isinstance(message, BaseException):
            self.feedback("error")
        self.toast = error_text(message) if isinstance(message, BaseException) else message
        self.toast_timer.start(6000)
        self._publish()

    def _clear_toast(self):
        self.toast = ""
        self._publish()

    @Slot(str)
    @interaction
    def setPage(self, page):
        if page not in ALL_PAGES:
            return
        if page != self.navigation.page:
            self.feedback("open")
        self.navigation.set_page(page)
        self.navigation.zone = "content"
        if page == "files" and not self.mock:
            self._browse(self.data["directory"])
        self._publish()

    @Slot(int)
    @interaction
    def select(self, index):
        if self.startup["active"] or self.app_launch["pending"]:
            return
        if (self.navigation.index, self.navigation.zone) != (max(0, index), "content"):
            self.feedback("navigate")
        self.navigation.select(index)
        if self.navigation.page == "files":
            self.file_section = "list"
        self._publish()

    @Slot(bool)
    def windowActive(self, active):
        self._test_active = active
        self.launches.foreground_changed(active)
        self._refresh_launch()
        self._publish()
        if not active:
            self._clear_test_inputs()
        self.foregroundChanged.emit(active)
        if active:
            self._request_files_refresh()
        if not active and self.data["bluetooth"].get("discovering"):
            self.backend.request("bluetooth_stop")

    @Slot(str)
    @interaction
    def dispatch(self, action):
        if self.shortcut_recorder and self.shortcut_recorder.window:
            if action == 'accept':
                self.shortcut_recorder.confirm()
            elif action == 'back':
                self.shortcut_recorder.cancel()
            return
        if self.startup["active"]:
            return
        if self.app_launch["pending"]:
            if action in ("back", "home", "switcher", "quick-settings", "console"):
                self._dismiss_launch()
                if action == "back":
                    self.feedback("back")
                    return
            else:
                return
        if action == 'console':
            if not any(modal.get('source') == 'console' for modal in self._modals):
                self._cancel_modals()
                self._menu(tr('控制台'), [
                    {'id': command, 'label': label, 'action': 'console-control', 'command': command}
                    for command, label in (
                        ('home', tr('回到主界面')), ('switcher', tr('运行中')), ('settings', tr('设置')),
                        ('poweroff', tr('关机')), ('reboot', tr('重启')),
                    )
                ], source='console', body=tr('{shortcut} opens console · Esc / B returns to the application',
                     shortcut=binding_label(self.shortcut_store.bindings()['console'])
                         if self.shortcut_store else tr('Unbound')))
            self.present.emit()
            return
        if self.modal.get("kind") == "key-test":
            if action == "back" and not self.modal["exitHolding"]:
                self._pop()
            return
        if self.modal.get("kind") == "calibration" and action in ("up", "down", "left", "right"):
            self.calibrationDirection.emit(action)
            return
        if action in ("previous-page", "next-page"):
            if not self.modal and self.navigation.page in PAGES:
                index = PAGES.index(self.navigation.page)
                offset = -1 if action == "previous-page" else 1
                self.setPage(PAGES[max(0, min(index + offset, len(PAGES) - 1))])
            return
        if action == "home":
            if self.modal:
                self.feedback("back")
            self._cancel_modals()
            self.setPage("home")
            self.present.emit()
            return
        if action == "switcher":
            if self.modal:
                self.feedback("open")
            self._cancel_modals()
            self.setPage("windows")
            self.present.emit()
            return
        if action == "quick-settings":
            if self.modal.get("source") == "quick-settings":
                return
            self._menu(tr('快捷设置'), self._quick_options(), source="quick-settings")
            self.present.emit()
            return
        if self.modal:
            self._dispatch_modal(action)
            return
        if self.navigation.page == "files" and self._file_dispatch(action):
            return
        items = self._items()
        if action in ("left", "right", "up", "down"):
            before = (self.navigation.page, self.navigation.zone, self.navigation.index)
            columns = max(1, len(items)) if self.navigation.page == "home" else 5 if self.navigation.page == "apps" else 1
            self.navigation.move(action, len(items), columns)
            after = (self.navigation.page, self.navigation.zone, self.navigation.index)
            if before != after and (items or before[:2] != after[:2]):
                self.feedback("open" if before[0] != after[0] else "navigate")
        elif action == "accept":
            if self.navigation.zone == "tabs":
                self.navigation.zone = "content"
                self.feedback("accept")
            elif items:
                self.feedback("accept")
                self._activate(items[min(self.navigation.index, len(items) - 1)])
        elif action == "back":
            if self.navigation.page != "home":
                self.feedback("back")
            if self.navigation.page == "files" and Path(self.data["directory"]) not in (Path.home(), Path("/")):
                self._browse(Path(self.data["directory"]).parent)
            else:
                self.setPage("home")
        elif action == "context":
            self._context(items[min(self.navigation.index, len(items) - 1)] if items else None)
        elif action == "search":
            self._text_prompt(tr('搜索应用'), tr('输入应用名称，按 A 或 Enter 搜索'), "search", self.query)
        self._publish()

    def _activate(self, item):
        if item.get("disabled"):
            self.feedback("error")
            component = self.data.get(item["id"], {})
            self.notify(item.get("reason") or component.get("error", tr('此功能当前不可用')))
        elif self.navigation.page == "home" and item.get("homeKind") == "settings":
            self.setPage("settings")
        elif self.navigation.page in ("home", "apps"):
            self._launch(item)
        elif self.navigation.page == "windows":
            if not self.mock:
                try:
                    self.window_service.request(item["id"], "activate")
                except RuntimeError as error:
                    self.notify(error)
            else:
                self.notify(tr('预览：切换到 ') + item["name"])
        elif self.navigation.page == "files":
            self._activate_file(item)
        elif self.navigation.page == "settings":
            self.activateSetting(item["id"])

    def _launch(self, item):
        self._start_application(item)

    def _context(self, item):
        page = self.navigation.page
        if page == "home" and item:
            self._menu(item["name"], [{"label": tr('打开'), "action": "open-home", "item": item,
                                      "disabled": item.get("disabled", False), "reason": item.get("reason", "")}])
        elif page == "apps":
            options = []
            if item:
                options.extend([{"label": tr('打开应用'), "action": "launch", "item": item}, {"label": tr('取消收藏') if item["id"] in self.config.data["favorites"] else tr('加入收藏'), "action": "favorite", "id": item["id"]}])
            options.extend([{"label": tr('搜索应用'), "action": "search"}, {"label": tr('应用分类'), "action": "categories"}, {"label": tr('清除搜索与筛选'), "action": "clear-search"}])
            self._menu(item["name"] if item else tr('应用操作'), options)
        elif page == "files":
            self._file_context(item)
        elif page == "windows" and item:
            self._menu(item["name"], [{"label": tr('切换到窗口'), "action": "activate-window", "item": item}, {"label": tr('请求关闭窗口'), "action": "close-window", "item": item}])
        else:
            self._menu(tr('设备操作'), [{"label": tr('刷新设备状态'), "action": "system", "systemAction": "refresh"}, {"label": tr('校准 ABXY'), "action": "setting", "id": "input"}])

    @Slot(str)
    @interaction
    def activateSetting(self, identifier):
        if identifier == "shortcuts":
            self._open_shortcuts()
        elif identifier == "ui-sounds":
            previous = ConfigStore(self.config.path).data["preferences"]["uiSounds"]
            self.config.data["preferences"]["uiSounds"] = not previous
            try:
                self.config.save()
            except OSError:
                self.config.data["preferences"]["uiSounds"] = previous
                self.feedback("error")
                self.notify(tr("Could not save interface sound settings"))
                return
            self.feedback("toggle-off" if previous else "toggle-on")
            self._refresh_open_menu()
        elif identifier == "key-test":
            self._open_key_test()
        elif identifier == "timezone":
            options = self._timezone_options()
            current_region = region(self.data["timezone"].get("current", ""))
            self._menu(tr("Time zone"), options, source="timezone-areas", body=self._timezone_body(),
                       index=next((i for i, option in enumerate(options) if option["id"] == current_region), 0))
        elif identifier == "language":
            self._menu(tr('界面语言'), self._language_options(), source="language",
                       index=list(LANGUAGES).index(self.language))
        elif identifier == "theme":
            self._menu(tr('Interface theme'), self._theme_options(), source="theme",
                       index=list(THEMES).index(self.theme))
        elif identifier == "volume":
            self._menu(tr('音量'), [{"label": tr('调整音量'), "action": "setting", "id": "volume-level"}, {"label": tr('取消静音') if self.data["audio"].get("muted") else tr('静音'), "action": "system", "systemAction": "mute"}])
        elif identifier in ("volume-level", "brightness"):
            component = "audio" if identifier == "volume-level" else "brightness"
            if not self.data[component].get("available"):
                self.notify(self.data[component].get("error", tr('设备不可用')))
                return
            value = self.data[component].get("volume" if identifier == "volume-level" else "value", 0)
            payload = {}
            if identifier == "volume-level":
                output = next((output for output in self.data["audio"].get("outputs", []) if output["active"]), None)
                if output is None:
                    self.notify(tr('音频设备已移除'))
                    return
                payload["id"] = output["id"]
            self._push({"kind": "slider", "title": tr('音量') if identifier == "volume-level" else tr('屏幕亮度'), "action": "volume" if identifier == "volume-level" else identifier, "value": value, "payload": payload, "body": tr('左右调节 · A 应用 · B 取消')})
        elif identifier == "output":
            self._menu(tr('音频输出'), self._audio_endpoint_options(), source="audio-output")
        elif identifier == "microphone":
            self._menu(tr("Microphone input"), self._audio_endpoint_options(True), source="audio-input")
        elif identifier == "microphone-level":
            source = next((source for source in self.data["audio"].get("inputs", []) if source["active"]), None)
            if source is None or source.get("volume") is None:
                self.notify(tr("No microphone detected"))
                return
            self._push({"kind": "slider", "title": tr("Input volume"), "action": "audio_input_volume",
                        "value": source["volume"], "payload": {"id": source["id"]}, "audioInputId": source["id"],
                        "body": source["name"] + "\n" + tr('左右调节 · A 应用 · B 取消')})
        elif identifier == "audio-modes":
            self._menu(tr("Bluetooth audio modes"), self._audio_card_options(), source="audio-cards")
        elif identifier == "wifi":
            self._menu(tr('Wi-Fi 网卡'), self._wifi_options(), source="wifi", body=wifi_summary(self.data["wifi"]),
                       index=1 if self.data["wifi"].get("devices") else 0)
        elif identifier == "hotspot":
            self._menu(tr("Hotspot adapters"), self._hotspot_options(), source="hotspot", body=hotspot_summary(self.data["wifi"]))
        elif identifier == "bluetooth":
            self._menu(tr('蓝牙'), self._bluetooth_options(), source="bluetooth")
        elif identifier in ("poweroff", "reboot", "logout"):
            title = {"poweroff": tr('关闭设备？'), "reboot": tr('重新启动？'), "logout": tr('注销当前会话？')}[identifier]
            self._confirm(title, tr('这会关闭当前工作会话并可能中断 SSH。请确认工作已保存。'), {"action": "system", "systemAction": identifier})
        elif identifier in ("lock", "blank"):
            self._system(identifier)
        elif identifier == "battery":
            self._push({"kind": "information", "title": tr('电池与电源'), "source": "battery",
                        **battery_details(self.data["battery"])})
        elif identifier == "input":
            if self.mock:
                self._push({"kind": "information", "title": tr('物理按键校准'), "body": tr('请在 uConsole 实机上逐个按下 A、B、X、Y。预览不会将键盘字母当作手柄。')})
            elif self.data["input"].get("available"):
                self.calibrationRequested.emit()
            else:
                self._push({"kind": "information", "title": tr('未检测到独立手柄'), "body": self.data["input"].get("message", tr('请检查手柄模式。若 ABXY 上报 j/k/u/i 字母，请切换设备原有手柄模式；不需要刷写固件。'))})
        self._publish()

    @Slot(result=str)
    def currentTime(self):
        return local_clock(self.data["timezone"].get("current", ""))

    def _timezone_body(self):
        state = self.data["timezone"]
        if "timezone_set" in self.pending_system:
            return tr("Changing time zone…")
        return state.get("error") or tr("Current time zone: {zone}", zone=zone_summary(state))

    def _timezone_options(self, area=None):
        state = self.data["timezone"]
        zones = sorted(set(state.get("zones", [])))
        if area is None:
            options = [{"id": value, "label": REGIONS.get(value, value), "action": "timezone-region", "region": value,
                        "subtitle": tr("Current region") if value == region(state.get("current", "")) else ""}
                       for value in sorted({region(zone) for zone in zones})]
        else:
            options = [{"id": zone, "label": zone_label(zone.split("/", 1)[-1] if area != "Other" else zone),
                        "subtitle": tr("Current time zone") if zone == state.get("current") else zone,
                        "action": "timezone-set", "timezone": zone,
                        "disabled": not state.get("available") or "timezone_set" in self.pending_system,
                        "reason": state.get("error", tr("This request is being processed"))}
                       for zone in zones if region(zone) == area]
        return options or [{"id": "unavailable", "label": tr("Time zone service unavailable"),
                            "subtitle": state.get("error", tr("Not available")), "disabled": True}]

    def _audio_endpoint_options(self, inputs=False):
        audio = self.data["audio"]
        entries = audio.get("inputs" if inputs else "outputs", [])
        options = []
        active = next((entry for entry in entries if entry["active"]), None)
        if inputs and active:
            options += [
                {"id": "input-level", "label": tr("Input volume"),
                 "subtitle": f"{round(active['volume'] * 100)}%" if active.get("volume") is not None else tr("Not available"),
                 "action": "setting", "idSetting": "microphone-level", "disabled": active.get("volume") is None},
                {"id": "input-mute", "label": tr("Unmute microphone") if active.get("muted") else tr("Mute microphone"),
                 "action": "system", "systemAction": "audio_input_mute", "payload": {"id": active["id"]}},
            ]
        for entry in entries:
            subtitle = tr("Bluetooth") if entry.get("bluetooth") else ""
            if entry["active"]:
                current = tr("Current input") if inputs else tr('当前输出')
                subtitle = current + (" · " + subtitle if subtitle else "")
            options.append({"id": entry["id"], "label": entry["name"], "subtitle": subtitle,
                            "action": "system", "systemAction": "audio_input" if inputs else "audio_output",
                            "payload": {"id": entry["id"]}})
        if not entries:
            options.append({"id": "empty", "label": audio.get("inputError" if inputs else "outputError") or (tr("No microphone detected") if inputs else tr('未检测到音频输出')),
                            "action": "none", "disabled": True})
        if audio.get("cards") or audio.get("cardError"):
            options.append({"id": "audio-modes", "label": tr("Bluetooth audio modes"), "action": "setting"})
        options.append({"id": "bluetooth", "label": tr("Bluetooth devices"), "action": "setting",
                        "disabled": not self.data["bluetooth"].get("available")})
        return options

    def _audio_card_options(self):
        return [{"id": card["id"], "label": card["name"],
                 "subtitle": next((profile["name"] for profile in card["profiles"] if profile["active"]), ""),
                 "action": "audio-card", "cardId": card["id"]} for card in self.data["audio"].get("cards", [])] or [
                     {"id": "empty", "label": self.data["audio"].get("cardError") or tr("No connected Bluetooth audio device"),
                      "action": "none", "disabled": True}]

    def _audio_profile_options(self, card):
        return [{"id": profile["id"], "label": tr("Call mode") if profile["microphone"] else tr("Playback mode"),
                 "subtitle": (tr("Current mode") + " · " if profile["active"] else "") + profile["name"],
                 "action": "audio-profile", "cardId": card["id"], "profile": profile,
                 "disabled": not profile["available"], "reason": tr("Bluetooth audio mode is unavailable")}
                for profile in card["profiles"]] or [
                    {"id": "empty", "label": tr("Bluetooth audio mode is unavailable"), "action": "none", "disabled": True}]

    def _bluetooth_options(self):
        information = self.data["bluetooth"]
        if not information.get("available"):
            return [{"label": information.get("error", tr('蓝牙适配器不可用')), "action": "none", "disabled": True}]
        options = [{"id": "power", "label": tr('关闭蓝牙') if information["powered"] else tr('开启蓝牙'), "action": "system", "systemAction": "bluetooth_power", "payload": {"enabled": not information["powered"]}}, {"id": "scan", "label": tr('停止发现') if information.get("discovering") else tr('发现附近设备（30 秒）'), "action": "system", "systemAction": "bluetooth_stop" if information.get("discovering") else "bluetooth_scan", "disabled": not information["powered"]}]
        options += [{"id": device["id"], "label": device["name"], "subtitle": tr('已连接') if device["connected"] else tr('已配对 · 未连接') if device["paired"] else tr('未配对'), "action": "device", "device": device} for device in information.get("devices", [])]
        return options

    def _push(self, modal):
        self.feedback("open")
        if self.modal.get("kind") == "key-test":
            self._clear_test_inputs()
        if modal.get("deviceId"):
            modal.setdefault("wifiEpoch", self.data["wifi"].get("epoch", ""))
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
        if modal.get("kind") == "key-test":
            self._clear_test_inputs()
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
        self._push({"kind": "menu", "title": title, "options": system_menu_icons(options, values.get("source", "")), **values})

    def _confirm(self, title, body, option, **values):
        self._push({"kind": "confirm", "title": title, "body": body, "option": option, **values})

    def _text_prompt(self, title, body, purpose, text="", **values):
        self._push({"kind": "text", "title": title, "body": body, "purpose": purpose, "text": text, **values})

    def _dispatch_modal(self, action):
        if self._file_modal(action):
            return
        modal = self.modal
        kind = modal["kind"]
        if action == "back":
            self.feedback("back")
            if kind == "progress":
                self.cancelled.set()
            self._pop(reject=True)
            if modal.get('source') == 'application' and not self.modal:
                self.applicationAction.emit('return')
            elif modal.get('source') == 'console':
                self.consoleAction.emit('dismiss')
            return
        if kind == "menu":
            options = modal["options"]
            if action in ("up", "down") and options:
                previous = modal["index"]
                modal["index"] = move_index(modal["index"], action, len(options))
                if modal["index"] != previous:
                    self.feedback("navigate")
            elif action == "accept" and options:
                self.feedback("accept")
                option = options[min(modal["index"], len(options) - 1)]
                if option.get("disabled"):
                    self.feedback("error")
                    self.notify(option.get("reason") or tr('此项目当前不可用'))
                    return
                keep_parent = modal.get('source') in ('console', 'shortcuts', 'shortcuts-group', 'shortcut-action') or (modal.get("source") == "quick-settings" and option.get("id") in ("theme", "timezone", "key-test", "ui-sounds", "hotspot", "shortcuts"))
                if modal.get("source") not in ("wifi", "wifi-device", "wifi-saved", "wifi-network", "wifi-profiles", "wifi-details", "hotspot", "hotspot-device", "language", "theme", "timezone-areas", "timezone-cities", "audio-input", "audio-output", "audio-cards", "audio-profiles") and not keep_parent:
                    self._pop()
                self._execute_option(option)
        elif kind == "confirm":
            previous = modal["index"]
            if action in ("left", "up"):
                modal["index"] = 0
            elif action in ("right", "down"):
                modal["index"] = 1
            elif action == "accept":
                accepted = modal["index"] == 1
                self.feedback("accept" if accepted else "back")
                self._pop()
                if modal.get("token"):
                    self.backend.reply(modal["token"], accepted)
                elif accepted:
                    self._execute_option(modal["option"])
            if action in ("left", "right", "up", "down") and modal["index"] != previous:
                self.feedback("navigate")
        elif kind == "text" and action == "context" and modal.get("secret"):
            modal["reveal"] = not modal.get("reveal", False)
            self.feedback("toggle-on" if modal["reveal"] else "toggle-off")
        elif kind == "text" and action == "accept":
            self.feedback("accept")
            if modal.get("purpose") == "hotspot-name":
                try:
                    validate_hotspot_name(self._text)
                except ValueError as error:
                    modal["error"] = error_text(error)
                    self.feedback("error")
                    self._publish()
                    return
            if modal.get("wifiSecurity"):
                from .wifi_backend import validate_wifi_password
                try:
                    validate_wifi_password(self._text, modal["wifiSecurity"])
                except ValueError as error:
                    self.feedback("error")
                    modal["error"] = error_text(error)
                    self._publish()
                    return
            text = self._text
            self._pop()
            self._submit_text(modal, text)
        elif kind == "slider":
            if action in ("left", "right"):
                minimum = 0.05 if modal["action"] == "brightness" else 0
                previous = modal["value"]
                modal["value"] = max(minimum, min(1, modal["value"] + (0.05 if action == "right" else -0.05)))
                if modal["value"] != previous:
                    self.feedback("navigate")
            elif action == "accept":
                self.feedback("accept")
                self._pop()
                self._system(modal["action"], {"value": modal["value"], **modal.get("payload", {})})
        elif kind == "information" and action == "accept":
            self.feedback("back")
            self._pop()
        self._publish()

    @Slot(str)
    def editText(self, value):
        self._text = value
        if self.modal.get("kind") == "text":
            self.modal["text"] = value

    @Slot(int)
    @interaction
    def chooseModal(self, index):
        if not self.modal:
            return
        self.modal["index"] = index
        self._dispatch_modal("accept")

    def _execute_option(self, option):
        if self._shortcut_option(option):
            return
        try:
            self._apply_option(option)
        except (OSError, ValueError, KeyError, RuntimeError) as error:
            self.feedback("error")
            self.notify(tr('操作失败：{value0}', value0=error))

    def _apply_option(self, option):
        action = option["action"]
        item = option.get("item", {})
        if action == "files":
            self._file_command(option["command"], option.get("value", ""), option)
        elif action == "open-home":
            self._activate(item)
        elif action == "language":
            self.setLanguage(option["language"])
        elif action == "theme":
            self.setTheme(option["theme"])
        elif action == "timezone-region":
            area = option["region"]
            options = self._timezone_options(area)
            self._menu(REGIONS.get(area, area), options, source="timezone-cities", region=area,
                       body=self._timezone_body(), index=next((i for i, item in enumerate(options)
                           if item["id"] == self.data["timezone"].get("current")), 0))
        elif action == "timezone-set":
            state = self.data["timezone"]
            if not state.get("available"):
                raise RuntimeError(state.get("error", tr("Time zone service unavailable")))
            if option["timezone"] not in state.get("zones", []):
                raise ValueError(tr("Invalid time zone"))
            if option["timezone"] != state.get("current"):
                self._system("timezone_set", {"timezone": option["timezone"]})
        elif action == "application-control":
            self.applicationAction.emit(option['command'])
        elif action == 'console-control':
            self.consoleAction.emit(option['command'])
        elif action == "setting":
            self.activateSetting(option.get("idSetting", option["id"]))
        elif action == "audio-card":
            card = next((card for card in self.data["audio"].get("cards", []) if card["id"] == option["cardId"]), None)
            if card is None:
                raise ValueError(tr('音频设备已移除'))
            self._menu(card["name"], self._audio_profile_options(card), source="audio-profiles", cardId=card["id"],
                       body=tr("Call mode enables the microphone and may reduce playback quality."))
        elif action == "audio-profile":
            if option["profile"]["active"]:
                return
            self._confirm(tr("Switch Bluetooth audio mode?"), tr("This may briefly interrupt audio. Call mode enables the microphone and may reduce playback quality."),
                          {"action": "system", "systemAction": "audio_profile", "payload": {"id": option["cardId"], "profile": option["profile"]["id"]}},
                          cardId=option["cardId"])
        elif action == "power-menu":
            self._menu(tr('电源与会话'), [{"label": entry["name"], "subtitle": entry["subtitle"], "action": "setting", "id": entry["id"]} for entry in self._settings() if entry["id"] in ("lock", "blank", "logout", "reboot", "poweroff")])
        elif action == "system":
            self._system(option["systemAction"], option.get("payload", {}))
        elif action == "launch":
            self._launch(item)
        elif action == "favorite":
            self.config.favorite(option["id"], option["id"] not in self.config.data["favorites"])
            self.feedback("toggle-on" if option["id"] in self.config.data["favorites"] else "toggle-off")
        elif action == "search":
            self.dispatch("search")
        elif action == "categories":
            categories = {application["category"] for application in self.applications}
            self._menu(tr('应用分类'), [{"label": label, "action": "category", "id": identifier} for identifier, label in CATEGORY_NAMES.items() if identifier == "All" or identifier in categories])
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
            self._activate_file(item)
        elif action == "open-terminal":
            if self.mock:
                self.notify(tr('预览：在此打开终端'))
            else:
                self._run(tr('打开终端'), lambda: open_terminal(option["directory"]))
        elif action in ("mkdir", "rename"):
            self._text_prompt(tr('新建文件夹') if action == "mkdir" else tr('重命名'), tr('输入名称，按 A 或 Enter 确认'), action, "" if action == "mkdir" else item["name"], item=item, directory=self.data["directory"])
        elif action in ("copy", "cut"):
            self.clipboard = {"path": item["path"], "move": action == "cut"}
            self.notify(tr('已剪切，选择目标目录后粘贴') if action == "cut" else tr('已复制，选择目标目录后粘贴'))
        elif action in ("paste", "overwrite"):
            self._paste(replace=action == "overwrite")
        elif action == "hidden":
            self.show_hidden = not self.show_hidden
            self.config.data["preferences"]["showHidden"] = self.show_hidden
            self.config.save()
            self.feedback("toggle-on" if self.show_hidden else "toggle-off")
            self._browse(self.data["directory"])
        elif action in ("parent", "refresh-files"):
            self._browse(Path(self.data["directory"]).parent if action == "parent" else self.data["directory"])
        elif action == "trash":
            self._confirm(tr('移入回收站？'), item["name"] + tr('\n不会执行永久删除。'), {"action": "trash-confirm", "item": item})
        elif action == "trash-confirm":
            if self.mock:
                self.data["files"] = [entry for entry in self.data["files"] if entry["id"] != item["id"]]
            else:
                self._run(tr('移入回收站'), lambda: self.operations.trash(item["path"]), lambda result: self._browse(self.data["directory"]))
        elif action.startswith("hotspot-"):
            self._apply_hotspot_option(option)
        elif action.startswith("wifi-"):
            self._apply_wifi_option(option)
        elif action == "device":
            device = option["device"]
            options = []
            if not device["paired"]:
                options.append({"label": tr('配对并信任此设备'), "action": "device-pair", "device": device})
            else:
                options.append({"label": tr('断开连接') if device["connected"] else tr('连接设备'), "action": "system", "systemAction": "bluetooth_disconnect" if device["connected"] else "bluetooth_connect", "payload": {"id": device["id"]}})
                options.append({"label": tr('移除配对'), "action": "device-remove", "device": device})
            self._menu(device["name"], options)
        elif action in ("device-pair", "device-remove"):
            device = option["device"]
            self._confirm(tr('配对并信任？') if action == "device-pair" else tr('移除蓝牙设备？'), device["name"], {"action": "system", "systemAction": "bluetooth_pair" if action == "device-pair" else "bluetooth_remove", "payload": {"id": device["id"]}})
        elif action == "activate-window":
            self._activate(item)
        elif action == "close-window":
            self._confirm(tr('请求关闭窗口？'), item["name"] + tr('\n应用可能要求保存工作；不会强制结束进程。'), {"action": "window-close-confirm", "item": item})
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
        if self._file_submit(modal, text):
            return
        if modal.get("token"):
            self.backend.reply(modal["token"], text)
        elif modal.get("purpose") == "wifi-password":
            self._system("wifi_update_password", {**modal["payload"], "password": text})
        elif modal.get("purpose") in ("hotspot-name", "hotspot-password"):
            self._submit_hotspot_text(modal, text)
        elif modal["purpose"] == "search":
            self.query = text.strip()
            self.navigation.select(0)
            self.setPage("apps")
        elif self.mock:
            name = validate_name(text)
            if modal["purpose"] == "mkdir":
                identifier = str(Path(modal["directory"]) / name)
                self._file_entries = [*self._file_entries, {"id": identifier, "path": identifier, "name": name, "directory": True, "subtitle": tr('预览文件夹'), "icon": "folder"}]
                self._file_apply_query(identifier)
            elif modal["purpose"] == "rename":
                identifier = str(Path(modal["item"]["path"]).with_name(name))
                entries = []
                for entry in self._file_entries:
                    if entry["id"] == modal["item"]["id"]:
                        kind, mime, icon = file_kind(name, entry.get("directory", False))
                        entry = {**entry, "name": name, "path": identifier, "id": identifier, "kind": kind, "mime": mime, "icon": icon}
                    entries.append(entry)
                self._file_entries = entries
                self._file_apply_query(identifier)
            self._publish()
        elif modal["purpose"] == "mkdir":
            self._run(tr('创建文件夹'), lambda: self.operations.mkdir(modal["directory"], text), lambda result: self._browse(modal["directory"], str(result)))
        elif modal["purpose"] == "rename":
            self._run(tr('重命名'), lambda: self.operations.rename(modal["item"]["path"], text), lambda result: self._browse(modal["directory"], str(result)))

    def _browse(self, directory, select_path=None):
        self._browse_files(directory, select_path)

    def _paste(self, replace=False):
        self._file_paste("replace" if replace else "error")

    def _run(self, label, work, success=None, *, report_success=True):
        if self.busy:
            self.notify(tr('请等待当前文件操作完成'))
            return
        self.busy, self.busy_label = True, label
        audible = bool(self._feedback_depth)

        def complete(future):
            try:
                self.taskFinished.emit((future.result(), success, None, audible, report_success))
            except Exception as error:
                self.taskFinished.emit((None, success, error, audible, report_success))

        self.executor.submit(work).add_done_callback(complete)
        self._publish()

    @Slot(object)
    def _finish_task(self, result):
        value, success, error, audible, report_success = result
        self.busy, self.busy_label = False, ""
        if self._files_closing:
            return
        if error:
            if audible:
                self.soundRequested.emit("back" if isinstance(error, InterruptedError) else "error")
            if self.modal.get("kind") == "progress" and not self.modal.get("fileTaskId"):
                self._pop()
            self.notify(tr('操作已取消') if isinstance(error, InterruptedError) else tr('操作失败：{value0}', value0=error))
        elif success:
            try:
                success(value)
            except (OSError, ValueError, RuntimeError) as error:
                if audible:
                    self.soundRequested.emit("error")
                self.notify(tr('操作已执行，但更新状态失败：{value0}', value0=error))
            else:
                if audible and report_success:
                    self.soundRequested.emit("success")
        else:
            if audible and report_success:
                self.soundRequested.emit("success")
        self._publish()
        self._file_pending()

    def _system(self, action, payload=None):
        if (action in self.pending_system or (action.startswith("wifi_") and action != "wifi_cancel_connect" and any(pending.startswith("wifi_") for pending in self.pending_system))
                or (action in AUDIO_ACTIONS and self.pending_system & AUDIO_ACTIONS)):
            self.notify(tr('此请求正在处理中，请稍候'))
            return
        self.pending_system.add(action)
        if action == "timezone_set":
            self._refresh_open_menu()
        if action == 'lock':
            self.inputSuspended.emit(True)
        if action.startswith("wifi_"):
            payload = {"wifiEpoch": self.data["wifi"].get("epoch", ""), **(payload or {})}
            identifier = payload.get("deviceId")
            if action in ("wifi_connect", "wifi_connect_saved", "wifi_reconnect") and identifier:
                device = next((device for device in self.data["wifi"].get("devices", []) if device["id"] == identifier), {})
                self._wifi_sound_requests[identifier] = {"epoch": self.data["wifi"].get("epoch", ""),
                                                        "baseline": device.get("operation", {}).get("id")}
            elif action in ("wifi_cancel_connect", "wifi_disconnect"):
                self._wifi_sound_requests.pop(identifier, None)
            elif action == "wifi_power":
                self._wifi_sound_requests.clear()
        self.backend.request(action, payload or {})
        self._publish()

    @Slot(object)
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
                self.notify(tr('目标无线网卡已移除，请重新选择'))
                return
            existing = next((entry for entry in self._modals if modal.get("token") and entry.get("token") == modal["token"]), None)
            if existing is not None:
                existing.update(modal)
                self._publish()
            else:
                self._push(modal)
                self.present.emit()

    def input_status(self, values):
        if "keyTestNativeKeys" in values:
            self._set_test_native_keys(values["keyTestNativeKeys"])
        if values.get("available") is False or values.get("grabbed") is False:
            self._clear_test_inputs("gamepad")
        if values.get("pointer", {}).get("blockedDevices") == 0:
            self._clear_test_inputs("shoulder")
            self._clear_test_inputs("pointer")
        self.data["input"].update(values)
        self._publish()

    def close(self):
        self._close_shortcuts()
        self._close_loading()
        self._close_files()
        self._cancel_modals()
        self.config.data["focus"] = self.navigation.positions
        try:
            self.config.save()
        except OSError:
            pass
        self.executor.shutdown(wait=True, cancel_futures=True)
