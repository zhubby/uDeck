import json
import os
import tempfile
from pathlib import Path

from .appearance import theme_code
from .i18n import language_code, tr

PAGES = ("home", "apps", "windows", "files")
ALL_PAGES = (*PAGES, "settings")
PAGE_NAMES = (tr('主页'), tr('应用'), tr('运行中'), tr('文件'))


def move_index(index, direction, count, columns=1):
    if count <= 0:
        return -1
    index = max(0, min(index, count - 1))
    if direction == "left" and index % columns:
        return index - 1
    if direction == "right" and index % columns < columns - 1:
        return min(index + 1, count - 1)
    if direction == "up":
        return max(index % columns, index - columns)
    if direction == "down" and index // columns < (count - 1) // columns:
        return min(index + columns, count - 1)
    return index


class Navigation:
    def __init__(self, saved=None):
        self.page = "home"
        self.zone = "content"
        self.positions = dict(saved or {})
        self.index = int(self.positions.get(self.page, 0))
        self.modal_owners = []

    def set_page(self, page):
        if page not in ALL_PAGES:
            raise ValueError(tr('未知页面'))
        self.positions[self.page] = self.index
        self.page = page
        self.index = max(0, int(self.positions.get(page, 0)))

    @property
    def tab_page(self):
        return self.page if self.page in PAGES else "home"

    def select(self, index):
        self.index = max(0, index)
        self.positions[self.page] = self.index
        self.zone = "content"

    def move(self, direction, count, columns=1):
        if self.zone == "tabs":
            if direction == "down":
                self.zone = "content"
            elif direction in ("left", "right"):
                tab_index = PAGES.index(self.tab_page)
                offset = -1 if direction == "left" else 1
                self.set_page(PAGES[max(0, min(tab_index + offset, len(PAGES) - 1))])
            return
        if direction == "up" and self.index < columns:
            if self.page not in PAGES:
                self.set_page(self.tab_page)
            self.zone = "tabs"
        else:
            self.index = move_index(self.index, direction, count, columns)
            self.positions[self.page] = self.index

    def open_modal(self):
        self.modal_owners.append((self.page, self.zone, self.index))

    def close_modal(self):
        if self.modal_owners:
            self.page, self.zone, self.index = self.modal_owners.pop()


class ConfigStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(
            os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        ) / "udeck/settings.json"
        self.data = {"version": 1, "favorites": [], "recent": [], "focus": {}, "input": {}, "applicationInput": {},
                     "fileManager": {"bookmarks": [], "sort": "name", "descending": False, "kind": "all"},
                     "preferences": {"showHidden": False, "category": "All", "language": "en", "theme": "classic", "uiSounds": True}}
        try:
            loaded = json.loads(self.path.read_text())
            if isinstance(loaded, dict):
                manager = loaded.get("fileManager", {})
                if isinstance(manager, dict):
                    bookmarks = manager.get("bookmarks", [])
                    if isinstance(bookmarks, list):
                        self.data["fileManager"]["bookmarks"] = list(dict.fromkeys(
                            path for path in bookmarks if isinstance(path, str) and 0 < len(path) <= 4096
                            and "\x00" not in path and Path(path).is_absolute()))[:64]
                    if manager.get("sort") in ("name", "modified", "size"):
                        self.data["fileManager"]["sort"] = manager["sort"]
                    if type(manager.get("descending")) is bool:
                        self.data["fileManager"]["descending"] = manager["descending"]
                    if manager.get("kind") in ("all", "audio", "video", "image", "book", "text", "archive", "other"):
                        self.data["fileManager"]["kind"] = manager["kind"]
                for field in ("favorites", "recent"):
                    values = loaded.get(field)
                    if isinstance(values, list):
                        self.data[field] = list(dict.fromkeys(
                            value for value in values if isinstance(value, str)
                        ))[:100]
                for field in ("focus", "input"):
                    if isinstance(loaded.get(field), dict):
                        self.data[field] = loaded[field]
                modes = loaded.get("applicationInput", {})
                if isinstance(modes, dict):
                    self.data["applicationInput"] = {key: mode for key, mode in modes.items()
                                                     if isinstance(key, str) and 0 < len(key) <= 256
                                                     and mode in ("keyboard", "pointer", "native")}
                self.data["focus"] = {
                    key: value for key, value in self.data["focus"].items()
                    if key in ALL_PAGES and type(value) is int and 0 <= value < 100000
                }
                preferences = loaded.get("preferences", {})
                if isinstance(preferences, dict):
                    self.data["preferences"]["language"] = language_code(preferences.get("language"))
                    self.data["preferences"]["theme"] = theme_code(preferences.get("theme"))
                    if type(preferences.get("showHidden")) is bool:
                        self.data["preferences"]["showHidden"] = preferences["showHidden"]
                    if type(preferences.get("uiSounds")) is bool:
                        self.data["preferences"]["uiSounds"] = preferences["uiSounds"]
                    if isinstance(preferences.get("category"), str):
                        self.data["preferences"]["category"] = preferences["category"]
        except (OSError, ValueError, TypeError):
            pass
        self._saved_preferences = dict(self.data["preferences"])
        self._saved_file_manager = {**self.data["fileManager"], "bookmarks": list(self.data["fileManager"]["bookmarks"])}

    def save(self):
        # Apps also update shared preferences. A cached shell store must not
        # overwrite their language/theme when saving focus or favorites.
        latest_store = ConfigStore(self.path)
        latest = latest_store.data["preferences"]
        if self.data["fileManager"] == self._saved_file_manager:
            self.data["fileManager"] = latest_store.data["fileManager"]
        preferences = dict(self.data["preferences"])
        for field in ("language", "theme", "uiSounds"):
            if preferences[field] == self._saved_preferences[field]:
                preferences[field] = latest[field]
        values = {**self.data, "preferences": preferences}
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=".settings-", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w") as stream:
                json.dump(values, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            self.data["preferences"] = preferences
            self._saved_preferences = dict(preferences)
            self._saved_file_manager = {**self.data["fileManager"], "bookmarks": list(self.data["fileManager"]["bookmarks"])}
        finally:
            Path(temporary).unlink(missing_ok=True)

    def favorite(self, identifier, enabled):
        favorites = self.data["favorites"]
        if enabled and identifier not in favorites:
            favorites.append(identifier)
        elif not enabled and identifier in favorites:
            favorites.remove(identifier)
        self.save()

    def remember(self, identifier):
        self.data["recent"] = [identifier] + [
            value for value in self.data["recent"] if value != identifier
        ][:19]
        self.save()
