import json
import os
import tempfile
from pathlib import Path

PAGES = ("home", "apps", "windows", "files", "settings")
PAGE_NAMES = ("主页", "应用", "运行中", "文件", "设置")


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
        if page not in PAGES:
            raise ValueError("未知页面")
        self.positions[self.page] = self.index
        self.page = page
        self.index = max(0, int(self.positions.get(page, 0)))

    def select(self, index):
        self.index = max(0, index)
        self.positions[self.page] = self.index
        self.zone = "content"

    def move(self, direction, count, columns=1):
        if self.zone == "tabs":
            if direction == "down":
                self.zone = "content"
            elif direction in ("left", "right"):
                tab_index = PAGES.index(self.page)
                offset = -1 if direction == "left" else 1
                self.set_page(PAGES[max(0, min(tab_index + offset, len(PAGES) - 1))])
            return
        if direction == "up" and self.index < columns:
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
        self.data = {"version": 1, "favorites": [], "recent": [], "focus": {}, "input": {},
                     "preferences": {"showHidden": False, "category": "All"}}
        try:
            loaded = json.loads(self.path.read_text())
            if isinstance(loaded, dict):
                for field in ("favorites", "recent"):
                    values = loaded.get(field)
                    if isinstance(values, list):
                        self.data[field] = list(dict.fromkeys(
                            value for value in values if isinstance(value, str)
                        ))[:100]
                for field in ("focus", "input"):
                    if isinstance(loaded.get(field), dict):
                        self.data[field] = loaded[field]
                self.data["focus"] = {
                    key: value for key, value in self.data["focus"].items()
                    if key in PAGES and type(value) is int and 0 <= value < 100000
                }
                preferences = loaded.get("preferences", {})
                if isinstance(preferences, dict):
                    if type(preferences.get("showHidden")) is bool:
                        self.data["preferences"]["showHidden"] = preferences["showHidden"]
                    if isinstance(preferences.get("category"), str):
                        self.data["preferences"]["category"] = preferences["category"]
        except (OSError, ValueError, TypeError):
            pass

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=".settings-", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w") as stream:
                json.dump(self.data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
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
