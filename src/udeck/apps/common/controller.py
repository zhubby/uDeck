"""Shared focus stack and translated interface, independent of native engines."""

import json
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot
from PySide6.QtDBus import QDBusConnection, QDBusMessage

from udeck.apps.common.library import Library
from udeck.apps.common.model import CardListModel
from udeck.apps.common.state import AppState
from udeck.core import ConfigStore, move_index
from udeck.i18n import Msg, language_code, render, tr
from udeck.i18n import translate as translate_message
from udeck.sounds import SoundFeedback, interaction
from udeck.text_input import composing_action_blocked


class AppController(SoundFeedback):
    changed = Signal()
    closed = Signal()
    present = Signal()
    webAction = Signal(str, str)
    selectionChanged = Signal()
    saveFailed = Signal(object)

    def __init__(self, app, directory=None, language_path=None):
        super().__init__()
        self.app = app
        self.store = AppState(app, directory, background=True)
        self.store.on_error = self.saveFailed.emit
        self.saveFailed.connect(self._save_failed)
        self._closed = False
        self.config_path = language_path
        preferences = ConfigStore(language_path).data["preferences"]
        self.language, self.theme = preferences["language"], preferences["theme"]
        self.library = self.create_library(app) if app != "browser" else None
        self.window = None
        self.inputs = None
        self.isolated = False
        self.page, self.tab, self.selected = "library", 0, ""
        self.columns = 3
        self.history, self.menus = [], []
        self.filter, self.folder = "", ""
        self.error, self.notice, self.current = "", "", None
        self._callbacks, self._serial = {}, 0
        self._rows = []
        self._card_model = CardListModel(self)
        self._card_key = None
        self._row_revision = 0
        self._published_selection = None
        self._last_saved = ""
        self.poller = QTimer(self)
        self.poller.setInterval(1000)
        self.poller.timeout.connect(self.poll)
        self.poller.start()
        if self.library:
            self.library.changed.connect(self._library_changed)
            self.library.lost.connect(self.source_lost)

    def create_library(self, app):
        return Library(app, self.store, self)

    def start(self):
        if self.library:
            self.library.refresh()
        self.publish()

    def poll(self):
        preferences = ConfigStore(self.config_path).data["preferences"]
        if (preferences["language"], preferences["theme"]) != (self.language, self.theme):
            self.language, self.theme = preferences["language"], preferences["theme"]
            self.publish()
        if self.library:
            self.library.check_sources()

    def tabs(self):
        return [tr(Msg.LIBRARY), tr(Msg.FOLDERS)]

    def rows(self):
        if not self.library:
            return []
        items = [i for i in self.library.items if i["sourceId"] not in self.library.unavailable]
        if self.folder:
            items = [i for i in items if i["folder"] == self.folder]
        if self.filter:
            items = [i for i in items if self.filter.casefold() in
                     (i["title"] + " " + i.get("artist", "")).casefold()]
        if self.tabs()[self.tab] == tr(Msg.FOLDERS) and not self.folder:
            folders = sorted({i["folder"] for i in items})
            return [{"id": "folder:" + p, "title": Path(p).name, "subtitle": p,
                     "kind": "folder", "cover": ""} for p in folders]
        return [{**i, "subtitle": i.get("artist") or i["format"], "kind": "item"} for i in items]

    def extra_state(self):
        return {}

    def _library_changed(self):
        self._row_revision += 1
        self.publish()

    def _view_rows(self):
        library = self.library
        key = (self._row_revision, id(library.items) if library else 0,
               len(library.items) if library else 0,
               frozenset(library.unavailable) if library else frozenset(),
               self.page, self.tab, self.folder, self.filter, self.language,
               getattr(self, 'album', ''), getattr(self, 'platform', ''),
               id(getattr(self, 'catalog', None)), getattr(library, 'root_id', ''),
               tuple(self.store.data['recent']), tuple(self.store.data['favorites']),
               tuple(self.queue.items) if hasattr(self, 'queue') else ())
        if key != self._card_key:
            self._reconcile_rows(self.rows())
            self._card_model.set_entries(self._rows, self.language)
            self._card_key = key
        return self._rows

    def _reconcile_rows(self, rows):
        previous_index = next((i for i, row in enumerate(self._rows) if row["id"] == self.selected), 0)
        if self.selected not in {row["id"] for row in rows}:
            self.selected = rows[min(previous_index, len(rows) - 1)]["id"] if rows else ""
        self._rows = rows

    def snapshot(self, compact=False):
        rows = self._view_rows() if compact else self.rows()
        if not compact:
            self._view_rows()
        return {"app": self.app, "language": self.language, "theme": self.theme, "page": self.page,
                "tabs": self.tabs(), "tab": self.tab, **({} if compact else {"cards": rows}), "selected": self.selected,
                "current": self.current or {}, "filter": self.filter, "folder": self.folder,
                "menu": {k: v for k, v in self.menus[-1].items() if k not in ("submit", "pickerParent")} if self.menus else {}, "error": self.error,
                "notice": self.notice, "scanning": bool(self.library and self.library.pending),
                "sourceErrors": [value for value in self.library.errors.values() if value] if self.library else [],
                "count": len(rows), **self.extra_state()}

    @Property(str, notify=changed)
    def snapshotJson(self):
        return json.dumps(render(self.snapshot(), self.language), ensure_ascii=False)

    @Property(str, notify=changed)
    def viewSnapshotJson(self):
        return json.dumps(render(self.snapshot(compact=True), self.language), ensure_ascii=False)

    @Property(QObject, constant=True)
    def cardModel(self):
        return self._card_model

    @Property(int, notify=selectionChanged)
    def selectedIndex(self):
        return self._card_model.by_id.get(self.selected, -1)

    @Property('QVariantMap', notify=selectionChanged)
    def selectedItem(self):
        return self._card_model.item(self.selected)

    @Property(bool, constant=True)
    def isolatedMode(self):
        return self.isolated

    @Property("QVariantMap", constant=True)
    def messageKeys(self):
        return {key.name: key.value for key in Msg}

    @Slot(str, str, result=str)
    def translate(self, key, language):
        return translate_message(key, language)

    def publish(self):
        self._view_rows()
        selection = (self.selected, self.selectedIndex, self._card_key)
        if selection != self._published_selection:
            self._published_selection = selection
            self.selectionChanged.emit()
        self.changed.emit()

    def persist(self):
        self.store.data["focus"][str(self.tab)] = self.selected
        self.store.save()

    def attempt(self, action):
        try:
            return action()
        except (OSError, ValueError, RuntimeError) as error:
            self.feedback("error")
            self.error = tr(Msg.OPERATION_FAILED_ERROR, error=error)
            self.publish()
            return None

    @Slot(object)
    def _save_failed(self, error):
        self.feedback('error')
        self.error = tr(Msg.OPERATION_FAILED_ERROR, error=error)
        self.publish()

    def menu(self, title, options=(), body="", owner=None, quiet=False, icon=""):
        if not quiet:
            self.feedback("open")
        if not icon and self.menus:
            parent = self.menus[-1]
            icon = parent["options"][parent["index"]].get("icon", "")
        rows = []
        for label, callback, *detail in options:
            self._serial += 1
            key = str(self._serial)
            self._callbacks[key] = callback
            rows.append({"id": key, "title": label, "subtitle": detail[0] if detail else "",
                         "icon": detail[1] if len(detail) > 1 else icon,
                         "disabled": callback is None})
        if not rows or all(r["disabled"] for r in rows):
            self._serial += 1
            key = str(self._serial)
            self._callbacks[key] = self.pop_menu
            rows.append({"id": key, "title": tr(Msg.BACK), "subtitle": "", "icon": "go-previous" if icon else "", "disabled": False})
        self.menus.append({"id": rows[0]["id"], "title": title, "body": body, "options": rows,
                           "index": next(i for i, r in enumerate(rows) if not r["disabled"]),
                           "owner": owner or (self.current or {}).get("sourceId", ""),
                           "input": False, "draft": ""})
        self.publish()

    def prompt(self, title, callback, draft="", body="", owner=None):
        self.menu(title, [(tr(Msg.CONFIRM), lambda: self.submit(self.menus[-1]["draft"]))], body, owner)
        self.menus[-1].update(input=True, draft=draft, submit=callback)
        self.publish()

    def pop_menu(self):
        if self.menus:
            for row in self.menus.pop()["options"]:
                self._callbacks.pop(row["id"], None)
        self.publish()

    def clear_menus(self):
        self.menus.clear()
        self._callbacks.clear()

    @Slot(str)
    def setDraft(self, text):
        if self.menus and self.menus[-1]["input"]:
            self.menus[-1]["draft"] = text

    @Slot(str)
    @interaction
    def submit(self, text):
        if not self.menus or not self.menus[-1].get("submit"):
            return
        self.feedback("accept")
        menu = self.menus[-1]
        def complete():
            menu["submit"](text)
            if menu in self.menus:
                self.menus.remove(menu)
                for row in menu["options"]:
                    self._callbacks.pop(row["id"], None)
            self.error = ""
            self.publish()
        self.attempt(complete)

    @Slot(int)
    def choose(self, index):
        if self.menus:
            menu = self.menus[-1]
            if 0 <= index < len(menu["options"]) and not menu["options"][index]["disabled"]:
                menu["index"] = index
                self.dispatch("accept")

    @Slot(str)
    @interaction
    def select(self, identifier):
        self._view_rows()
        if identifier in self._card_model.by_id:
            if identifier != self.selected:
                self.feedback("navigate")
            self.selected = identifier
            self.publish()

    @Slot(int)
    def setColumns(self, columns):
        self.columns = max(1, columns)

    @Slot(int)
    @interaction
    def setTab(self, index):
        if not 0 <= index < len(self.tabs()):
            return
        if index != self.tab or self.page != "library" or self.folder:
            self.feedback("open")
        self.store.data["focus"][str(self.tab)] = self.selected
        self.tab, self.page, self.folder = index, "library", ""
        self.history.clear()
        self.selected = self.store.data["focus"].get(str(index), "")
        self.publish()

    def enter(self, page):
        self.feedback("open")
        self.history.append((self.page, self.tab, self.folder, self.selected))
        self.page = page

    def back(self):
        if self.history:
            self.page, self.tab, self.folder, self.selected = self.history.pop()
        else:
            self.desktop("Home")

    def activate(self, row):
        if row.get("kind") == "folder":
            self.enter("library")
            self.folder = row["id"][7:]
        else:
            self.open_item(row["id"])

    def open_item(self, identifier):
        pass

    @Slot(str)
    @interaction
    def dispatch(self, action):
        if composing_action_blocked(self, action):
            return
        self.error = ""
        if self.menus:
            menu = self.menus[-1]
            if action == "back":
                self.feedback("back")
                self.pop_menu()
            elif action == "accept":
                callback = self._callbacks.get(menu["options"][menu["index"]]["id"])
                if callback:
                    self.feedback("accept")
                    self.attempt(callback)
            elif action in ("up", "down") and not menu["input"]:
                direction = -1 if action == "up" else 1
                index = menu["index"]
                previous = index
                for _ in menu["options"]:
                    index = (index + direction) % len(menu["options"])
                    if not menu["options"][index]["disabled"]:
                        menu["index"] = index
                        break
                if menu["index"] != previous:
                    self.feedback("navigate")
            self.publish()
            return
        if action == "quick-settings":
            self.settings()
        elif action == "context":
            self.context()
        elif action == "back":
            self.feedback("back")
            self.attempt(self.back)
        elif action in ("previous-tab", "next-tab"):
            self.setTab((self.tab + (-1 if action == "previous-tab" else 1)) % len(self.tabs()))
        elif action == "accept":
            row = next((row for row in self._view_rows() if row["id"] == self.selected), None)
            if row:
                self.feedback("accept")
                self.attempt(lambda: self.activate(row))
            elif not self._view_rows():
                self.sources_menu() if self.library else self.command("address")
        elif action in ("up", "down", "left", "right"):
            rows = self._view_rows()
            index = max(0, self.selectedIndex)
            if rows:
                previous = self.selected
                self.selected = rows[move_index(index, action, len(rows),
                                               1 if self.page == "album" else self.columns)]["id"]
                if self.selected != previous:
                    self.feedback("navigate")
        self.publish()

    def context(self):
        self.menu(tr(Msg.LIBRARY_ACTIONS), [
            (tr(Msg.SEARCH), lambda: self.prompt(tr(Msg.SEARCH_LIBRARY), self.search, self.filter)),
            (tr(Msg.CLEAR_SEARCH), lambda: self.search("")),
            (tr(Msg.SOURCES), self.sources_menu),
            (tr(Msg.REFRESH_LIBRARY), self.refresh)])

    def search(self, text):
        self.filter = text
        self.clear_menus()
        self.publish()

    def refresh(self):
        self.clear_menus()
        self.library.refresh()

    def sources_menu(self):
        options = [(tr(Msg.ADD_FOLDER), lambda: self.prompt(
            tr(Msg.FOLDER_PATH), self.library.add, str(Path.home()), tr(Msg.FILES_STAY_IN_THEIR_ORIGINAL_LOCATION)), "", "folder-new")]
        for source in self.library.sources:
            options.append((Path(source.path).name, lambda s=source: self.prompt(
                tr(Msg.RECONNECT_SOURCE), lambda p: self.library.add(p), s.path),
                tr(Msg.CONNECTED) if source.available() else tr(Msg.DISCONNECTED)))
        options.extend([(tr(Msg.REFRESH_LIBRARY), self.refresh, "", "view-refresh"),
                        (tr(Msg.CANCEL_SCAN), self.cancel_scan, "", "process-stop")])
        self.menu(tr(Msg.SOURCES), options, icon="folder")

    def cancel_scan(self):
        self.library.cancel.set()
        self.library.generation += 1
        self.library.pending.clear()
        self.pop_menu()

    def settings_options(self):
        return []

    def settings(self):
        options = self.settings_options()
        if self.library:
            options.append((tr(Msg.SOURCES), self.sources_menu, "", "folder"))
        options.append((tr(Msg.CLOSE_APPLICATION), self.requestClose, "", "window-close"))
        self.menu(tr(Msg.SETTINGS), options, icon="preferences-system")

    def language_menu(self):
        self.menu(tr(Msg.LANGUAGE), [("English", lambda: self.set_language("en")),
                                   ("简体中文", lambda: self.set_language("zh_CN"))])

    def set_language(self, language):
        config = ConfigStore(self.config_path)
        config.data["preferences"]["language"] = language_code(language)
        config.save()
        self.language = language
        if self.menus and self.menus[-1]["title"] == tr(Msg.LANGUAGE):
            self.pop_menu()
        else:
            self.publish()

    def source_lost(self, source_id):
        while any(m["owner"] == source_id for m in self.menus):
            self.pop_menu()
        if self.current and self.current.get("sourceId") == source_id:
            self.stop_source()
            self.page = "library"
            self.history.clear()
        self.notice = tr(Msg.SOURCE_DISCONNECTED_RECONNECT_IT_IN_SOURCES)
        self.publish()

    def stop_source(self):
        pass

    def desktop(self, method):
        message = QDBusMessage.createMethodCall("io.github.zhubby.uDeck", "/io/github/zhubby/uDeck",
                                                 "io.github.zhubby.uDeck.Control", method)
        if not self.isolated:
            QDBusConnection.sessionBus().asyncCall(message)
        if method == "Home" and self.window:
            self.window.showMinimized()

    @Slot(str)
    @interaction
    def command(self, command):
        handlers = {"settings": self.settings, "sources": self.sources_menu,
                    "search": lambda: self.prompt(tr(Msg.SEARCH_LIBRARY), self.search, self.filter),
                    "refresh": self.refresh, "context": self.context, "home": lambda: self.desktop("Home")}
        if command in handlers:
            self.feedback("accept")
            self.attempt(handlers[command])
        self.publish()

    @Slot()
    def requestClose(self):
        self.attempt(self.persist)
        self.closed.emit()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.poller.stop()
        if self.inputs:
            self.inputs.close()
        if self.library:
            self.library.close()
        self.attempt(self.persist)
        self.attempt(self.store.close)
