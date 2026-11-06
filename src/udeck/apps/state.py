"""Atomic local state and the music queue, independent of engine lifetimes."""

import json
import os
import tempfile
from pathlib import Path


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class AppState:
    def __init__(self, app, directory=None):
        root = Path(directory) if directory else Path(os.environ.get(
            "XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "udeck/apps"
        self.path = root / (app + ".json")
        self.error = ""
        self.data = {"version": 1, "sources": [], "positions": {}, "favorites": [],
                     "recent": [], "bookmarks": {}, "preferences": {}, "focus": {},
                     "history": [], "tabs": [], "queue": [], "index": []}
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict) or loaded.get("version") != 1:
                raise ValueError("Unsupported state version")
            for key, default in self.data.items():
                if key in loaded and type(loaded[key]) is type(default):
                    self.data[key] = loaded[key]
        except FileNotFoundError:
            pass
        except (ValueError, OSError) as error:
            self.error = str(error)

    def save(self):
        # Preserve corrupt input for recovery before the first successful write.
        if self.error and self.path.exists():
            recovery = self.path.with_suffix(".recovery.json")
            if not recovery.exists():
                recovery.write_bytes(self.path.read_bytes())
        atomic_json(self.path, self.data)
        self.error = ""

    def remember(self, identifier):
        self.data["recent"] = [identifier] + [x for x in self.data["recent"] if x != identifier][:99]


class PlayQueue:
    def __init__(self):
        self.items = []
        self.current = None
        self.cursor = -1
        self.repeat = "off"
        self.shuffle = False

    def replace(self, items, current):
        self.items = list(items)
        self.current = current
        self.cursor = self.items.index(current) if current in self.items else -1

    def append(self, items):
        self.items.extend(items)

    def remove(self, identifier):
        if identifier not in self.items:
            return
        index = self.items.index(identifier)
        self.items.pop(index)
        if index <= self.cursor:
            self.cursor -= 1

    def move(self, identifier, delta):
        if identifier not in self.items:
            return
        index = self.items.index(identifier)
        target = max(0, min(len(self.items) - 1, index + delta))
        self.items.insert(target, self.items.pop(index))
        if self.current in self.items:
            self.cursor = self.items.index(self.current)

    def advance(self, delta=1):
        if self.repeat == "one" and delta == 1 and self.current in self.items:
            return self.current
        if self.shuffle and len(self.items) > 1:
            import random

            choices = [i for i, item in enumerate(self.items) if item != self.current]
            self.cursor = random.choice(choices) if choices else 0
        else:
            self.cursor += delta
            if self.repeat == "all" and self.items:
                self.cursor %= len(self.items)
        if 0 <= self.cursor < len(self.items):
            self.current = self.items[self.cursor]
        else:
            self.current = None
        return self.current
