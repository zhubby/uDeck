"""Bounded background indexing and mount ownership; no files are moved."""

import hashlib
import json
import os
import shutil
import subprocess
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from udeck.i18n import error_text, tr

EXTENSIONS = {
    "music": {".mp3", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".wav", ".aiff"},
    "video": {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".ts"},
    "reader": {".txt", ".pdf", ".epub"},
    "emulator": {".gb", ".gbc", ".gba", ".sfc", ".smc", ".nes", ".cue", ".chd", ".pbp"},
}
DEFAULT_FOLDERS = {"music": "Music", "video": "Video", "reader": "Books"}
PLATFORMS = {".gb": "GB", ".gbc": "GB", ".gba": "GBA", ".sfc": "SNES",
             ".smc": "SNES", ".nes": "NES", ".cue": "PS1", ".chd": "PS1", ".pbp": "PS1"}


@dataclass
class Source:
    id: str
    path: str
    device: int
    inode: int

    @classmethod
    def create(cls, path, identifier=None):
        path = Path(path).expanduser().resolve(strict=True)
        if not path.is_dir():
            raise ValueError(tr("Choose a folder"))
        stat = path.stat()
        # The saved identity survives remounts; dev/inode are revalidated on reconnect.
        identifier = identifier or hashlib.sha256(
            f"{path}:{stat.st_dev}:{stat.st_ino}".encode()).hexdigest()[:24]
        return cls(identifier, str(path), stat.st_dev, stat.st_ino)

    def available(self):
        try:
            stat = Path(self.path).stat()
            return (stat.st_dev, stat.st_ino) == (self.device, self.inode)
        except OSError:
            return False

    def to_dict(self):
        return asdict(self)


def fingerprint(path, cancelled=lambda: False):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            if cancelled():
                raise OSError(tr("Scan cancelled"))
            digest.update(chunk)
    return digest.hexdigest()


def probe(path):
    if not shutil.which("ffprobe"):
        return {}
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_chapters",
                                 "-of", "json", str(path)], capture_output=True, timeout=8)
        return json.loads(result.stdout) if result.returncode == 0 else {}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {}


def scan(source, app, cancelled=lambda: False, metadata=False, cache=None):
    items = []
    cache = cache or {}
    root = Path(source.path)
    if not source.available():
        raise OSError(tr("Source disconnected"))
    for directory, folders, files in os.walk(root, followlinks=False):
        folders[:] = sorted(x for x in folders if not x.startswith(".")
                            and not (Path(directory) / x).is_symlink())
        for name in sorted(files):
            if cancelled():
                return []
            path = Path(directory) / name
            if path.suffix.lower() not in EXTENSIONS[app] or path.is_symlink():
                continue
            try:
                relative = str(path.relative_to(root))
                stat = path.stat()
                cached = cache.get(str(path), {})
                unchanged = cached.get("stamp") == [stat.st_size, stat.st_mtime_ns]
                digest = cached["fingerprint"] if unchanged else fingerprint(path, cancelled)
                identifier = hashlib.sha256(f"{source.id}/{relative}/{digest}".encode()).hexdigest()
                info = cached.get("metadata", {}) if unchanged else {}
                if metadata and app in ("music", "video") and not info:
                    info = probe(path)
                tags = {k.lower(): v for k, v in info.get("format", {}).get("tags", {}).items()}
                cover = next((p for p in (path.with_suffix(".jpg"), path.with_suffix(".png"),
                             path.parent / "cover.jpg", path.parent / "folder.jpg") if p.is_file() and not p.is_symlink()), None)
                items.append({"id": identifier, "sourceId": source.id, "path": str(path),
                              "relative": relative, "fingerprint": digest,
                              "stamp": [stat.st_size, stat.st_mtime_ns], "metadata": info,
                              "title": tags.get("title") or path.stem, "artist": tags.get("artist", ""),
                              "album": tags.get("album") or path.parent.name,
                              "folder": str(path.parent), "format": path.suffix[1:].upper(),
                              "platform": PLATFORMS.get(path.suffix.lower(), ""),
                              "cover": cover.as_uri() if cover else "",
                              "duration": float(info.get("format", {}).get("duration", 0) or 0)})
            except (OSError, ValueError):
                continue
            if len(items) >= 20000:
                return items
    if not source.available():
        raise OSError(tr("Source disconnected"))
    return sorted(items, key=lambda x: (x["album"].casefold(), x["relative"].casefold()))


class ScanSignals(QObject):
    done = Signal(int, str, list, object)


class ScanTask(QRunnable):
    def __init__(self, generation, source, app, cancel, cache):
        super().__init__()
        self.generation, self.source, self.app = generation, source, app
        self.cancel, self.cache = cancel, cache
        self.signals = ScanSignals()

    def run(self):
        try:
            items, error = scan(self.source, self.app, self.cancel.is_set, True, self.cache), ""
        except (OSError, ValueError) as exception:
            items, error = [], error_text(exception)
        self.signals.done.emit(self.generation, self.source.id, items, error)


class Library(QObject):
    changed = Signal()
    lost = Signal(str)

    def __init__(self, app, state, parent=None):
        super().__init__(parent)
        self.app, self.state = app, state
        self.sources = []
        for value in state.data["sources"]:
            try:
                self.sources.append(Source(**value))
            except (TypeError, ValueError):
                continue
        self.items = state.data.get("index", [])
        if not isinstance(self.items, list):
            self.items = []
        self.generation, self.pending = 0, set()
        self.errors = {}
        self.cancel = threading.Event()
        self.tasks = []
        self.unavailable = set()

    def add(self, path):
        existing = next((s for s in self.sources if s.path == str(Path(path).expanduser().resolve())), None)
        source = Source.create(path, existing.id if existing else None)
        if existing:
            self.sources.remove(existing)
        self.sources.append(source)
        self.state.data["sources"] = [s.to_dict() for s in self.sources]
        self.state.save()
        self.refresh()

    def refresh(self):
        self.cancel.set()
        self.cancel = threading.Event()
        self.generation += 1
        self.pending.clear()
        self.errors.pop("default-source", None)
        if not self.sources and self.app in DEFAULT_FOLDERS:
            try:
                source = Source.create(Path.home() / DEFAULT_FOLDERS[self.app])
            except FileNotFoundError:
                pass
            except (OSError, ValueError) as error:
                self.errors["default-source"] = error_text(error)
            else:
                self.sources.append(source)
                self.state.data["sources"] = [source.to_dict()]
        self.check_sources()
        cache = {item["path"]: item for item in self.items}
        for source in self.sources:
            if not source.available():
                continue
            self.pending.add(source.id)
            task = ScanTask(self.generation, source, self.app, self.cancel, cache)
            task.signals.done.connect(self._done)
            self.tasks.append(task)
            QThreadPool.globalInstance().start(task)
        self.changed.emit()

    def _done(self, generation, source_id, items, error):
        self.tasks = [t for t in self.tasks if not (t.generation == generation and t.source.id == source_id)]
        if generation != self.generation or source_id in self.unavailable:
            return
        self.pending.discard(source_id)
        self.errors[source_id] = error
        if not error:
            self.items = [i for i in self.items if i["sourceId"] != source_id] + items
        self.state.set_index(self.items)
        try:
            self.state.save()
        except OSError as exception:
            self.errors[source_id] = error_text(exception)
        self.changed.emit()

    def check_sources(self):
        for source in self.sources:
            if not source.available() and source.id not in self.unavailable:
                self.unavailable.add(source.id)
                self.pending.discard(source.id)
                self.lost.emit(source.id)
            elif source.available() and source.id in self.unavailable:
                self.unavailable.remove(source.id)
                self.changed.emit()

    def require(self, identifier):
        item = next((i for i in self.items if i["id"] == identifier), None)
        source = next((s for s in self.sources if item and s.id == item["sourceId"]), None)
        if not item or not source or not source.available() or not Path(item["path"]).is_file():
            raise OSError(tr("Source disconnected. Reconnect the folder in Sources."))
        stat = Path(item["path"]).stat()
        if [stat.st_size, stat.st_mtime_ns] != item["stamp"] or Path(item["path"]).is_symlink():
            raise OSError(tr("The file has changed. Refresh the library before opening it."))
        return item

    def close(self):
        self.cancel.set()
        self.generation += 1
