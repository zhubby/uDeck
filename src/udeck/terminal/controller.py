"""Window and modal state. PTYs belong to stable QML delegates, never to snapshots.

SPDX-License-Identifier: GPL-2.0-or-later
"""

import json
import uuid

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QModelIndex,
    QObject,
    Qt,
    QTimer,
    Signal,
    Slot,
)

from ..core import ConfigStore
from ..i18n import LANGUAGES, render, tr
from .core import LaunchRequest


class SessionModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []

    def roleNames(self):
        return {Qt.UserRole + 1: b"identifier", Qt.UserRole + 2: b"label"}

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.items)

    def data(self, index, role):
        if index.isValid() and 0 <= index.row() < len(self.items):
            return render(self.items[index.row()].get({Qt.UserRole + 1: "id", Qt.UserRole + 2: "title"}.get(role, "")), self.parent().language)
        return None

    def append(self, item):
        position = len(self.items)
        self.beginInsertRows(QModelIndex(), position, position)
        self.items.append(item)
        self.endInsertRows()

    def remove(self, position):
        self.beginRemoveRows(QModelIndex(), position, position)
        self.items.pop(position)
        self.endRemoveRows()


class TerminalController(QObject):
    changed = Signal()
    operate = Signal(str, str, str)
    closed = Signal()
    home = Signal()
    quickSettings = Signal()
    clipboardRequested = Signal()

    def __init__(self, request, preferences, *, mock=False, parent=None, language=None, theme=None):
        super().__init__(parent)
        self.preferences = preferences
        self.mock = mock
        interface = ConfigStore(preferences.path.with_name("settings.json")).data["preferences"]
        self.language = language or interface["language"]
        self.theme = theme or interface["theme"]
        self.tabs = SessionModel(self)
        self.requests = {}
        self.native_sessions = {}
        self.current = ""
        self.mode = "input"
        self.index = 0
        self.anchored = False
        self.query = ""
        self.message = ""
        self.pending_text = ""
        self.closing = []
        self.closing_window = False
        self.add_session(request)

    @Property(QObject, constant=True)
    def sessions(self):
        return self.tabs

    @Property(str, notify=changed)
    def snapshotJson(self):
        return json.dumps(render({"tabs": self.tabs.items, "current": self.current, "mode": self.mode,
                           "language": self.language, "theme": self.theme,
                           "index": self.index, "anchored": self.anchored,
                           "fontSize": self.preferences.font_size,
                           "colorScheme": self.preferences.color_scheme,
                           "query": self.query, "message": self.message,
                           "pastePreview": self._paste_preview(),
                           "options": self._options()}, self.language), ensure_ascii=False)

    @Slot(str, str, result=str)
    def translate(self, source, language):
        return render(tr(source), self.language)

    @Slot(str)
    def setLanguage(self, language):
        if not isinstance(language, str) or language not in LANGUAGES or language == self.language:
            return
        self.language = language
        if self.tabs.items:
            self.tabs.dataChanged.emit(self.tabs.index(0), self.tabs.index(len(self.tabs.items) - 1), [Qt.UserRole + 2])
        self.changed.emit()

    def setTheme(self, theme):
        if theme != self.theme:
            self.theme = theme
            self.changed.emit()

    def _paste_preview(self):
        # Escape controls so a preview cannot conceal an embedded Escape or NUL.
        return "".join(char if char in "\n\t" or ord(char) >= 32 and not 127 <= ord(char) < 160
                       else f"\\x{ord(char):02x}" for char in self.pending_text[:4000])

    def _options(self):
        if self.mode == "menu":
            return [tr('新建标签'), tr('历史与复制'), tr('搜索文字'), tr('粘贴'), tr('终端设置'), tr('返回桌面'), tr('关闭标签'), tr('关闭窗口')]
        if self.mode == "settings":
            return [tr('减小字号'), tr('增大字号'), tr('切换深浅配色'), tr('返回输入')]
        if self.mode in ("close", "paste"):
            return [tr('取消'), tr('确认关闭') if self.mode == "close" else tr('粘贴')]
        if self.mode == "error":
            return [tr('返回')]
        return []

    def add_session(self, request):
        if len(self.requests) >= 32:
            self.showError(tr('每个窗口最多 32 个会话，请关闭部分标签或新建窗口'))
            return
        identifier = uuid.uuid4().hex
        self.requests[identifier] = request
        self.current = identifier
        self.tabs.append({"id": identifier, "title": request.title or tr('本地 shell')})
        self.changed.emit()

    @Slot()
    def newTab(self):
        if self.closing_window or self.mode != "input":
            return
        original = self.requests[self.current]
        self.mode = "input"
        self.add_session(LaunchRequest(original.cwd, [], "", dict(original.environment)))

    @Slot(str, QObject)
    def attachSession(self, identifier, session):
        if identifier in self.requests:
            self.native_sessions[identifier] = session

    @Slot(str, result=str)
    def sessionSpec(self, identifier):
        request = self.requests[identifier]
        program, arguments = request.executable()
        environment = {**request.environment, "TERM": "xterm-256color", "COLORTERM": "truecolor"}
        return json.dumps({"cwd": request.cwd, "program": program, "arguments": arguments,
                           "environment": [f"{key}={value}" for key, value in environment.items()]}, ensure_ascii=False)

    @Slot(str, str)
    def updateTitle(self, identifier, title):
        for position, item in enumerate(self.tabs.items):
            if item["id"] == identifier and not self.requests[identifier].title:
                item["title"] = title[:160] or tr('本地 shell')
                self.tabs.dataChanged.emit(self.tabs.index(position), self.tabs.index(position), [Qt.UserRole + 2])
                self.changed.emit()
                break

    @Slot(str)
    def sessionFinished(self, identifier):
        if identifier not in self.requests:
            return
        position = next(i for i, item in enumerate(self.tabs.items) if item["id"] == identifier)
        del self.requests[identifier]
        self.native_sessions.pop(identifier, None)
        self.tabs.remove(position)
        if not self.tabs.items:
            self.closed.emit()
            return
        if self.current == identifier:
            self.current = self.tabs.items[min(position, len(self.tabs.items) - 1)]["id"]
            self.mode = "input"
        self.changed.emit()

    @Slot(str)
    def selectTab(self, identifier):
        if self.mode == "input" and identifier in self.requests:
            self.current = identifier
            self.changed.emit()

    def _send(self, action, text=""):
        self.operate.emit(self.current, action, text)

    @Slot()
    def requestCloseWindow(self):
        if self.closing_window:
            return
        self._ask_close(list(self.requests))

    def _ask_close(self, identifiers):
        self.closing = identifiers
        self.mode, self.index = "close", 0
        self.message = tr('关闭将结束所选会话及其中的任务。')
        self.changed.emit()

    @Slot(str)
    def showError(self, message):
        self.mode, self.index, self.message = "error", 0, message
        self.changed.emit()

    @Slot()
    def componentFailed(self):
        self.showError(tr('终端原生组件加载失败，请检查 udeck-terminal 安装和 Qt 版本。'))

    @Slot(str)
    def preparePaste(self, text):
        from .core import paste_needs_confirmation

        if not text:
            return
        if paste_needs_confirmation(text):
            self.pending_text = text
            self.mode, self.index = "paste", 0
            self.message = tr('粘贴 {value0} 个字符？包含换行或控制字符。', value0=len(text))
            self.changed.emit()
        else:
            self.mode = "input"
            self._send("paste", text)
            self.changed.emit()

    @Slot(str)
    def setQuery(self, text):
        self.query = text

    @Slot(bool)
    def search(self, forwards=True):
        if self.query:
            self._send("search-next" if forwards else "search-previous", self.query)

    @Slot(str)
    def command(self, action):
        if self.closing_window:
            return
        if action == "copy" and self.mode in ("history", "search"):
            self._send("copy-history")
            self.mode = "input"
            self.changed.emit()
            return
        if self.mode != "input":
            return
        if action == "menu":
            self.mode, self.index = "menu", 0
        elif action == "new-tab":
            self.newTab()
        elif action == "close-tab":
            self._ask_close([self.current])
        elif action == "history":
            self.mode, self.anchored = "history", False
            self._send("history")
        elif action == "search":
            self.mode = "search"
        elif action == "paste":
            self.clipboardRequested.emit()
        elif action == "copy":
            self._send("copy")
        elif action == "settings":
            self.mode, self.index = "settings", 0
        elif action == "home":
            self.mode = "input"
            self.home.emit()
        self.changed.emit()

    @Slot(str)
    def dispatch(self, action):
        if self.closing_window:
            return
        if self.mode == "input":
            if action in ("accept", "back"):
                self._send("return" if action == "accept" else "escape")
            elif action in ("up", "down", "left", "right"):
                self._send(action)
            elif action == "context":
                self.command("menu")
            elif action == "quick-settings":
                self.quickSettings.emit()
            elif action in ("previous-tab", "next-tab"):
                ids = list(self.requests)
                position = max(0, min(len(ids) - 1, ids.index(self.current) + (-1 if action == "previous-tab" else 1)))
                self.current = ids[position]
        elif action == "back":
            if self.mode in ("history", "search"):
                self._send("leave-history")
            self.mode = "input"
            self.pending_text = ""
        elif self.mode == "history":
            if action in ("up", "down", "left", "right", "page-up", "page-down"):
                self._send(action)
            elif action == "accept":
                self._send("copy-history" if self.anchored else "anchor")
                if self.anchored:
                    self.mode = "input"
                self.anchored = True
        elif self.mode == "search":
            if action == "accept":
                self.search(True)
            elif action in ("up", "down"):
                self.search(action == "down")
        elif action in ("up", "down", "left", "right"):
            delta = -1 if action in ("up", "left") else 1
            self.index = max(0, min(len(self._options()) - 1, self.index + delta))
        elif action == "accept":
            self._confirm()
        self.changed.emit()

    def _confirm(self):
        mode, position = self.mode, self.index
        if mode == "menu":
            actions = ("new-tab", "history", "search", "paste", "settings", "home", "close-tab", "close-window")
            self.mode = "input"
            if actions[position] == "close-window":
                self.requestCloseWindow()
            else:
                self.command(actions[position])
        elif mode == "settings":
            if position in (0, 1):
                self.preferences.change_font(-2 if position == 0 else 2)
            elif position == 2:
                self.preferences.color_scheme = "SolarizedLight" if self.preferences.color_scheme == "udeck" else "udeck"
            else:
                self.mode = "input"
            try:
                self.preferences.save()
            except OSError as error:
                self.showError(tr('设置保存失败：{value0}', value0=error))
        elif mode == "paste":
            text, self.pending_text = self.pending_text, ""
            self.mode = "input"
            if position == 1:
                self._send("paste", text)
        elif mode == "close":
            self.mode = "input"
            if position == 1:
                self.closing_window = set(self.closing) == set(self.requests)
                for identifier in self.closing:
                    self.operate.emit(identifier, "close", "")
                    if self.mock:
                        QTimer.singleShot(0, lambda identifier=identifier: self.sessionFinished(identifier))
        elif mode == "error":
            self.mode = "input"
