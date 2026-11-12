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
from .i18n import LANGUAGES, Msg, error_text, render, tr
from .i18n import translate as translate_message
from .key_test import KeyTestControls
from .launch_controller import LaunchControls
from .menu_icons import system_menu_icons
from .mock import mock_apps
from .sharing import SharingControls
from .shortcut_controller import ShortcutControls
from .shortcuts import binding_label
from .sounds import SoundFeedback, interaction
from .text_input import composing_action_blocked
from .timezone import REGIONS, local_clock, region, zone_label, zone_summary
from .wifi import wifi_indicators, wifi_label, wifi_status, wifi_summary
from .wifi_controller import WifiControls

CATEGORY_NAMES = {"All": tr(Msg.ALL_APPS), "Development": tr(Msg.DEVELOPMENT), "Network": tr(Msg.NETWORK), "System": tr(Msg.SYSTEM),
                  "Utility": tr(Msg.UTILITIES), "Game": tr(Msg.GAMES), "Graphics": tr(Msg.GRAPHICS), "Office": tr(Msg.OFFICE), "AudioVideo": tr(Msg.MULTIMEDIA), "Other": tr(Msg.OTHER)}


class ShellController(LaunchControls, KeyTestControls, WifiControls, FileControls, ShortcutControls, SharingControls, SoundFeedback):
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
    networkAccessFinished = Signal(object)
    sharingFinished = Signal(object)
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
        self._init_sharing()
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
                                      "name": tr(key), "icon": "folder"}
                                     for name, key in (("Home folder", Msg.HOME_FOLDER), ("Downloads", Msg.DOWNLOADS),
                                                       ("Documents", Msg.DOCUMENTS), ("Music", Msg.MUSIC),
                                                       ("Videos", Msg.VIDEOS), ("Pictures", Msg.PICTURES))]
            self._file_places_base.append({"id": "trash", "path": "trash:///", "name": tr(Msg.TRASH), "icon": "user-trash"})
            self.data["files"] = [{"id": "/home/demo/" + name, "path": "/home/demo/" + name,
                                   "name": name, "directory": directory, "icon": "folder" if directory else "text-x-generic", "subtitle": subtitle}
                                  for name, directory, subtitle in [("Documents", True, tr(Msg.FOLDER)), ("Downloads", True, tr(Msg.FOLDER)), ("Projects", True, tr(Msg.FOLDER)), ("Pictures", True, tr(Msg.FOLDER)), ("掌机使用笔记.md", False, "2.4 KiB"), ("README.txt", False, "1.2 KiB")]]
            for entry in self.data["files"]:
                entry["kind"], entry["mime"], entry["icon"] = file_kind(entry["name"], entry["directory"])
            self.data["windows"] = [{"id": "terminal", "name": "zhubby@uconsole: ~", "appId": "terminal", "subtitle": tr(Msg.TERMINAL), "icon": "utilities-terminal", "active": False}, {"id": "editor", "name": "uDeck — 代码编辑器", "appId": "code", "subtitle": "Visual Studio Code", "icon": "visual-studio-code", "active": False}]
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
        return system_menu_icons([
            {"id": "volume", "name": tr(Msg.VOLUME), "subtitle": tr(Msg.MUTE) if audio.get("muted") else f"{round(audio.get('volume', 0) * 100)}%", "icon": "audio-volume-high", "value": audio.get("volume", 0), "disabled": not audio.get("available") or not audio.get("outputs")},
            {"id": "brightness", "name": tr(Msg.SCREEN_BRIGHTNESS), "subtitle": f"{round(brightness.get('value', 0) * 100)}%", "icon": "display-brightness", "value": brightness.get("value", 0), "disabled": not brightness.get("available")},
            {"id": "output", "name": tr(Msg.AUDIO_OUTPUT), "subtitle": next((output["name"] for output in audio.get("outputs", []) if output.get("active")), tr(Msg.NO_AUDIO_OUTPUT_DETECTED)), "icon": "audio-card", "disabled": not audio.get("available")},
            {"id": "microphone", "name": tr(Msg.MICROPHONE_INPUT), "subtitle": microphone.get("name", tr(Msg.NO_MICROPHONE_DETECTED)), "icon": "audio-input-microphone", "disabled": not audio.get("available")},
            {"id": "wifi", "name": "Wi-Fi", "subtitle": wifi_summary(wifi), "icon": "network-wireless", "disabled": not wifi.get("available")},
            {"id": "hotspot", "name": tr(Msg.HOTSPOT), "subtitle": hotspot_summary(wifi), "icon": "network-wireless", "disabled": not wifi.get("available")},
            {"id": "bluetooth", "name": tr(Msg.BLUETOOTH), "subtitle": tr(Msg.ENABLED) if bluetooth.get("powered") else tr(Msg.DISABLED), "icon": "bluetooth", "disabled": not bluetooth.get("available")},
            {"id": "sharing", "name": tr(Msg.SHARING), "subtitle": tr(Msg.WEB_AND_SMB_FILE_SHARING), "icon": "network-connect"},
            {"id": "battery", "name": tr(Msg.BATTERY), "subtitle": battery_summary(battery), "icon": "battery"},
            {"id": "input", "name": tr(Msg.BUTTONS_AND_CONTROLLERS), "subtitle": tr(Msg.ABXY_CALIBRATED) if self.data["input"].get("verified") else (tr(Msg.ABXY_FIRMWARE_MAPPING_RECALIBRATE_AVAILABLE) if self.data["input"].get("mapped") else tr(Msg.CALIBRATE_PHYSICAL_ABXY_KEYBOARD_LETTERS_STAY_AVAILABLE)), "icon": "udeck-setting:controller"},
            {"id": "key-test", "name": tr(Msg.KEY_TEST), "subtitle": tr(Msg.FULL_KEYBOARD_CONTROLS_AND_TRACKBALL), "icon": "udeck-setting:keyboard-fill"},
            {"id": "shortcuts", "name": tr(Msg.SHORTCUT_BINDINGS), "subtitle": tr(Msg.SYSTEM_ACTIONS_AND_KEYBOARD_COMBINATIONS), "icon": "udeck-setting:command"},
            {"id": "language", "name": tr(Msg.LANGUAGE), "subtitle": LANGUAGES[self.language], "icon": "preferences-desktop-locale"},
            {"id": "theme", "name": tr(Msg.THEME), "subtitle": THEMES[self.theme], "icon": "preferences-desktop-theme"},
            {"id": "ui-sounds", "name": tr(Msg.INTERFACE_SOUNDS), "subtitle": tr(Msg.ON) if self.config.data["preferences"]["uiSounds"] else tr(Msg.OFF), "checked": self.config.data["preferences"]["uiSounds"], "icon": "audio-volume-high"},
            {"id": "timezone", "name": tr(Msg.TIME_ZONE), "subtitle": zone_summary(self.data["timezone"]), "icon": "preferences-system-time"},
            {"id": "lock", "name": tr(Msg.LOCK_SCREEN), "subtitle": tr(Msg.UNLOCK_WITH_YOUR_LOGIN_PASSWORD), "icon": "system-lock-screen"},
            {"id": "blank", "name": tr(Msg.TURN_OFF_DISPLAY), "subtitle": tr(Msg.PRESS_A_DIRECTION_OR_KEYBOARD_KEY_TO_WAKE_THE_SYSTEM_STAYS_AWAKE), "icon": "video-display"},
            {"id": "logout", "name": tr(Msg.LOG_OUT), "subtitle": tr(Msg.RETURN_TO_LOGIN_SAVE_YOUR_WORK_FIRST), "icon": "system-log-out"},
            {"id": "reboot", "name": tr(Msg.RESTART_SYSTEM), "subtitle": tr(Msg.CONFIRMATION_REQUIRED), "icon": "system-reboot"},
            {"id": "poweroff", "name": tr(Msg.SHUT_DOWN), "subtitle": tr(Msg.CONFIRMATION_REQUIRED), "icon": "system-shutdown"},
        ], "settings")

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
        titles = {"home": tr(Msg.START_HERE), "apps": CATEGORY_NAMES[self.category], "windows": tr(Msg.RUNNING_APPS), "files": tr(Msg.TRASH) if self.data["directory"] == "trash:///" else Path(self.data["directory"]).name or "/", "settings": tr(Msg.DEVICE_SETTINGS)}
        descriptions = {"home": tr(Msg.CHOOSE_A_DESTINATION_WITH_LEFT_RIGHT), "apps": tr(Msg.APPS_VALUE0, value0=len(items)) + (tr(Msg.SEARCH_VALUE0_SUFFIX, value0=self.query) if self.query else tr(Msg.X_FILTER_AND_ACTIONS_SUFFIX)), "windows": tr(Msg.SELECT_A_WINDOW_TO_CONTINUE), "files": self.data["directory"], "settings": tr(Msg.EVERYDAY_CONTROLS_WITHIN_REACH)}
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
            "homeShortcutHints": self._shortcut_hints('home', tr(Msg.HOME)),
        }, self.language), ensure_ascii=False)

    @Property("QVariantMap", constant=True)
    def messageKeys(self):
        return {key.name: key.value for key in Msg}

    @Slot(str, str, result=str)
    def translate(self, key, language):
        return translate_message(key, self.language)

    def _language_options(self):
        return [{"id": code, "label": name, "subtitle": tr(Msg.CURRENT_LANGUAGE) if code == self.language else "",
                 "action": "language", "language": code} for code, name in LANGUAGES.items()]

    def _theme_options(self):
        return [{"id": code, "label": name, "subtitle": tr(Msg.CURRENT_THEME) if code == self.theme else "",
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
            self.notify(tr(Msg.COULD_NOT_SAVE_THEME_SETTINGS_ERROR, error=error_text(error)))
            return False
        self.theme = theme
        self._refresh_open_menu()
        self._publish()
        return True

    def _quick_options(self):
        controls = {"volume", "brightness", "output", "microphone", "wifi", "hotspot", "bluetooth", "sharing", "battery", "input", "key-test", "language", "theme", "timezone", "ui-sounds"}
        return [{"label": entry["name"], "subtitle": entry["subtitle"], "action": "setting", "id": entry["id"],
                 "icon": entry["icon"], "checked": entry.get("checked"), "disabled": entry.get("disabled", False)} for entry in self._settings() if entry["id"] in controls] + [
            {"label": tr(Msg.POWER_AND_SESSION), "action": "power-menu"}, {"label": tr(Msg.RUNNING_APPLICATIONS), "action": "switcher"}]

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
            self.notify(tr(Msg.COULD_NOT_SAVE_LANGUAGE_SETTINGS_ERROR, error=error_text(error)))
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
                modal["options"] = system_menu_icons(self._language_options(), "language")
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
        self._sharing_refresh()
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
            elif source == "volume":
                options = self._volume_options()
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
            self.notify(tr(Msg.THE_WI_FI_ADAPTER_WAS_REMOVED_OR_IS_UNAVAILABLE_SELECT_AN_ADAPTER_AGAIN))
        if removed_audio:
            self.notify(tr(Msg.THE_AUDIO_DEVICE_WAS_REMOVED))

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
            self.notify(tr(Msg.PASSWORD_SAVED_IT_WILL_BE_USED_THE_NEXT_TIME_YOU_JOIN))
        elif action == "wifi_set_autoconnect":
            self.notify(tr(Msg.AUTO_JOIN_PREFERENCE_SAVED))
        elif action == "wifi_forget":
            self.notify(tr(Msg.SAVED_CONFIGURATION_FORGOTTEN))
        elif action == "wifi_hotspot_configure":
            self.notify(tr(Msg.HOTSPOT_CONFIGURATION_SAVED_TURN_IT_ON_WHEN_READY))
        elif action == "timezone_set":
            self.notify(tr(Msg.TIME_ZONE_UPDATED) if not self.mock else tr(Msg.PREVIEW_TIME_ZONE_UPDATED))
        elif action not in ("refresh", "bluetooth_stop", "wifi_connect", "wifi_connect_saved", "wifi_reconnect", "wifi_scan", "wifi_cancel_connect", "wifi_hotspot_start", "wifi_hotspot_stop"):
            self.notify(tr(Msg.PREVIEW_ACTION_SIMULATED_NO_HARDWARE_CHANGES) if self.mock else tr(Msg.REQUEST_PROCESSED_CHECK_THE_DEVICE_STATUS_FOR_THE_CONNECTION_RESULT))
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
        if composing_action_blocked(self, action):
            return
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
                self._menu(tr(Msg.CONTROL_PANEL), [
                    {'id': command, 'label': label, 'action': 'console-control', 'command': command}
                    for command, label in (
                        ('home', tr(Msg.BACK_TO_HOME)), ('switcher', tr(Msg.RUNNING)), ('settings', tr(Msg.SETTINGS)),
                        ('poweroff', tr(Msg.POWER_OFF)), ('reboot', tr(Msg.REBOOT)),
                    )
                ], source='console', body=tr(Msg.SHORTCUT_OPENS_CONSOLE_ESC_B_RETURNS_TO_THE_APPLICATION,
                     shortcut=binding_label(self.shortcut_store.bindings()['console'])
                         if self.shortcut_store else tr(Msg.UNBOUND)))
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
            self._menu(tr(Msg.QUICK_SETTINGS), self._quick_options(), source="quick-settings")
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
            self._text_prompt(tr(Msg.SEARCH_APPS), tr(Msg.ENTER_AN_APP_NAME_THEN_PRESS_A_OR_ENTER_TO_SEARCH), "search", self.query)
        self._publish()

    def _activate(self, item):
        if item.get("disabled"):
            self.feedback("error")
            component = self.data.get(item["id"], {})
            self.notify(item.get("reason") or component.get("error", tr(Msg.THIS_FEATURE_IS_CURRENTLY_UNAVAILABLE)))
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
                self.notify(tr(Msg.PREVIEW_SWITCH_TO_PREFIX) + item["name"])
        elif self.navigation.page == "files":
            self._activate_file(item)
        elif self.navigation.page == "settings":
            self.activateSetting(item["id"])

    def _launch(self, item):
        self._start_application(item)

    def _context(self, item):
        page = self.navigation.page
        if page == "home" and item:
            self._menu(item["name"], [{"label": tr(Msg.OPEN), "action": "open-home", "item": item,
                                      "disabled": item.get("disabled", False), "reason": item.get("reason", "")}])
        elif page == "apps":
            options = []
            if item:
                options.extend([{"label": tr(Msg.OPEN_APP), "action": "launch", "item": item}, {"label": tr(Msg.REMOVE_FROM_FAVORITES) if item["id"] in self.config.data["favorites"] else tr(Msg.ADD_TO_FAVORITES), "action": "favorite", "id": item["id"]}])
            options.extend([{"label": tr(Msg.SEARCH_APPS), "action": "search"}, {"label": tr(Msg.APP_CATEGORIES), "action": "categories"}, {"label": tr(Msg.CLEAR_SEARCH_AND_FILTERS), "action": "clear-search"}])
            self._menu(item["name"] if item else tr(Msg.APP_ACTIONS), options)
        elif page == "files":
            self._file_context(item)
        elif page == "windows" and item:
            self._menu(item["name"], [{"label": tr(Msg.SWITCH_TO_WINDOW), "action": "activate-window", "item": item}, {"label": tr(Msg.REQUEST_WINDOW_CLOSE), "action": "close-window", "item": item}])
        else:
            self._menu(tr(Msg.DEVICE_ACTIONS), [{"label": tr(Msg.REFRESH_DEVICE_STATUS), "action": "system", "systemAction": "refresh"}, {"label": tr(Msg.CALIBRATE_ABXY), "action": "setting", "id": "input"}])

    @Slot(str)
    @interaction
    def activateSetting(self, identifier):
        if identifier == "sharing":
            self._sharing_menu()
        elif identifier == "shortcuts":
            self._open_shortcuts()
        elif identifier == "ui-sounds":
            previous = ConfigStore(self.config.path).data["preferences"]["uiSounds"]
            self.config.data["preferences"]["uiSounds"] = not previous
            try:
                self.config.save()
            except OSError:
                self.config.data["preferences"]["uiSounds"] = previous
                self.feedback("error")
                self.notify(tr(Msg.COULD_NOT_SAVE_INTERFACE_SOUND_SETTINGS))
                return
            self.feedback("toggle-off" if previous else "toggle-on")
            self._refresh_open_menu()
        elif identifier == "key-test":
            self._open_key_test()
        elif identifier == "timezone":
            options = self._timezone_options()
            current_region = region(self.data["timezone"].get("current", ""))
            self._menu(tr(Msg.TIME_ZONE), options, source="timezone-areas", body=self._timezone_body(),
                       index=next((i for i, option in enumerate(options) if option["id"] == current_region), 0))
        elif identifier == "language":
            self._menu(tr(Msg.INTERFACE_LANGUAGE), self._language_options(), source="language",
                       index=list(LANGUAGES).index(self.language))
        elif identifier == "theme":
            self._menu(tr(Msg.INTERFACE_THEME), self._theme_options(), source="theme",
                       index=list(THEMES).index(self.theme))
        elif identifier == "volume":
            self._menu(tr(Msg.VOLUME), self._volume_options(), source="volume")
        elif identifier in ("volume-level", "brightness"):
            component = "audio" if identifier == "volume-level" else "brightness"
            if not self.data[component].get("available"):
                self.notify(self.data[component].get("error", tr(Msg.DEVICE_UNAVAILABLE)))
                return
            value = self.data[component].get("volume" if identifier == "volume-level" else "value", 0)
            payload = {}
            if identifier == "volume-level":
                output = next((output for output in self.data["audio"].get("outputs", []) if output["active"]), None)
                if output is None:
                    self.notify(tr(Msg.THE_AUDIO_DEVICE_WAS_REMOVED))
                    return
                payload["id"] = output["id"]
            self._push({"kind": "slider", "title": tr(Msg.VOLUME) if identifier == "volume-level" else tr(Msg.SCREEN_BRIGHTNESS), "action": "volume" if identifier == "volume-level" else identifier, "value": value, "payload": payload, "body": tr(Msg.LEFT_RIGHT_ADJUST_A_APPLY_B_CANCEL)})
        elif identifier == "output":
            self._menu(tr(Msg.AUDIO_OUTPUT), self._audio_endpoint_options(), source="audio-output")
        elif identifier == "microphone":
            self._menu(tr(Msg.MICROPHONE_INPUT), self._audio_endpoint_options(True), source="audio-input")
        elif identifier == "microphone-level":
            source = next((source for source in self.data["audio"].get("inputs", []) if source["active"]), None)
            if source is None or source.get("volume") is None:
                self.notify(tr(Msg.NO_MICROPHONE_DETECTED))
                return
            self._push({"kind": "slider", "title": tr(Msg.INPUT_VOLUME), "action": "audio_input_volume",
                        "value": source["volume"], "payload": {"id": source["id"]}, "audioInputId": source["id"],
                        "body": source["name"] + "\n" + tr(Msg.LEFT_RIGHT_ADJUST_A_APPLY_B_CANCEL)})
        elif identifier == "audio-modes":
            self._menu(tr(Msg.BLUETOOTH_AUDIO_MODES), self._audio_card_options(), source="audio-cards")
        elif identifier == "wifi":
            self._menu(tr(Msg.WI_FI_ADAPTERS), self._wifi_options(), source="wifi", body=wifi_summary(self.data["wifi"]),
                       index=1 if self.data["wifi"].get("devices") else 0)
        elif identifier == "hotspot":
            self._menu(tr(Msg.HOTSPOT_ADAPTERS), self._hotspot_options(), source="hotspot", body=hotspot_summary(self.data["wifi"]))
        elif identifier == "bluetooth":
            self._menu(tr(Msg.BLUETOOTH), self._bluetooth_options(), source="bluetooth")
        elif identifier in ("poweroff", "reboot", "logout"):
            title = {"poweroff": tr(Msg.SHUT_DOWN_PROMPT), "reboot": tr(Msg.RESTART_SYSTEM_PROMPT), "logout": tr(Msg.LOG_OUT_OF_THIS_SESSION_PROMPT)}[identifier]
            self._confirm(title, tr(Msg.THIS_CLOSES_THE_CURRENT_WORK_SESSION_AND_MAY_INTERRUPT_SSH_SAVE_YOUR_WORK_FIRST), {"action": "system", "systemAction": identifier})
        elif identifier in ("lock", "blank"):
            self._system(identifier)
        elif identifier == "battery":
            self._push({"kind": "information", "title": tr(Msg.BATTERY_AND_POWER), "source": "battery",
                        **battery_details(self.data["battery"])})
        elif identifier == "input":
            if self.mock:
                self._push({"kind": "information", "title": tr(Msg.PHYSICAL_BUTTON_CALIBRATION), "body": tr(Msg.PHYSICAL_ABXY_CALIBRATION_INSTRUCTIONS)})
            elif self.data["input"].get("available"):
                self.calibrationRequested.emit()
            else:
                self._push({"kind": "information", "title": tr(Msg.NO_SEPARATE_GAMEPAD_DETECTED), "body": self.data["input"].get("message", tr(Msg.CHECK_ABXY_GAMEPAD_MODE_INSTRUCTIONS))})
        self._publish()

    @Slot(result=str)
    def currentTime(self):
        return local_clock(self.data["timezone"].get("current", ""))

    def _timezone_body(self):
        state = self.data["timezone"]
        if "timezone_set" in self.pending_system:
            return tr(Msg.CHANGING_TIME_ZONE)
        return state.get("error") or tr(Msg.CURRENT_TIME_ZONE_ZONE, zone=zone_summary(state))

    def _timezone_options(self, area=None):
        state = self.data["timezone"]
        zones = sorted(set(state.get("zones", [])))
        if area is None:
            options = [{"id": value, "label": REGIONS.get(value, value), "action": "timezone-region", "region": value,
                        "subtitle": tr(Msg.CURRENT_REGION) if value == region(state.get("current", "")) else ""}
                       for value in sorted({region(zone) for zone in zones})]
        else:
            options = [{"id": zone, "label": zone_label(zone.split("/", 1)[-1] if area != "Other" else zone),
                        "subtitle": tr(Msg.CURRENT_TIME_ZONE) if zone == state.get("current") else zone,
                        "action": "timezone-set", "timezone": zone,
                        "disabled": not state.get("available") or "timezone_set" in self.pending_system,
                        "reason": state.get("error", tr(Msg.THIS_REQUEST_IS_BEING_PROCESSED))}
                       for zone in zones if region(zone) == area]
        return options or [{"id": "unavailable", "label": tr(Msg.TIME_ZONE_SERVICE_UNAVAILABLE),
                            "subtitle": state.get("error", tr(Msg.NOT_AVAILABLE)), "disabled": True}]

    def _volume_options(self):
        audio = self.data["audio"]
        disabled = not audio.get("available") or not audio.get("outputs")
        return [
            {"id": "volume-level", "label": tr(Msg.ADJUST_VOLUME), "subtitle": f"{round(audio.get('volume', 0) * 100)}%",
             "action": "setting", "disabled": disabled},
            {"id": "mute", "label": tr(Msg.MUTE), "checked": bool(audio.get("muted")), "pendingAction": "mute",
             "action": "system", "systemAction": "mute", "disabled": disabled},
        ]

    def _audio_endpoint_options(self, inputs=False):
        audio = self.data["audio"]
        entries = audio.get("inputs" if inputs else "outputs", [])
        options = []
        active = next((entry for entry in entries if entry["active"]), None)
        if inputs and active:
            options += [
                {"id": "input-level", "label": tr(Msg.INPUT_VOLUME),
                 "subtitle": f"{round(active['volume'] * 100)}%" if active.get("volume") is not None else tr(Msg.NOT_AVAILABLE),
                 "action": "setting", "idSetting": "microphone-level", "disabled": active.get("volume") is None},
                {"id": "input-mute", "label": tr(Msg.MUTE_MICROPHONE), "checked": bool(active.get("muted")),
                 "pendingAction": "audio_input_mute",
                 "action": "system", "systemAction": "audio_input_mute", "payload": {"id": active["id"]}},
            ]
        for entry in entries:
            subtitle = tr(Msg.BLUETOOTH) if entry.get("bluetooth") else ""
            if entry["active"]:
                current = tr(Msg.CURRENT_INPUT) if inputs else tr(Msg.CURRENT_OUTPUT)
                subtitle = current + (" · " + subtitle if subtitle else "")
            options.append({"id": entry["id"], "label": entry["name"], "subtitle": subtitle,
                            "action": "system", "systemAction": "audio_input" if inputs else "audio_output",
                            "payload": {"id": entry["id"]}})
        if not entries:
            options.append({"id": "empty", "label": audio.get("inputError" if inputs else "outputError") or (tr(Msg.NO_MICROPHONE_DETECTED) if inputs else tr(Msg.NO_AUDIO_OUTPUT_DETECTED)),
                            "action": "none", "disabled": True})
        if audio.get("cards") or audio.get("cardError"):
            options.append({"id": "audio-modes", "label": tr(Msg.BLUETOOTH_AUDIO_MODES), "action": "setting"})
        options.append({"id": "bluetooth", "label": tr(Msg.BLUETOOTH_DEVICES), "action": "setting",
                        "disabled": not self.data["bluetooth"].get("available")})
        return options

    def _audio_card_options(self):
        return [{"id": card["id"], "label": card["name"],
                 "subtitle": next((profile["name"] for profile in card["profiles"] if profile["active"]), ""),
                 "action": "audio-card", "cardId": card["id"]} for card in self.data["audio"].get("cards", [])] or [
                     {"id": "empty", "label": self.data["audio"].get("cardError") or tr(Msg.NO_CONNECTED_BLUETOOTH_AUDIO_DEVICE),
                      "action": "none", "disabled": True}]

    def _audio_profile_options(self, card):
        return [{"id": profile["id"], "label": tr(Msg.CALL_MODE) if profile["microphone"] else tr(Msg.PLAYBACK_MODE),
                 "subtitle": (tr(Msg.CURRENT_MODE) + " · " if profile["active"] else "") + profile["name"],
                 "action": "audio-profile", "cardId": card["id"], "profile": profile,
                 "disabled": not profile["available"], "reason": tr(Msg.BLUETOOTH_AUDIO_MODE_IS_UNAVAILABLE)}
                for profile in card["profiles"]] or [
                    {"id": "empty", "label": tr(Msg.BLUETOOTH_AUDIO_MODE_IS_UNAVAILABLE), "action": "none", "disabled": True}]

    def _bluetooth_options(self):
        information = self.data["bluetooth"]
        if not information.get("available"):
            return [{"label": information.get("error", tr(Msg.BLUETOOTH_ADAPTER_UNAVAILABLE)), "action": "none", "disabled": True}]
        options = [
            {"id": "power", "label": tr(Msg.BLUETOOTH), "checked": bool(information["powered"]),
             "pendingAction": "bluetooth_power", "action": "system", "systemAction": "bluetooth_power",
             "payload": {"enabled": not information["powered"]}},
            {"id": "scan", "label": tr(Msg.DISCOVER_NEARBY_DEVICES_30_SECONDS), "checked": bool(information.get("discovering")),
             "pendingAction": "bluetooth_stop" if information.get("discovering") else "bluetooth_scan",
             "action": "system", "systemAction": "bluetooth_stop" if information.get("discovering") else "bluetooth_scan",
             "disabled": not information["powered"]},
        ]
        options += [{"id": device["id"], "label": device["name"], "subtitle": tr(Msg.CONNECTED) if device["connected"] else tr(Msg.PAIRED_DISCONNECTED) if device["paired"] else tr(Msg.NOT_PAIRED), "action": "device", "device": device} for device in information.get("devices", [])]
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
                    self.notify(option.get("reason") or tr(Msg.THIS_ITEM_IS_CURRENTLY_UNAVAILABLE))
                    return
                keep_parent = modal.get('source', '').startswith('sharing') or modal.get('source') in ('console', 'shortcuts', 'shortcuts-group', 'shortcut-action') or (modal.get("source") == "quick-settings" and option.get("id") in ("theme", "timezone", "key-test", "ui-sounds", "hotspot", "shortcuts", "sharing"))
                if modal.get("source") not in ("wifi", "wifi-device", "wifi-saved", "wifi-network", "wifi-profiles", "wifi-details", "hotspot", "hotspot-device", "bluetooth", "volume", "language", "theme", "timezone-areas", "timezone-cities", "audio-input", "audio-output", "audio-cards", "audio-profiles") and not keep_parent:
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
            self.notify(tr(Msg.OPERATION_FAILED_VALUE0, value0=error))

    def _apply_option(self, option):
        action = option["action"]
        item = option.get("item", {})
        if action == "sharing":
            self._sharing_command(option["protocol"], option["command"], option.get("value", ""))
        elif action == "files":
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
                raise RuntimeError(state.get("error", tr(Msg.TIME_ZONE_SERVICE_UNAVAILABLE)))
            if option["timezone"] not in state.get("zones", []):
                raise ValueError(tr(Msg.INVALID_TIME_ZONE))
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
                raise ValueError(tr(Msg.THE_AUDIO_DEVICE_WAS_REMOVED))
            self._menu(card["name"], self._audio_profile_options(card), source="audio-profiles", cardId=card["id"],
                       body=tr(Msg.CALL_MODE_ENABLES_THE_MICROPHONE_AND_MAY_REDUCE_PLAYBACK_QUALITY))
        elif action == "audio-profile":
            if option["profile"]["active"]:
                return
            self._confirm(tr(Msg.SWITCH_BLUETOOTH_AUDIO_MODE_PROMPT), tr(Msg.AUDIO_PROFILE_CHANGE_INSTRUCTIONS),
                          {"action": "system", "systemAction": "audio_profile", "payload": {"id": option["cardId"], "profile": option["profile"]["id"]}},
                          cardId=option["cardId"])
        elif action == "power-menu":
            self._menu(tr(Msg.POWER_AND_SESSION), [{"label": entry["name"], "subtitle": entry["subtitle"], "action": "setting", "id": entry["id"]} for entry in self._settings() if entry["id"] in ("lock", "blank", "logout", "reboot", "poweroff")])
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
            self._menu(tr(Msg.APP_CATEGORIES), [{"label": label, "action": "category", "id": identifier} for identifier, label in CATEGORY_NAMES.items() if identifier == "All" or identifier in categories])
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
                self.notify(tr(Msg.PREVIEW_OPEN_TERMINAL_HERE))
            else:
                self._run(tr(Msg.OPEN_TERMINAL), lambda: open_terminal(option["directory"]))
        elif action in ("mkdir", "rename"):
            self._text_prompt(tr(Msg.NEW_FOLDER) if action == "mkdir" else tr(Msg.RENAME), tr(Msg.ENTER_A_NAME_THEN_PRESS_A_OR_ENTER_TO_CONFIRM), action, "" if action == "mkdir" else item["name"], item=item, directory=self.data["directory"])
        elif action in ("copy", "cut"):
            self.clipboard = {"path": item["path"], "move": action == "cut"}
            self.notify(tr(Msg.CUT_CHOOSE_A_DESTINATION_FOLDER_AND_PASTE) if action == "cut" else tr(Msg.COPIED_CHOOSE_A_DESTINATION_FOLDER_AND_PASTE))
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
            self._confirm(tr(Msg.MOVE_TO_TRASH_PROMPT), item["name"] + tr(Msg.THIS_DOES_NOT_PERMANENTLY_DELETE_THE_ITEM_NOTICE), {"action": "trash-confirm", "item": item})
        elif action == "trash-confirm":
            if self.mock:
                self.data["files"] = [entry for entry in self.data["files"] if entry["id"] != item["id"]]
            else:
                self._run(tr(Msg.MOVE_TO_TRASH), lambda: self.operations.trash(item["path"]), lambda result: self._browse(self.data["directory"]))
        elif action.startswith("hotspot-"):
            self._apply_hotspot_option(option)
        elif action.startswith("wifi-"):
            self._apply_wifi_option(option)
        elif action == "device":
            device = option["device"]
            options = []
            if not device["paired"]:
                options.append({"label": tr(Msg.PAIR_AND_TRUST_THIS_DEVICE), "action": "device-pair", "device": device})
            else:
                options.append({"label": tr(Msg.DISCONNECT) if device["connected"] else tr(Msg.CONNECT_DEVICE), "action": "system", "systemAction": "bluetooth_disconnect" if device["connected"] else "bluetooth_connect", "payload": {"id": device["id"]}})
                options.append({"label": tr(Msg.REMOVE_PAIRING), "action": "device-remove", "device": device})
            self._menu(device["name"], options)
        elif action in ("device-pair", "device-remove"):
            device = option["device"]
            self._confirm(tr(Msg.PAIR_AND_TRUST_PROMPT) if action == "device-pair" else tr(Msg.REMOVE_BLUETOOTH_DEVICE_PROMPT), device["name"], {"action": "system", "systemAction": "bluetooth_pair" if action == "device-pair" else "bluetooth_remove", "payload": {"id": device["id"]}})
        elif action == "activate-window":
            self._activate(item)
        elif action == "close-window":
            self._confirm(tr(Msg.REQUEST_WINDOW_CLOSE_PROMPT), item["name"] + tr(Msg.THE_APP_MAY_ASK_YOU_TO_SAVE_YOUR_WORK_IT_WILL_NOT_BE_FORCIBLY_TERMINATED_NOTICE), {"action": "window-close-confirm", "item": item})
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
                self._file_entries = [*self._file_entries, {"id": identifier, "path": identifier, "name": name, "directory": True, "subtitle": tr(Msg.PREVIEW_FOLDER), "icon": "folder"}]
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
            self._run(tr(Msg.CREATE_FOLDER), lambda: self.operations.mkdir(modal["directory"], text), lambda result: self._browse(modal["directory"], str(result)))
        elif modal["purpose"] == "rename":
            self._run(tr(Msg.RENAME), lambda: self.operations.rename(modal["item"]["path"], text), lambda result: self._browse(modal["directory"], str(result)))

    def _browse(self, directory, select_path=None):
        self._browse_files(directory, select_path)

    def _paste(self, replace=False):
        self._file_paste("replace" if replace else "error")

    def _run(self, label, work, success=None, *, report_success=True):
        if self.busy:
            self.notify(tr(Msg.WAIT_FOR_THE_CURRENT_FILE_OPERATION_TO_FINISH))
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
            self.notify(tr(Msg.OPERATION_CANCELLED) if isinstance(error, InterruptedError) else tr(Msg.OPERATION_FAILED_VALUE0, value0=error))
        elif success:
            try:
                success(value)
            except (OSError, ValueError, RuntimeError) as error:
                if audible:
                    self.soundRequested.emit("error")
                self.notify(tr(Msg.THE_OPERATION_COMPLETED_BUT_STATUS_COULD_NOT_BE_UPDATED_VALUE0, value0=error))
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
            self.notify(tr(Msg.THIS_REQUEST_IS_BEING_PROCESSED_PLEASE_WAIT))
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
                self.notify(tr(Msg.THE_TARGET_WI_FI_ADAPTER_WAS_REMOVED_SELECT_AN_ADAPTER_AGAIN))
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
        self._close_sharing()
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
