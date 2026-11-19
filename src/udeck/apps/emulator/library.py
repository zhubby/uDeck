"""
[INPUT]: 依赖共享 Library、Libretro 列表和单轮封面目录索引。
[OUTPUT]: 提供后台列表与封面解析、扫描代次和封面修订隔离。
[POS]: Emulator 游戏库；工作线程构造独占结果，Qt 线程发布。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import copy
import hashlib
import os
import re
import shlex
import threading
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from udeck.apps.common.library import Library, ScanSignals, Source, fingerprint
from udeck.i18n import Msg, error_text, tr

DESCRIPTORS = {".cue", ".gdi", ".m3u"}


def confined_path(path, root):
    """Check every component, including symlinks pointing back inside the root."""
    root = Path(root).absolute()
    path = Path(path)
    path = path if path.is_absolute() else Path.cwd() / path
    try:
        relative = path.relative_to(root)
    except ValueError:
        raise ValueError(tr(Msg.CONTENT_REFERENCE_LEAVES_ITS_PLATFORM_FOLDER_PATH, path=path)) from None
    current = root
    for part in relative.parts:
        if part == "..":
            current = current.parent
            if current != root and root not in current.parents:
                raise ValueError(tr(Msg.CONTENT_REFERENCE_LEAVES_ITS_PLATFORM_FOLDER_PATH, path=path))
            continue
        current = current / part
        if current.is_symlink():
            raise ValueError(tr(Msg.CONTENT_REFERENCE_USES_A_SYMBOLIC_LINK_PATH, path=current))
    if root.is_symlink():
        raise ValueError(tr(Msg.CONTENT_REFERENCE_USES_A_SYMBOLIC_LINK_PATH, path=root))
    return current


def content_dependencies(path, root, cancelled=lambda: False):
    references, referenced, visiting, visited = [], set(), set(), set()
    edges, descriptor_bytes = 0, 0

    def visit(entry, depth=0):
        nonlocal edges, descriptor_bytes
        if cancelled():
            raise OSError(tr(Msg.SCAN_CANCELLED))
        entry = confined_path(entry, root)
        if entry in visiting or depth > 8:
            raise ValueError(tr(Msg.CIRCULAR_OR_DEEPLY_NESTED_DISC_PLAYLIST))
        if entry in visited:
            return
        if entry.suffix.lower() not in DESCRIPTORS or not entry.is_file():
            visited.add(entry)
            return
        size = entry.stat().st_size
        descriptor_bytes += size
        if size > 2 * 1024 * 1024 or descriptor_bytes > 8 * 1024 * 1024:
            raise ValueError(tr(Msg.DISC_DESCRIPTOR_IS_TOO_LARGE))
        text = entry.read_text(encoding="utf-8-sig", errors="replace")
        suffix = entry.suffix.lower()
        if suffix == ".cue":
            names = [a or b for a, b in re.findall(r'^\s*FILE\s+(?:"([^"\n]+)"|(\S+))\s+', text, re.M | re.I)]
        elif suffix == ".m3u":
            names = [line.strip().strip('"') for line in text.splitlines()
                     if line.strip() and not line.lstrip().startswith("#")]
        else:
            lines = [line for line in text.splitlines() if line.strip()]
            try:
                count = int(lines[0].strip())
                names = [shlex.split(line)[4] for line in lines[1:]]
                if len(names) != count:
                    raise ValueError("Track count mismatch")
            except (IndexError, ValueError):
                raise ValueError(tr(Msg.INVALID_GDI_DESCRIPTOR)) from None
        if not names:
            raise ValueError(tr(Msg.DISC_DESCRIPTOR_CONTAINS_NO_ENTRIES))
        visiting.add(entry)
        for name in names:
            if cancelled():
                raise OSError(tr(Msg.SCAN_CANCELLED))
            edges += 1
            if edges > 8192:
                raise ValueError(tr(Msg.TOO_MANY_DISC_REFERENCES))
            name = name.replace("\\", "/")
            if Path(name).is_absolute() or re.match(r"^[A-Za-z]:", name):
                raise ValueError(tr(Msg.CONTENT_REFERENCE_LEAVES_ITS_PLATFORM_FOLDER_PATH, path=name))
            target = confined_path(entry.parent / name, root)
            if target not in referenced:
                if len(references) >= 512:
                    raise ValueError(tr(Msg.TOO_MANY_DISC_REFERENCES))
                referenced.add(target)
                references.append(target)
            visit(target, depth + 1)
        visiting.remove(entry)
        visited.add(entry)

    visit(Path(path))
    return references


@dataclass
class GameScan:
    items: list = field(default_factory=list)
    hints: list = field(default_factory=list)


def scan_games(source, catalog, cancelled=lambda: False, cache=None, *, enabled_only=True):
    result = GameScan()
    cache = cache or {}
    root = Path(source.path)
    if not source.available():
        raise OSError(tr(Msg.SOURCE_DISCONNECTED))
    confined_path(root, root)
    manual = set(catalog.preferences.get("engineEntries", []))
    for directory in sorted(root.iterdir()):
        if cancelled():
            return GameScan()
        if directory.name.startswith("."):
            continue
        platform = catalog.platform_for_directory(directory.name)
        if directory.is_symlink() or not directory.is_dir() or not platform:
            if len(result.hints) < 20:
                result.hints.append(tr(Msg.NOT_SCANNED_NAME_USE_A_PLATFORM_FOLDER, name=directory.name))
            continue
        candidates = catalog.candidates(platform.id, enabled_only=enabled_only)
        if not candidates:
            if len(result.hints) < 20:
                result.hints.append(tr(Msg.ENABLE_A_CORE_FOR_PLATFORM, platform=platform.title))
            continue
        files = []
        for folder, folders, names in os.walk(directory, followlinks=False):
            folders[:] = sorted(n for n in folders if not n.startswith(".") and not (Path(folder) / n).is_symlink())
            for name in sorted(names):
                if cancelled():
                    return GameScan()
                path = Path(folder) / name
                if name.startswith(".") or path.is_symlink() or not path.is_file():
                    continue
                suffix = path.suffix.lower()
                if not any(c.supports(suffix) for c in candidates):
                    continue
                if platform.mode == "scummvm" and suffix != ".scummvm":
                    continue
                if platform.mode == "dos" and suffix not in {".dosz", ".zip", ".7z", ".conf", ".dosbox"} and str(path) not in manual:
                    continue
                if platform.mode == "manual" and str(path) not in manual:
                    continue
                files.append(path)
                if len(files) >= 30000:
                    break
            if len(files) >= 30000:
                break
        referenced, dependencies, errors = set(), {}, {}
        for path in files:
            if cancelled():
                return GameScan()
            if path.suffix.lower() in DESCRIPTORS:
                try:
                    dependencies[path] = content_dependencies(path, directory, cancelled)
                    referenced.update(dependencies[path])
                except (OSError, ValueError) as error:
                    errors[path] = error_text(error)
        for path in files:
            if cancelled():
                return GameScan()
            if path in referenced:
                continue
            try:
                relative = str(path.relative_to(root))
                stat = path.stat()
                stamp = [stat.st_size, stat.st_mtime_ns]
                old = cache.get(str(path), {})
                digest = old["fingerprint"] if old.get("stamp") == stamp else fingerprint(path, cancelled)
                identifier = hashlib.sha256(f"{source.id}/{relative}/{digest}".encode()).hexdigest()
                cover = next((p for p in (path.with_suffix(".jpg"), path.with_suffix(".png"),
                             path.parent / "cover.jpg") if p.is_file() and not p.is_symlink()), None)
                result.items.append({"id": identifier, "sourceId": source.id, "path": str(path),
                    "relative": relative, "fingerprint": digest, "stamp": stamp, "metadata": {},
                    "title": path.stem, "artist": "", "album": path.parent.name, "folder": str(path.parent),
                    "format": path.suffix[1:].upper(), "platform": platform.id,
                    "platformRoot": str(directory), "dependencies": [str(p) for p in dependencies.get(path, [])],
                    "contentError": errors.get(path, ""), "cover": cover.as_uri() if cover else "", "duration": 0})
            except (OSError, ValueError):
                continue
            if len(result.items) >= 20000:
                result.hints.append(tr(Msg.LIBRARY_LIMIT_REACHED_USE_A_SMALLER_ROM_ROOT))
                return result
    if cancelled():
        return GameScan()
    if not source.available():
        raise OSError(tr(Msg.SOURCE_DISCONNECTED))
    result.items.sort(key=lambda i: (i["platform"], i["relative"].casefold()))
    return result


class GameScanTask(QRunnable):
    def __init__(self, generation, source, catalog, cancel, cache):
        super().__init__()
        self.generation, self.source, self.catalog = generation, source, catalog
        self.cancel, self.cache = cancel, cache
        self.signals = ScanSignals()

    def run(self):
        report = {"error": "", "hints": []}
        try:
            result = scan_games(self.source, self.catalog, self.cancel.is_set, self.cache)
            items, report["hints"] = result.items, result.hints
        except (OSError, ValueError) as error:
            items, report["error"] = [], error_text(error)
        self.signals.done.emit(self.generation, self.source.id, items, report)


class PlaylistReadSignals(QObject):
    done = Signal(int, object, object)


class PlaylistReadTask(QRunnable):
    def __init__(self, generation, directory, root, catalog, identities, cache, cancel,
                 previous, thumbnail_path, preferred, thumbnail_revision):
        super().__init__()
        self.generation, self.directory, self.root = generation, directory, root
        self.catalog, self.identities, self.cache, self.cancel = catalog, identities, cache, cancel
        self.previous, self.thumbnail_path, self.preferred = previous, thumbnail_path, preferred
        self.thumbnail_revision = thumbnail_revision
        self.signals = PlaylistReadSignals()

    def run(self):
        from .playlists import read_library
        from .thumbnails import apply_library_thumbnails

        try:
            result = read_library(self.directory, self.root, self.catalog, self.identities,
                                  self.cancel.is_set, self.cache)
            for playlist in result.playlists:
                if playlist['error']:
                    kept = [item for item in self.previous if item.get('playlistPath') == playlist['path']]
                    result.items.extend(kept)
                    playlist['count'] = len(kept)
            apply_library_thumbnails(result.items, self.thumbnail_path, self.preferred,
                                     cancelled=self.cancel.is_set)
            if self.cancel.is_set():
                raise OSError(tr(Msg.SCAN_CANCELLED))
            self.signals.done.emit(self.generation, (result, self.identities, self.thumbnail_revision), None)
        except (OSError, ValueError) as error:
            self.signals.done.emit(self.generation, None, error_text(error))


class EmulatorLibrary(Library):
    def __init__(self, state, catalog, parent=None):
        super().__init__("emulator", state, parent)
        self.catalog, self.reports, self.playlists = catalog, {}, []
        self.suspended = False
        self.thumbnail_revision = 0
        self.reload_configuration()

    def reload_configuration(self):
        from udeck.apps.common.state import atomic_json

        from .playlists import ContentIdentities

        self.cancel.set()
        self.generation += 1
        self.pending.clear()
        self.errors.clear()
        self.unavailable.clear()
        self.playlists, self.reports = [], {}
        self.items = self.state.data.get("index", [])
        self.sources = []
        for value in self.state.data["sources"]:
            try:
                self.sources.append(Source(**value))
            except (TypeError, ValueError):
                continue
        prefs = self.state.data["preferences"]
        self.root_id = prefs.get("romSourceId", "")
        self.root_path = str(Path(prefs.get("romRoot", str(Path.home() / "Games/roms"))).expanduser())
        self.playlist_path = str(Path(prefs.get("playlistDirectory", str(Path.home() / "Games/playlists"))).expanduser())
        self.thumbnail_path = str(Path(prefs.get("thumbnailDirectory", str(Path.home() / "Games/thumbnails"))).expanduser())
        self.legacy_path = self.state.path.parent / "emulator-legacy-library.json"
        self.legacy_root = prefs.get("romRoot", "") if prefs.get("emulatorSchema") == 2 else ""
        if self.legacy_root and not self.legacy_path.exists():
            atomic_json(self.legacy_path, {"root": self.legacy_root, "items": self.items})
        self.identity_error = ""
        try:
            self.identities = ContentIdentities(self.state.path.parent / "emulator-identities.json")
        except (OSError, ValueError) as error:
            self.identities = None
            self.identity_error = error_text(error)
            self.errors["identities"] = self.identity_error
        if self.identities is not None:
            for item in self.items:
                if item.get("path") and item.get("id"):
                    self.identities.register(item["path"], item.get("archiveMember", ""), item["id"])
        if Path(self.root_path).is_dir():
            self._attach_root(self.root_path, reconnect=False)

    def _attach_root(self, path, reconnect=True):
        path = str(Path(path).expanduser().resolve(strict=True))
        existing = next((s for s in self.sources if s.path == path), None)
        source = Source.create(path, existing.id if existing else None) if reconnect or not existing else existing
        if existing:
            self.sources.remove(existing)
        self.sources.append(source)
        self.root_id, self.root_path = source.id, source.path
        prefs = self.state.data["preferences"]
        prefs.update(romRoot=source.path, romSourceId=source.id)
        if not self.legacy_root:
            prefs["emulatorSchema"] = 3
        self.state.data["sources"] = [s.to_dict() for s in self.sources]

    def configure_root(self, path):
        source = Source.create(path)
        with os.scandir(source.path) as entries:
            next(entries, None)
        previous = (self.root_path, self.root_id, list(self.sources),
                    copy.deepcopy(self.state.data["preferences"]), self.state.data["sources"])
        try:
            self._attach_root(source.path)
            self.state.save()
        except OSError:
            self.root_path, self.root_id, self.sources, preferences, sources = previous
            self.state.data["preferences"].clear()
            self.state.data["preferences"].update(preferences)
            self.state.data["sources"] = sources
            raise
        self.refresh()

    def configure_directory(self, key, path):
        source = Source.create(path)
        with os.scandir(source.path) as entries:
            next(entries, None)
        attribute = {"playlistDirectory": "playlist_path", "thumbnailDirectory": "thumbnail_path"}[key]
        previous = getattr(self, attribute)
        old = self.state.data["preferences"].get(key)
        try:
            self.state.data["preferences"][key] = source.path
            setattr(self, attribute, source.path)
            self.state.save()
        except OSError:
            setattr(self, attribute, previous)
            if old is None:
                self.state.data["preferences"].pop(key, None)
            else:
                self.state.data["preferences"][key] = old
            raise
        self.refresh()

    def refresh(self):
        if self.suspended:
            return
        if self.identity_error:
            self.errors["identities"] = self.identity_error
            self.changed.emit()
            return
        self.cancel.set()
        self.cancel = threading.Event()
        self.generation += 1
        self.pending = {"playlists"}
        self.check_sources()
        previous = [dict(item) for item in self.items]
        task = PlaylistReadTask(self.generation, self.playlist_path, self.root_path,
                                copy.deepcopy(self.catalog), copy.deepcopy(self.identities),
                                {i["path"]: i for i in previous}, self.cancel, previous,
                                self.thumbnail_path,
                                self.state.data['preferences'].get('thumbnailType', 'Named_Boxarts'),
                                self.thumbnail_revision)
        task.signals.done.connect(self._playlist_done)
        self.tasks.append(task)
        QThreadPool.globalInstance().start(task)
        self.changed.emit()

    def _playlist_done(self, generation, payload, error):
        self.tasks = [t for t in self.tasks if t.generation != generation]
        if generation != self.generation or self.suspended:
            return
        self.pending.discard("playlists")
        if error:
            self.errors["playlists"] = error
        else:
            result, identities, thumbnail_revision = payload
            if thumbnail_revision != self.thumbnail_revision:
                self.refresh()
                return
            from .thumbnails import preferred_cover

            self.items, self.playlists, self.identities = result.items, result.playlists, identities
            preferred = self.state.data['preferences'].get('thumbnailType', 'Named_Boxarts')
            for item in self.items:
                item["romRoot"] = self.root_path
                item['cover'] = preferred_cover(item.get('thumbnails', {}), preferred)
            existing = {s.path: s for s in self.sources}
            existing.update({s.path: s for s in result.sources})
            self.sources = list(existing.values())
            if Path(self.root_path).is_dir():
                self._attach_root(self.root_path, reconnect=False)
            self.state.data["sources"] = [s.to_dict() for s in self.sources]
            self.errors = dict(result.errors)
            self.reports[self.root_id] = list(result.errors.values())
            self.state.set_index(self.items)
            try:
                self.identities.save()
                self.state.save()
            except OSError as failure:
                self.errors["state"] = error_text(failure)
        self.changed.emit()

    def _done(self, generation, source_id, items, report):
        # Ignore any pre-playlist worker finishing after a configuration change.
        if generation == self.generation and source_id not in self.unavailable:
            self.reports[source_id] = report["hints"]
        super()._done(generation, source_id, items, report["error"])

    def entry(self, identifier):
        item = next((i for i in self.items if i.get("entryId") == identifier), None)
        item = item or next((i for i in self.items if i["id"] == identifier), None)
        if item is None:
            raise OSError(tr(Msg.SOURCE_DISCONNECTED_RECONNECT_THE_FOLDER_IN_SOURCES))
        return item

    def require(self, identifier):
        item = self.entry(identifier)
        source = next((s for s in self.sources if s.id == item["sourceId"]), None)
        path = Path(item["path"])
        if not source or not source.available() or not path.is_file():
            raise OSError(tr(Msg.SOURCE_DISCONNECTED_RECONNECT_THE_FOLDER_IN_SOURCES))
        confined_path(path, source.path)
        confined_path(path, item.get("platformRoot", path.parent))
        stat = path.stat()
        if [stat.st_size, stat.st_mtime_ns] != item["stamp"]:
            raise OSError(tr(Msg.THE_FILE_HAS_CHANGED_REFRESH_THE_LIBRARY_BEFORE_OPENING_IT))
        return item

    def reload_thumbnails(self, emit=True):
        from .thumbnails import apply_library_thumbnails

        self.thumbnail_revision += 1
        preferred = self.state.data["preferences"].get("thumbnailType", "Named_Boxarts")
        apply_library_thumbnails(self.items, self.thumbnail_path, preferred)
        if emit:
            self.changed.emit()


def create_platform_directories(root, catalog):
    root = Path(root).expanduser()
    if root.is_symlink():
        raise ValueError(tr(Msg.CHOOSE_A_FOLDER_WITHOUT_SYMBOLIC_LINKS))
    root.mkdir(parents=True, exist_ok=True)
    created = []
    for platform in catalog.platforms.values():
        if not catalog.candidates(platform.id):
            continue
        for database in platform.databases or (platform.directory,):
            path = root / database
            if path.is_symlink():
                raise ValueError(tr(Msg.CONTENT_REFERENCE_USES_A_SYMBOLIC_LINK_PATH, path=path))
            path.mkdir(exist_ok=True)
            created.append(str(path))
    return created
