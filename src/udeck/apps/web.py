"""Browser address parsing; web content is never an interface translation."""

import re
import uuid
from urllib.parse import quote_plus, urlsplit

from PySide6.QtCore import Property, QAbstractListModel, QModelIndex, QObject, Qt, Signal, Slot

from ..i18n import tr
from .controller import AppController


def address_url(value):
    text = value.strip()
    if not text:
        return "about:blank"
    if re.match(r"^[a-zA-Z][a-zA-Z\d+.-]*:", text) and not re.match(r"^[\w.-]+:\d+(/|$)", text):
        parsed = urlsplit(text)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError(tr("Only HTTP and HTTPS addresses are allowed"))
        return text
    if not any(c.isspace() for c in text) and ("." in text.split("/")[0] or text.startswith("localhost")):
        return "https://" + text
    return "https://duckduckgo.com/?q=" + quote_plus(text)


class BrowserTab(QObject):
    def __init__(self, url="about:blank", identifier=None, parent=None):
        super().__init__(parent)
        self.identifier = identifier or uuid.uuid4().hex
        self.initial_url = url
        self.url, self.title = url, ""
        self.loading, self.error, self.can_back = False, "", False

    @Property(str, constant=True)
    def tabId(self):
        return self.identifier

    @Property(str, constant=True)
    def initialUrl(self):
        return self.initial_url


class TabModel(QAbstractListModel):
    def __init__(self, tabs, parent):
        super().__init__(parent)
        self.tabs = tabs

    def rowCount(self, parent=QModelIndex()):  # noqa: B008
        return 0 if parent.isValid() else len(self.tabs)

    def roleNames(self):
        return {Qt.ItemDataRole.UserRole: b"tabObject"}

    def data(self, index, role=Qt.ItemDataRole.UserRole):
        if index.isValid() and role == Qt.ItemDataRole.UserRole and 0 <= index.row() < len(self.tabs):
            return self.tabs[index.row()]

    def append(self, tab):
        self.beginInsertRows(QModelIndex(), len(self.tabs), len(self.tabs))
        self.tabs.append(tab)
        self.endInsertRows()

    def remove(self, index):
        self.beginRemoveRows(QModelIndex(), index, index)
        self.tabs.pop(index)
        self.endRemoveRows()


class BrowserController(AppController):
    tabsChanged = Signal()

    def __init__(self, directory=None, language_path=None):
        super().__init__("browser", directory, language_path)
        self.page = "browser"
        self.web_mode, self.reading_text = "navigation", ""
        self.web_tabs = []
        self.tab_model = TabModel(self.web_tabs, self)
        self.current_tab = ""
        self.zoom = float(self.store.data["preferences"].get("zoom", 1.0))
        for entry in self.store.data["tabs"][:12]:
            if isinstance(entry, dict) and isinstance(entry.get("url"), str):
                try:
                    self.new_tab(address_url(entry["url"]) if entry["url"] != "about:blank" else "about:blank")
                except ValueError:
                    continue
        if not self.web_tabs:
            self.new_tab()

    @Property("QVariantList", notify=tabsChanged)
    def webTabs(self):
        return self.web_tabs

    @Property(QObject, constant=True)
    def browserModel(self):
        return self.tab_model

    @Property(str, constant=True)
    def profilePath(self):
        return str(self.store.path.parent / "browser-profile")

    def tabs(self):
        return [tab.title or (tr("New tab") if tab.url == "about:blank" else tab.url) for tab in self.web_tabs]

    def active_tab(self):
        return next((tab for tab in self.web_tabs if tab.identifier == self.current_tab), None)

    def new_tab(self, url="about:blank"):
        if len(self.web_tabs) >= 12:
            raise ValueError(tr("Close a tab before opening another (12 tab limit)"))
        tab = BrowserTab(url, parent=self)
        self.current_tab = tab.identifier
        self.tab = len(self.web_tabs)
        self.tab_model.append(tab)
        self.tabsChanged.emit()
        self.publish()

    @Slot(str)
    def closeTab(self, identifier):
        tab = next((t for t in self.web_tabs if t.identifier == identifier), None)
        if not tab:
            return
        index = self.web_tabs.index(tab)
        if len(self.web_tabs) == 1:
            self.new_tab()
        elif self.current_tab == identifier:
            neighbor = self.web_tabs[index + 1] if index + 1 < len(self.web_tabs) else self.web_tabs[index - 1]
            self.current_tab = neighbor.identifier
        self.tab_model.remove(index)
        self.tab = next(i for i, t in enumerate(self.web_tabs) if t.identifier == self.current_tab)
        self.tabsChanged.emit()
        tab.deleteLater()
        self.persist()
        self.publish()

    @Slot(int)
    def setTab(self, index):
        if 0 <= index < len(self.web_tabs):
            self.tab = index
            self.current_tab = self.web_tabs[index].identifier
            self.web_mode = "navigation"
            self.publish()

    def send(self, operation, **values):
        import json

        self.webAction.emit(operation, json.dumps({"id": self.current_tab, **values}))

    def navigate(self, text):
        self.send("navigate", url=address_url(text))
        self.web_mode = "navigation"

    @Slot(str, str, str, bool, bool, str)
    def webUpdated(self, identifier, url, title, loading, can_back, error):
        tab = next((t for t in self.web_tabs if t.identifier == identifier), None)
        if tab is None:
            return
        tab.url, tab.title, tab.loading, tab.can_back, tab.error = url, title, loading, can_back, error
        if not loading and not error and url.startswith(("https://", "http://")):
            self.store.data["history"] = [{"url": url, "title": title}] + [
                e for e in self.store.data["history"] if e.get("url") != url][:199]
        self.publish()

    @Slot(str, str)
    def readingReady(self, identifier, text):
        if identifier == self.current_tab:
            self.reading_text = text
            self.web_mode = "reading"
            self.publish()

    @Slot(str, bool)
    def webInput(self, identifier, editing):
        if identifier == self.current_tab:
            self.web_mode = "text" if editing else "navigation"
            self.publish()

    def extra_state(self):
        tab = self.active_tab()
        return {"currentTab": self.current_tab, "webMode": self.web_mode,
                "url": tab.url if tab else "about:blank", "webTitle": tab.title if tab else "",
                "loading": bool(tab and tab.loading), "webError": tab.error if tab else "",
                "zoom": self.zoom, "readingText": self.reading_text}

    def context(self):
        self.menu(tr("Browser actions"), [
            (tr("Address or search"), lambda: self.command("address")),
            (tr("New tab"), self.open_new_tab),
            (tr("Bookmarks"), lambda: self.saved_menu(False)),
            (tr("History"), lambda: self.saved_menu(True)),
            (tr("Bookmark this page"), self.bookmark),
            (tr("Interaction mode"), self.mode_menu),
            (tr("Reload"), lambda: self.send("reload")),
            (tr("Close tab"), self.close_active)])

    def open_new_tab(self):
        self.new_tab()
        self.clear_menus()

    def close_active(self):
        self.closeTab(self.current_tab)
        self.clear_menus()

    def bookmark(self):
        tab = self.active_tab()
        if tab.url.startswith(("http://", "https://")):
            self.store.data["bookmarks"][tab.url] = tab.title or tab.url
            self.persist()
        self.pop_menu()

    def saved_menu(self, history):
        entries = self.store.data["history"] if history else [
            {"url": url, "title": title} for url, title in self.store.data["bookmarks"].items()]
        self.menu(tr("History") if history else tr("Bookmarks"), [
            (e["title"] or e["url"], lambda url=e["url"]: self.saved_actions(url, history), e["url"])
            for e in entries], "" if entries else tr("No saved pages yet"))

    def saved_actions(self, url, history):
        self.menu(url, [(tr("Open"), lambda: self.open_saved(url)),
                        (tr("Remove"), lambda: self.remove_saved(url, history))])

    def open_saved(self, url):
        self.navigate(url)
        self.clear_menus()

    def remove_saved(self, url, history):
        if history:
            self.store.data["history"] = [e for e in self.store.data["history"] if e["url"] != url]
        else:
            self.store.data["bookmarks"].pop(url, None)
        self.persist()
        self.pop_menu()
        self.pop_menu()
        self.saved_menu(history)

    def mode_menu(self):
        self.menu(tr("Interaction mode"), [(tr(label), lambda mode=mode: self.set_mode(mode))
                  for label, mode in (("Link navigation", "navigation"), ("Reading", "reading"),
                                      ("Virtual pointer", "pointer"), ("Text input", "text"))])

    def set_mode(self, mode):
        self.clear_menus()
        if mode == "reading":
            self.send("reading")
        else:
            self.web_mode = mode
            self.send("mode", mode=mode)
        self.publish()

    @Slot(str)
    def dispatch(self, action):
        if self.menus or action in ("context", "quick-settings", "previous-tab", "next-tab"):
            return super().dispatch(action)
        if action == "back":
            if self.web_mode != "navigation":
                self.set_mode("navigation")
            elif self.active_tab().can_back:
                self.send("back")
            else:
                self.desktop("Home")
        elif action in ("up", "down", "left", "right", "accept"):
            if self.active_tab().url == "about:blank":
                if action == "accept":
                    self.command("address")
            else:
                self.send("input", action=action, mode=self.web_mode)
        self.publish()

    @Slot(str)
    def command(self, command):
        if command == "address":
            self.prompt(tr("Address or search"), self.navigate,
                        "" if self.active_tab().url == "about:blank" else self.active_tab().url)
        elif command in ("reload", "stop", "forward", "back"):
            self.send(command)
        elif command == "bookmarks":
            self.saved_menu(False)
        elif command == "new-tab":
            self.attempt(self.open_new_tab)
        else:
            super().command(command)
        self.publish()

    def settings_options(self):
        return [(tr("Page zoom: {value}", value=f"{self.zoom:.0%}"), self.zoom_menu),
                (tr("Interaction mode"), self.mode_menu)]

    def zoom_menu(self):
        self.menu(tr("Page zoom"), [(f"{z:.0%}", lambda z=z: self.set_zoom(z))
                                    for z in (0.8, 1, 1.25, 1.5, 2)])

    def set_zoom(self, value):
        self.zoom = value
        self.persist()
        self.pop_menu()

    @Slot(str, str, int)
    def permission(self, identifier, origin, feature):
        self.menu(tr("Website permission"), [
            (tr("Deny"), lambda: self.permission_answer(identifier, origin, feature, False)),
            (tr("Allow this time"), lambda: self.permission_answer(identifier, origin, feature, True))], origin)

    def permission_answer(self, identifier, origin, feature, allow):
        import json

        if any(t.identifier == identifier for t in self.web_tabs):
            self.webAction.emit("permission", json.dumps({"id": identifier, "origin": origin,
                                                         "feature": feature, "allow": allow}))
        self.pop_menu()

    def persist(self):
        self.store.data["tabs"] = [{"url": t.url} for t in self.web_tabs]
        self.store.data["preferences"]["zoom"] = self.zoom
        super().persist()

    @Slot(str)
    def openLink(self, url):
        self.attempt(lambda: self.new_tab(address_url(url)))

    @Slot(str, float, float)
    def webClick(self, identifier, x, y):
        from PySide6.QtCore import QPoint
        from PySide6.QtTest import QTest

        if (identifier != self.current_tab or not self.window or not self.window.isActive()
                or self.menus or not (0 <= x < self.window.width() and 0 <= y < self.window.height())):
            return
        # WebEngine needs QPA delivery to update mouse-button state and trusted history.
        # QTest's public QWindow API supplies that path, scoped to this foreground window.
        QTest.mouseClick(self.window, Qt.MouseButton.LeftButton, pos=QPoint(round(x), round(y)))

    @Slot(str)
    def webKey(self, action):
        from PySide6.QtTest import QTest

        key = {"left": Qt.Key.Key_Left, "right": Qt.Key.Key_Right, "up": Qt.Key.Key_Up,
               "down": Qt.Key.Key_Down, "accept": Qt.Key.Key_Return}.get(action)
        if self.window and self.window.isActive() and key and not self.menus:
            QTest.keyClick(self.window, key)

    @Slot(str, result=str)
    def navigationScript(self, action):
        import json
        from pathlib import Path

        return "(" + Path(__file__).with_name("navigation.js").read_text() + ")(" + json.dumps(action) + ")"

    @Slot(QObject)
    def configureProfile(self, profile):
        profile.downloadRequested.connect(self.download_requested)

    def download_requested(self, download):
        from pathlib import Path

        from PySide6.QtCore import QStandardPaths

        root = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation))
        name = Path(download.downloadFileName()).name or "download"
        if (root / name).exists():
            name = Path(name).stem + "-" + uuid.uuid4().hex[:8] + Path(name).suffix
        def accept():
            root.mkdir(parents=True, exist_ok=True)
            download.setDownloadDirectory(str(root))
            download.setDownloadFileName(name)
            download.accept()
            self.pop_menu()
            self.menu(tr("Download"), [(tr("Cancel download"), lambda: (download.cancel(), self.pop_menu()))], str(root / name))
        self.menu(tr("Download this file?"), [(tr("Download"), accept),
                                             (tr("Cancel"), lambda: (download.cancel(), self.pop_menu()))],
                  str(root / name))
        def finished():
            if download.isFinished():
                self.notice = tr("Download: {state}", state=download.state().name)
                self.publish()
        download.isFinishedChanged.connect(finished)
